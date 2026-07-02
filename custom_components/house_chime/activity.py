"""Home Assistant activity events for House Chime."""

from __future__ import annotations

from typing import Any

from .const import (
    ANNOUNCEMENT_EVENT_TYPES,
    BUS_EVENT_ANNOUNCEMENT,
    DOMAIN,
)
from .models import AnnouncementResolution


def announcement_event_data(
    event_type: str,
    resolution: AnnouncementResolution,
    *,
    source: str,
) -> dict[str, Any]:
    """Return normalized event data for HA Activity and automation triggers."""

    if event_type not in ANNOUNCEMENT_EVENT_TYPES:
        raise ValueError(f"Unsupported House Chime event type: {event_type}")
    return {
        "type": event_type,
        "domain": DOMAIN,
        "source": source,
        "event_id": resolution.event_id,
        "ok": resolution.ok,
        "suppressed": resolution.suppressed,
        "active_context_id": resolution.active_context_id,
        "voice_id": resolution.voice_id,
        "media_path": resolution.media_path,
        "target_player_entity_ids": list(resolution.target_player_entity_ids),
        "quiet_active": resolution.quiet_active,
        "errors": list(resolution.errors),
        "warnings": list(resolution.warnings),
    }


def fire_announcement_event(
    hass: Any,
    event_type: str,
    resolution: AnnouncementResolution,
    *,
    source: str,
) -> None:
    """Publish the normalized House Chime event."""

    data = announcement_event_data(event_type, resolution, source=source)
    hass.bus.async_fire(BUS_EVENT_ANNOUNCEMENT, data)
