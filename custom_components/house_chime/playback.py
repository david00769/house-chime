"""Playback orchestration through Music Assistant/Juke."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import Any, Callable
from urllib.parse import quote, unquote, urlsplit, urlunsplit

from .discovery import (
    DiscoveredEntity,
    UNAVAILABLE_STATES,
    has_music_assistant_announcement_features,
    is_music_assistant_announcement_player,
)
from .media import LOCAL_MEDIA_PREFIX
from .models import AnnouncementResolution

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PlayerSnapshot:
    """Best-effort player state snapshot for restore."""

    entity_id: str
    state: str | None
    volume_level: float | None
    source: str | None


@dataclass(frozen=True, slots=True)
class PlaybackResult:
    """Outcome from the Music Assistant dispatch boundary."""

    warnings: tuple[str, ...] = ()
    dispatched_group_count: int = 0
    cancelled_reason: str | None = None
    suppression_until: str | None = None


class PlaybackMediaError(Exception):
    """Raised when a resolved media URL cannot be fetched by a server-side player."""


async def play_music_assistant_announcement(
    hass: Any,
    resolution: AnnouncementResolution,
    *,
    should_cancel: Callable[[], tuple[str | None, str | None]] | None = None,
) -> PlaybackResult:
    """Play a resolved announcement through Music Assistant.

    This is the runtime boundary. The resolver decides what to play and where;
    this function only translates the plan into Home Assistant service calls.
    """

    if not resolution.ok or not resolution.media_path:
        raise ValueError(f"Cannot play unresolved announcement: {resolution.to_dict()}")

    incompatible_targets = _incompatible_music_assistant_targets(
        hass,
        resolution.target_player_entity_ids,
    )
    if incompatible_targets:
        raise PlaybackMediaError(
            "incompatible_playback_targets:" + ",".join(incompatible_targets)
        )

    snapshots = [_snapshot_player(hass, entity_id) for entity_id in resolution.target_player_entity_ids]

    service_data = {
        "url": await _playback_url(hass, resolution.media_path),
    }
    if resolution.trigger_sound_path:
        service_data["use_pre_announce"] = True
        service_data["pre_announce_url"] = await _playback_url(
            hass,
            resolution.trigger_sound_path,
        )

    await _assert_playback_url_reachable(hass, service_data["url"], "media")
    if pre_announce_url := service_data.get("pre_announce_url"):
        await _assert_playback_url_reachable(hass, pre_announce_url, "pre_announce")

    warnings: list[str] = []
    dispatched_group_count = 0
    cancelled_reason = None
    suppression_until = None
    try:
        for volume_level, entity_ids in _target_volume_groups(resolution):
            if should_cancel is not None:
                cancelled_reason, suppression_until = should_cancel()
                if cancelled_reason:
                    break
            await hass.services.async_call(
                "music_assistant",
                "play_announcement",
                {
                    **service_data,
                    "announce_volume": int(round(volume_level * 100)),
                },
                blocking=True,
                target={"entity_id": entity_ids},
            )
            dispatched_group_count += 1
    except Exception:
        _LOGGER.exception("Music Assistant announcement playback failed")
        raise
    finally:
        if dispatched_group_count:
            warnings.extend(await _restore_player_snapshots(hass, snapshots))
    return PlaybackResult(
        warnings=tuple(warnings),
        dispatched_group_count=dispatched_group_count,
        cancelled_reason=cancelled_reason,
        suppression_until=suppression_until,
    )


def _target_volume_groups(
    resolution: AnnouncementResolution,
) -> list[tuple[float, list[str]]]:
    """Group targets by their resolved announcement level.

    Music Assistant accepts one ``announce_volume`` per service call. Grouping
    lets selected targets use deliberately different announcement levels while
    keeping targets at the same level in a single, simultaneous call.
    """

    groups: dict[float, list[str]] = {}
    for entity_id in resolution.target_player_entity_ids:
        volume_level = resolution.target_volume_levels.get(
            entity_id,
            resolution.volume_level,
        )
        groups.setdefault(volume_level, []).append(entity_id)
    return [(volume_level, entity_ids) for volume_level, entity_ids in groups.items()]


async def _playback_url(hass: Any, media_path: str) -> str:
    """Convert configured media into the URL shape Music Assistant expects."""

    if media_path.startswith(LOCAL_MEDIA_PREFIX):
        relative_path = unquote(media_path.removeprefix(LOCAL_MEDIA_PREFIX))
        path = f"/media/local/{quote(relative_path, safe='/')}"
        return f"{_ha_base_url(hass)}{await _signed_path(hass, path)}"
    return media_path


async def _signed_path(hass: Any, path: str) -> str:
    """Return a short-lived signed HA path when running inside Home Assistant."""

    if signer := getattr(hass, "async_sign_path", None):
        return await signer(path)

    try:
        from homeassistant.components.http.auth import async_sign_path
    except Exception:
        _LOGGER.debug("Home Assistant path signing helper is unavailable", exc_info=True)
        return path

    expiration = timedelta(seconds=300)
    try:
        return async_sign_path(
            hass,
            path,
            expiration,
            use_content_user=True,
        )
    except TypeError:
        try:
            return async_sign_path(hass, path, expiration)
        except TypeError as err:
            _LOGGER.warning("Home Assistant path signing helper rejected supported signatures")
            raise PlaybackMediaError(f"playback_url_signing_failed:{type(err).__name__}") from err
    except Exception as err:
        _LOGGER.warning("Home Assistant path signing failed", exc_info=True)
        raise PlaybackMediaError(f"playback_url_signing_failed:{type(err).__name__}") from err


async def _assert_playback_url_reachable(hass: Any, url: str, label: str) -> None:
    """Verify Music Assistant can fetch the URL shape before handoff."""

    status = await _probe_playback_url(hass, url)
    if status is None or 200 <= status < 400:
        return
    raise PlaybackMediaError(
        f"playback_url_unreachable:{label}:http_{status}:{_redact_url(url)}"
    )


async def _probe_playback_url(hass: Any, url: str) -> int | None:
    """Return HTTP status for a small unauthenticated media probe."""

    if probe := getattr(hass, "async_probe_playback_url", None):
        return await probe(url)

    try:
        from homeassistant.helpers.aiohttp_client import async_get_clientsession
    except Exception:
        return None

    session = async_get_clientsession(hass)
    try:
        async with session.get(url, headers={"Range": "bytes=0-0"}) as response:
            return response.status
    except Exception:
        _LOGGER.debug("Playback URL probe failed for %s", _redact_url(url), exc_info=True)
        return 0


def _redact_url(url: str) -> str:
    split = urlsplit(url)
    return urlunsplit((split.scheme, split.netloc, split.path, "", ""))


def _ha_base_url(hass: Any) -> str:
    try:
        from homeassistant.helpers.network import get_url

        return get_url(hass, prefer_external=False).rstrip("/")
    except Exception:
        config = getattr(hass, "config", None)
        api = getattr(config, "api", None)
        base_url = getattr(api, "base_url", None) or getattr(config, "internal_url", None)
        return str(base_url or "").rstrip("/")


def _incompatible_music_assistant_targets(hass: Any, entity_ids: list[str]) -> list[str]:
    incompatible: list[str] = []
    for entity_id in entity_ids:
        state = hass.states.get(entity_id)
        if state is None:
            incompatible.append(f"{entity_id}:missing")
            continue
        if state.state in UNAVAILABLE_STATES:
            incompatible.append(f"{entity_id}:{state.state}")
            continue
        attributes = dict(state.attributes or {})
        record = DiscoveredEntity(
            entity_id=entity_id,
            name=str(attributes.get("friendly_name") or entity_id),
            state=state.state,
            attributes=attributes,
        )
        if not is_music_assistant_announcement_player(record):
            incompatible.append(f"{entity_id}:not_music_assistant")
            continue
        if not has_music_assistant_announcement_features(record):
            incompatible.append(f"{entity_id}:missing_announcement_features")
            continue
    return incompatible


def _snapshot_player(hass: Any, entity_id: str) -> PlayerSnapshot:
    state = hass.states.get(entity_id)
    if state is None:
        return PlayerSnapshot(entity_id, None, None, None)
    attributes = state.attributes or {}
    return PlayerSnapshot(
        entity_id=entity_id,
        state=state.state,
        volume_level=attributes.get("volume_level"),
        source=attributes.get("source"),
    )


async def _restore_player_snapshots(hass: Any, snapshots: list[PlayerSnapshot]) -> list[str]:
    warnings: list[str] = []
    for snapshot in snapshots:
        if snapshot.volume_level is not None:
            try:
                await hass.services.async_call(
                    "media_player",
                    "volume_set",
                    {"entity_id": snapshot.entity_id, "volume_level": snapshot.volume_level},
                    blocking=False,
                )
            except Exception:
                _LOGGER.exception("Failed to restore volume for %s", snapshot.entity_id)
                warnings.append(f"volume_restore_failed:{snapshot.entity_id}")

        current = hass.states.get(snapshot.entity_id)
        current_source = (current.attributes or {}).get("source") if current is not None else None
        if snapshot.source and current_source and snapshot.source != current_source:
            try:
                await hass.services.async_call(
                    "media_player",
                    "select_source",
                    {"entity_id": snapshot.entity_id, "source": snapshot.source},
                    blocking=False,
                )
            except Exception:
                _LOGGER.debug("Source restore is not supported for %s", snapshot.entity_id)
                warnings.append(f"source_restore_unsupported:{snapshot.entity_id}")
    return warnings
