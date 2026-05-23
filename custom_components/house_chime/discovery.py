"""Discovery helpers for Home Assistant state snapshots."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


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
    """Return true for likely Music Assistant/Juke announcement targets."""

    if is_music_assistant_announcement_player(record):
        return True

    haystack = " ".join(
        [
            record.entity_id,
            record.name,
            " ".join(str(key) for key in record.attributes),
            " ".join(str(value) for value in record.attributes.values()),
        ]
    ).lower()
    return any(
        token in haystack
        for token in (
            "music assistant",
            "music_assistant",
            "mass",
            "announcement",
        )
    )


def is_music_assistant_announcement_player(record: DiscoveredEntity) -> bool:
    """Return true when the player satisfies Music Assistant announcement target features."""

    # Historically we used `supported_features` bitflags as a proxy for announcement
    # capability. Music Assistant/Juke entities do not consistently expose these
    # flags, so relying on them creates false negatives and a confusing options UI.
    #
    # Instead, treat Music Assistant/Juke-flavored entities as announcement-capable
    # for recommendation purposes. Final compatibility checks happen at playback-time.
    haystack = " ".join(
        [
            record.entity_id,
            record.name,
            " ".join(str(key) for key in record.attributes),
            " ".join(str(value) for value in record.attributes.values()),
        ]
    ).lower()
    return any(token in haystack for token in ("music assistant", "music_assistant", "mass", "juke"))


def discover_helpers(states: Iterable[Any]) -> list[DiscoveredEntity]:
    """Return helper entities that can be used as bridge triggers."""

    helpers: list[DiscoveredEntity] = []
    for state in states:
        entity_id = _entity_id(state)
        if entity_id.startswith(("input_boolean.", "input_button.", "button.")):
            helpers.append(_record(state))
    return sorted(helpers, key=lambda item: item.entity_id)


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
