"""Pure data models for announcement resolution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .const import (
    DEFAULT_DUPLICATE_WINDOW_SECONDS,
    DEFAULT_NORMAL_VOLUME,
    DEFAULT_QUIET_MULTIPLIER,
)


@dataclass(slots=True)
class PersonConfig:
    """A person or household context selected by the operator."""

    id: str
    name: str
    entity_id: str | None = None
    fallback_tracker_entity_ids: list[str] = field(default_factory=list)
    in_scope: bool = True
    default_voice_id: str | None = None
    custom_voice_profile: str | None = None
    playback_enabled_when_home: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PersonConfig":
        return cls(
            id=str(data["id"]),
            name=str(data.get("name") or data["id"]),
            entity_id=data.get("entity_id"),
            fallback_tracker_entity_ids=list(data.get("fallback_tracker_entity_ids", [])),
            in_scope=bool(data.get("in_scope", True)),
            default_voice_id=data.get("default_voice_id"),
            custom_voice_profile=data.get("custom_voice_profile"),
            playback_enabled_when_home=bool(data.get("playback_enabled_when_home", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "entity_id": self.entity_id,
            "fallback_tracker_entity_ids": list(self.fallback_tracker_entity_ids),
            "in_scope": self.in_scope,
            "default_voice_id": self.default_voice_id,
            "custom_voice_profile": self.custom_voice_profile,
            "playback_enabled_when_home": self.playback_enabled_when_home,
        }


@dataclass(slots=True)
class ZoneConfig:
    """A Music Assistant/Juke playback target candidate."""

    entity_id: str
    name: str | None = None
    selected: bool = False
    quiet_excluded: bool = False
    volume_multiplier: float = 1.0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ZoneConfig":
        return cls(
            entity_id=str(data["entity_id"]),
            name=data.get("name"),
            selected=bool(data.get("selected", False)),
            quiet_excluded=bool(data.get("quiet_excluded", False)),
            volume_multiplier=float(data.get("volume_multiplier", 1.0)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "name": self.name,
            "selected": self.selected,
            "quiet_excluded": self.quiet_excluded,
            "volume_multiplier": self.volume_multiplier,
        }


@dataclass(slots=True)
class PlaybackRouteConfig:
    """Source route needed before playing to one announcement target."""

    target_player_entity_id: str
    source: str
    zone_entity_ids: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlaybackRouteConfig":
        return cls(
            target_player_entity_id=str(data["target_player_entity_id"]),
            source=str(data["source"]),
            zone_entity_ids=list(data.get("zone_entity_ids", [])),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_player_entity_id": self.target_player_entity_id,
            "source": self.source,
            "zone_entity_ids": list(self.zone_entity_ids),
        }


@dataclass(slots=True)
class VoicePersonality:
    """A named voice mapped to approved runtime media."""

    id: str
    name: str
    source: str
    media_by_event: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VoicePersonality":
        return cls(
            id=str(data["id"]),
            name=str(data.get("name") or data["id"]),
            source=str(data.get("source") or "approved_media"),
            media_by_event=dict(data.get("media_by_event", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "source": self.source,
            "media_by_event": dict(self.media_by_event),
        }


@dataclass(slots=True)
class EventConfig:
    """Operator configuration for one announcement event."""

    id: str
    name: str
    enabled: bool = True
    voice_by_context: dict[str, str] = field(default_factory=dict)
    default_voice_id: str | None = None
    common_trigger_sound: str | None = None
    trigger_sound_by_context: dict[str, str] = field(default_factory=dict)
    duplicate_window_seconds: int = DEFAULT_DUPLICATE_WINDOW_SECONDS

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EventConfig":
        return cls(
            id=str(data["id"]),
            name=str(data.get("name") or data["id"]),
            enabled=bool(data.get("enabled", True)),
            voice_by_context=dict(data.get("voice_by_context", {})),
            default_voice_id=data.get("default_voice_id"),
            common_trigger_sound=data.get("common_trigger_sound"),
            trigger_sound_by_context=dict(data.get("trigger_sound_by_context", {})),
            duplicate_window_seconds=int(
                data.get("duplicate_window_seconds", DEFAULT_DUPLICATE_WINDOW_SECONDS)
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "enabled": self.enabled,
            "voice_by_context": dict(self.voice_by_context),
            "default_voice_id": self.default_voice_id,
            "common_trigger_sound": self.common_trigger_sound,
            "trigger_sound_by_context": dict(self.trigger_sound_by_context),
            "duplicate_window_seconds": self.duplicate_window_seconds,
        }


@dataclass(slots=True)
class QuietConfig:
    """Quiet-mode and quiet-zone rules."""

    enabled: bool = False
    start: str = "22:00"
    end: str = "08:00"
    volume_multiplier: float = DEFAULT_QUIET_MULTIPLIER
    excluded_zone_entity_ids: list[str] = field(default_factory=list)
    zone_start: str | None = None
    zone_end: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "QuietConfig":
        if not data:
            return cls()
        return cls(
            enabled=bool(data.get("enabled", False)),
            start=str(data.get("start", "22:00")),
            end=str(data.get("end", "08:00")),
            volume_multiplier=float(data.get("volume_multiplier", DEFAULT_QUIET_MULTIPLIER)),
            excluded_zone_entity_ids=list(data.get("excluded_zone_entity_ids", [])),
            zone_start=data.get("zone_start"),
            zone_end=data.get("zone_end"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "start": self.start,
            "end": self.end,
            "volume_multiplier": self.volume_multiplier,
            "excluded_zone_entity_ids": list(self.excluded_zone_entity_ids),
            "zone_start": self.zone_start,
            "zone_end": self.zone_end,
        }


@dataclass(slots=True)
class AnnouncementConfig:
    """Durable operator-managed configuration."""

    version: int = 3
    people: list[PersonConfig] = field(default_factory=list)
    person_priority: list[str] = field(default_factory=list)
    default_context_id: str | None = None
    zones: list[ZoneConfig] = field(default_factory=list)
    playback_routes: list[PlaybackRouteConfig] = field(default_factory=list)
    voices: list[VoicePersonality] = field(default_factory=list)
    events: list[EventConfig] = field(default_factory=list)
    quiet: QuietConfig = field(default_factory=QuietConfig)
    normal_volume: float = DEFAULT_NORMAL_VOLUME

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "AnnouncementConfig":
        if not data:
            return cls()
        return cls(
            version=int(data.get("version", 1)),
            people=[PersonConfig.from_dict(item) for item in data.get("people", [])],
            person_priority=list(data.get("person_priority", [])),
            default_context_id=data.get("default_context_id"),
            zones=[ZoneConfig.from_dict(item) for item in data.get("zones", [])],
            playback_routes=[
                PlaybackRouteConfig.from_dict(item)
                for item in data.get("playback_routes", [])
            ],
            voices=[VoicePersonality.from_dict(item) for item in data.get("voices", [])],
            events=[EventConfig.from_dict(item) for item in data.get("events", [])],
            quiet=QuietConfig.from_dict(data.get("quiet")),
            normal_volume=float(data.get("normal_volume", DEFAULT_NORMAL_VOLUME)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "people": [item.to_dict() for item in self.people],
            "person_priority": list(self.person_priority),
            "default_context_id": self.default_context_id,
            "zones": [item.to_dict() for item in self.zones],
            "playback_routes": [item.to_dict() for item in self.playback_routes],
            "voices": [item.to_dict() for item in self.voices],
            "events": [item.to_dict() for item in self.events],
            "quiet": self.quiet.to_dict(),
            "normal_volume": self.normal_volume,
        }


@dataclass(slots=True)
class ResolverRuntime:
    """Runtime inputs that do not belong in durable config."""

    states: dict[str, str] = field(default_factory=dict)
    available_media: set[str] | None = None
    last_triggered_by_event: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class AnnouncementResolution:
    """Resolved playback plan and diagnostics for an event."""

    event_id: str
    ok: bool
    suppressed: bool = False
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    active_context_id: str | None = None
    present_person_ids: list[str] = field(default_factory=list)
    playback_enabled_person_ids: list[str] = field(default_factory=list)
    playback_disabled_person_ids: list[str] = field(default_factory=list)
    suppression_reason: str | None = None
    voice_id: str | None = None
    media_path: str | None = None
    trigger_sound_path: str | None = None
    target_player_entity_ids: list[str] = field(default_factory=list)
    quiet_active: bool = False
    quiet_excluded_zone_entity_ids: list[str] = field(default_factory=list)
    volume_level: float = DEFAULT_NORMAL_VOLUME
    target_volume_levels: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "ok": self.ok,
            "suppressed": self.suppressed,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "active_context_id": self.active_context_id,
            "present_person_ids": list(self.present_person_ids),
            "playback_enabled_person_ids": list(self.playback_enabled_person_ids),
            "playback_disabled_person_ids": list(self.playback_disabled_person_ids),
            "suppression_reason": self.suppression_reason,
            "voice_id": self.voice_id,
            "media_path": self.media_path,
            "trigger_sound_path": self.trigger_sound_path,
            "target_player_entity_ids": list(self.target_player_entity_ids),
            "quiet_active": self.quiet_active,
            "quiet_excluded_zone_entity_ids": list(self.quiet_excluded_zone_entity_ids),
            "volume_level": self.volume_level,
            "target_volume_levels": dict(self.target_volume_levels),
        }
