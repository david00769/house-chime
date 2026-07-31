"""Runtime status helpers for entities and diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .models import AnnouncementConfig, AnnouncementResolution
from .resolver import resolve_household_presence


@dataclass(frozen=True, slots=True)
class StatusEntityDescription:
    """Description for one exposed status entity."""

    key: str
    name: str
    icon: str | None = None


SENSOR_DESCRIPTIONS = (
    StatusEntityDescription("last_resolved_event", "Last resolved event", "mdi:bell-check"),
    StatusEntityDescription("last_played_event", "Last played event", "mdi:speaker-message"),
    StatusEntityDescription("last_failed_event", "Last failed event", "mdi:alert-circle"),
    StatusEntityDescription("active_household_context", "Active household context", "mdi:account-home"),
    StatusEntityDescription("present_household_people", "People home", "mdi:account-group"),
    StatusEntityDescription("playback_enabled_people", "Enabled listeners home", "mdi:account-check"),
    StatusEntityDescription("playback_disabled_people", "Muted listeners home", "mdi:account-off"),
    StatusEntityDescription("last_suppression_reason", "Last suppression reason", "mdi:volume-off"),
    StatusEntityDescription(
        "approach_suppression_until",
        "Approach suppression until",
        "mdi:timer-sand",
    ),
    StatusEntityDescription(
        "approach_wait_until",
        "Approach wait until",
        "mdi:account-clock",
    ),
    StatusEntityDescription("selected_target_zones", "Selected target zones", "mdi:speaker-multiple"),
    StatusEntityDescription("configured_daytime_volume", "Daytime announcement volume", "mdi:volume-high"),
    StatusEntityDescription("last_effective_volume", "Last effective announcement volume", "mdi:volume-medium"),
    StatusEntityDescription("last_media_path", "Last media path", "mdi:file-music"),
    StatusEntityDescription("last_failure_reason", "Last failure reason", "mdi:alert"),
)

BINARY_SENSOR_DESCRIPTIONS = (
    StatusEntityDescription("integration_ready", "Integration ready", "mdi:check-circle"),
    StatusEntityDescription("quiet_mode_active", "Quiet mode active", "mdi:volume-low"),
    StatusEntityDescription("last_resolution_valid", "Last resolution valid", "mdi:check-decagram"),
    StatusEntityDescription(
        "approach_suppression_active",
        "Approach suppression active",
        "mdi:door-open",
    ),
    StatusEntityDescription(
        "approach_waiting",
        "Approach waiting",
        "mdi:account-clock",
    ),
)


def status_entity_name(description: StatusEntityDescription) -> str:
    """Return the public HA entity name used to derive stable entity IDs."""

    return f"House Chime {description.name}"


def status_native_value(key: str, value: Any) -> Any:
    """Return a HA-safe sensor state value for a status key."""

    if key == "selected_target_zones" and isinstance(value, list):
        return f"{len(value)} speakers selected"
    if key == "present_household_people" and isinstance(value, list):
        return f"{len(value)} people home"
    if key in {"playback_enabled_people", "playback_disabled_people"} and isinstance(value, list):
        return f"{len(value)} people"
    if key in {"configured_daytime_volume", "last_effective_volume"} and isinstance(value, (int, float)):
        return f"{round(value * 100)}%"
    if key == "last_failure_reason" and isinstance(value, str) and len(value) > 255:
        return f"{value.split(':', 1)[0]} (see details)"
    if key in {"approach_suppression_until", "approach_wait_until"} and isinstance(
        value,
        str,
    ):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    if key in {"last_suppression_reason", "last_failure_reason"} and isinstance(
        value,
        str,
    ):
        return friendly_reason(value)
    if isinstance(value, list):
        return ", ".join(value)
    return value


def friendly_reason(reason: str | None) -> str | None:
    """Translate stable internal reason codes into concise operator copy."""

    if not reason:
        return None
    labels = {
        "front_door_open": "Front door is open",
        "recent_front_door_activity": "Recent front-door activity",
        "recent_doorbell_activity": "Recent Doorbell event",
        "doorbell_during_wait": "Doorbell rang during the wait",
        "front_door_open_during_wait": "Front door opened during the wait",
        "person_left_before_delay": "Person left before the wait finished",
        "approach_sensor_missing": "Person sensor is missing",
        "approach_sensor_unavailable": "Person sensor is unavailable",
        "approach_sensor_unknown": "Person sensor state is unknown",
        "approach_delay_not_configured": "Delayed Approach is not configured",
        "all_present_people_muted": "Everyone home has muted announcements",
    }
    return labels.get(reason, reason.replace("_", " ").capitalize())


def initial_status(
    config: AnnouncementConfig,
    states: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Return initial status for a loaded integration entry."""

    status = {
        "integration_ready": True,
        "last_resolved_event": None,
        "last_played_event": None,
        "last_failed_event": None,
        "active_household_context": config.default_context_id,
        "present_household_people": [],
        "playback_enabled_people": [],
        "playback_disabled_people": [],
        "last_suppression_reason": None,
        "approach_suppression_active": False,
        "approach_suppression_until": None,
        "approach_suppression_reason": None,
        "approach_waiting": False,
        "approach_wait_started_at": None,
        "approach_wait_until": None,
        "approach_delay_seconds": config.approach_delay.delay_seconds,
        "approach_delay_sensor_entity_id": config.approach_delay.sensor_entity_id,
        "approach_delay_sensor_state": (
            (states or {}).get(config.approach_delay.sensor_entity_id)
            if config.approach_delay.sensor_entity_id
            else None
        ),
        "approach_delay_warning": None,
        "last_approach_wait_cancellation_reason": None,
        "door_guard_sensor_entity_id": config.door_guard.sensor_entity_id,
        "door_guard_sensor_state": (
            (states or {}).get(config.door_guard.sensor_entity_id)
            if config.door_guard.sensor_entity_id
            else None
        ),
        "door_guard_warning": None,
        "selected_target_zones": [zone.entity_id for zone in config.zones if zone.selected],
        "configured_daytime_volume": config.normal_volume,
        "last_effective_volume": None,
        "last_media_path": None,
        "last_failure_reason": None,
        "quiet_mode_active": False,
        "last_resolution_valid": False,
        "last_resolution": None,
    }
    refresh_presence_status(status, config, states or {})
    return status


def refresh_presence_status(
    status: dict[str, Any],
    config: AnnouncementConfig,
    states: dict[str, str],
) -> None:
    """Refresh dashboard presence values from the current entity states."""

    present, enabled, disabled, active_context_id = resolve_household_presence(
        config,
        states,
    )
    status["present_household_people"] = present
    status["playback_enabled_people"] = enabled
    status["playback_disabled_people"] = disabled
    status["active_household_context"] = (
        active_context_id if present else config.default_context_id
    )


def record_resolution(
    status: dict[str, Any],
    resolution: AnnouncementResolution,
    *,
    outcome: str,
    has_music_assistant: bool | None = None,
) -> None:
    """Update runtime status after resolve/play actions."""

    if has_music_assistant is not None:
        status["integration_ready"] = bool(has_music_assistant)
    status["last_resolved_event"] = resolution.event_id
    if not resolution.suppressed or resolution.suppression_reason:
        status["active_household_context"] = resolution.active_context_id
        status["last_media_path"] = resolution.media_path
        status["quiet_mode_active"] = resolution.quiet_active
        status["last_effective_volume"] = resolution.volume_level
    status["present_household_people"] = list(resolution.present_person_ids)
    status["playback_enabled_people"] = list(resolution.playback_enabled_person_ids)
    status["playback_disabled_people"] = list(resolution.playback_disabled_person_ids)
    status["last_suppression_reason"] = resolution.suppression_reason
    status["last_resolution_valid"] = resolution.ok
    status["last_resolution"] = resolution.to_dict()

    if outcome == "played" and resolution.ok:
        status["last_played_event"] = resolution.event_id
        status["last_failure_reason"] = None
    elif outcome == "suppressed":
        status["last_failure_reason"] = None
    elif outcome == "failed" or not resolution.ok:
        status["last_failed_event"] = resolution.event_id
        status["last_failure_reason"] = "; ".join(resolution.errors or resolution.warnings)
