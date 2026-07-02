"""Runtime status helpers for entities and diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import AnnouncementConfig, AnnouncementResolution


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
    StatusEntityDescription("selected_target_zones", "Selected target zones", "mdi:speaker-multiple"),
    StatusEntityDescription("last_media_path", "Last media path", "mdi:file-music"),
    StatusEntityDescription("last_failure_reason", "Last failure reason", "mdi:alert"),
)

BINARY_SENSOR_DESCRIPTIONS = (
    StatusEntityDescription("integration_ready", "Integration ready", "mdi:check-circle"),
    StatusEntityDescription("quiet_mode_active", "Quiet mode active", "mdi:volume-low"),
    StatusEntityDescription("last_resolution_valid", "Last resolution valid", "mdi:check-decagram"),
)


def status_entity_name(description: StatusEntityDescription) -> str:
    """Return the public HA entity name used to derive stable entity IDs."""

    return f"House Chime {description.name}"


def status_native_value(key: str, value: Any) -> Any:
    """Return a HA-safe sensor state value for a status key."""

    if key == "selected_target_zones" and isinstance(value, list):
        return f"{len(value)} speakers selected"
    if key == "last_failure_reason" and isinstance(value, str) and len(value) > 255:
        return f"{value.split(':', 1)[0]} (see details)"
    if isinstance(value, list):
        return ", ".join(value)
    return value


def initial_status(config: AnnouncementConfig) -> dict[str, Any]:
    """Return initial status for a loaded integration entry."""

    return {
        "integration_ready": True,
        "last_resolved_event": None,
        "last_played_event": None,
        "last_failed_event": None,
        "active_household_context": config.default_context_id,
        "selected_target_zones": [zone.entity_id for zone in config.zones if zone.selected],
        "last_media_path": None,
        "last_failure_reason": None,
        "quiet_mode_active": False,
        "last_resolution_valid": False,
        "last_resolution": None,
    }


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
    if not resolution.suppressed:
        status["active_household_context"] = resolution.active_context_id
        status["last_media_path"] = resolution.media_path
        status["quiet_mode_active"] = resolution.quiet_active
    status["last_resolution_valid"] = resolution.ok
    status["last_resolution"] = resolution.to_dict()

    if outcome == "played" and resolution.ok:
        status["last_played_event"] = resolution.event_id
        status["last_failure_reason"] = None
    elif outcome == "failed" or not resolution.ok:
        status["last_failed_event"] = resolution.event_id
        status["last_failure_reason"] = "; ".join(resolution.errors or resolution.warnings)
