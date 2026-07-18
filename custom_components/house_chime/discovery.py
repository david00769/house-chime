"""Discovery helpers for Home Assistant state snapshots."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from .const import STATE_UNAVAILABLE, STATE_UNKNOWN

UNAVAILABLE_STATES = {STATE_UNAVAILABLE, STATE_UNKNOWN}
MUSIC_ASSISTANT_APP_ID = "music_assistant"
MUSIC_ASSISTANT_QUEUE_SOURCE = "music assistant queue"
MUSIC_ASSISTANT_TARGET_FEATURES = (512, 1048576)


@dataclass(frozen=True, slots=True)
class DiscoveredEntity:
    """Small serializable discovery record."""

    entity_id: str
    name: str
    state: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    def to_dict(self) -> dict[str, str | None]:
        return {"entity_id": self.entity_id, "name": self.name, "state": self.state}


def discover_people(states: Iterable[Any]) -> list[DiscoveredEntity]:
    """Return HA `person.*` candidates."""

    return _discover_domain(states, "person")


def discover_device_trackers(states: Iterable[Any]) -> list[DiscoveredEntity]:
    """Return device trackers that can be used as fallback presence sources."""

    return _discover_domain(states, "device_tracker")


def discover_media_players(states: Iterable[Any]) -> list[DiscoveredEntity]:
    """Return media-player candidates for Music Assistant/Juke selection."""

    return sorted(
        (_record(state) for state in states if _entity_id(state).startswith("media_player.")),
        key=_media_player_sort_key,
    )


def is_recommended_media_player(record: DiscoveredEntity) -> bool:
    """Return true for selectable Music Assistant announcement targets."""

    return is_selectable_announcement_player(record)


def is_selectable_announcement_player(record: DiscoveredEntity) -> bool:
    """Return true when House Chime can expose the player for selection."""

    return (
        is_available_media_player(record)
        and is_music_assistant_announcement_player(record)
        and has_music_assistant_announcement_features(record)
    )


def is_available_media_player(record: DiscoveredEntity) -> bool:
    """Return true when the media player exists and is currently usable."""

    return _normalise(record.state) not in UNAVAILABLE_STATES


def is_music_assistant_announcement_player(record: DiscoveredEntity) -> bool:
    """Return true when the player is owned or presented by Music Assistant."""

    attributes = record.attributes
    app_id = _normalise(attributes.get("app_id"))
    app_name = _normalise(attributes.get("app_name"))
    source = _normalise(attributes.get("source"))
    mass_player_type = _normalise(attributes.get("mass_player_type"))

    return (
        app_id == MUSIC_ASSISTANT_APP_ID
        or app_name == "music assistant"
        or source == MUSIC_ASSISTANT_QUEUE_SOURCE
        or mass_player_type == "player"
        or "mass_player_id" in attributes
    )


def has_music_assistant_announcement_features(record: DiscoveredEntity) -> bool:
    """Return true when Home Assistant reports Music Assistant target features."""

    try:
        supported_features = int(record.attributes.get("supported_features") or 0)
    except (TypeError, ValueError):
        supported_features = 0

    return all(
        supported_features & feature
        for feature in MUSIC_ASSISTANT_TARGET_FEATURES
    )


def _discover_domain(states: Iterable[Any], domain: str) -> list[DiscoveredEntity]:
    prefix = f"{domain}."
    return sorted((_record(state) for state in states if _entity_id(state).startswith(prefix)), key=lambda item: item.entity_id)


def _record(state: Any) -> DiscoveredEntity:
    entity_id = _entity_id(state)
    attributes = getattr(state, "attributes", {}) or {}
    name = attributes.get("friendly_name") or entity_id
    return DiscoveredEntity(
        entity_id=entity_id,
        name=str(name),
        state=getattr(state, "state", None),
        attributes=dict(attributes),
    )


def _entity_id(state: Any) -> str:
    return str(getattr(state, "entity_id", ""))


def _media_player_sort_key(record: DiscoveredEntity) -> tuple[int, str]:
    return (0 if is_recommended_media_player(record) else 1, record.entity_id)


def _normalise(value: Any) -> str:
    return str(value or "").strip().lower()
