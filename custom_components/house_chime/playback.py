"""Playback orchestration through Music Assistant/Juke."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any
from urllib.parse import quote, unquote, urlsplit, urlunsplit

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


class PlaybackMediaError(Exception):
    """Raised when a resolved media URL cannot be fetched by a server-side player."""


async def play_music_assistant_announcement(hass: Any, resolution: AnnouncementResolution) -> list[str]:
    """Play a resolved announcement through Music Assistant.

    This is the runtime boundary. The resolver decides what to play and where;
    this function only translates the plan into Home Assistant service calls.
    """

    if not resolution.ok or not resolution.media_path:
        raise ValueError(f"Cannot play unresolved announcement: {resolution.to_dict()}")

    snapshots = [_snapshot_player(hass, entity_id) for entity_id in resolution.target_player_entity_ids]

    service_data = {
        "url": await _playback_url(hass, resolution.media_path),
        "announce_volume": int(round(resolution.volume_level * 100)),
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
    try:
        await hass.services.async_call(
            "music_assistant",
            "play_announcement",
            service_data,
            blocking=True,
            target={"entity_id": list(resolution.target_player_entity_ids)},
        )
    except Exception:
        _LOGGER.exception("Music Assistant announcement playback failed")
        raise
    finally:
        warnings.extend(await _restore_player_snapshots(hass, snapshots))
    return warnings


async def _playback_url(hass: Any, media_path: str) -> str:
    """Convert configured media into the URL shape Music Assistant expects."""

    if media_path.startswith(LOCAL_MEDIA_PREFIX):
        relative_path = unquote(media_path.removeprefix(LOCAL_MEDIA_PREFIX))
        path = f"/media/local/{quote(relative_path, safe='/')}"
        return f"{_ha_base_url(hass)}{await _signed_path(hass, path)}"
    return media_path


async def _signed_path(hass: Any, path: str) -> str:
    """Return a short-lived signed HA path when running inside Home Assistant."""

    try:
        from homeassistant.components.http.auth import async_sign_path

        return async_sign_path(hass, path, expiration=300)
    except Exception:
        _LOGGER.debug("Falling back to unsigned media path", exc_info=True)
        return path


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
