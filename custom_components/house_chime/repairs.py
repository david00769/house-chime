"""Repair issue helpers for House Chime."""

from __future__ import annotations

from typing import Any

from .const import DOMAIN
from .models import AnnouncementResolution

ISSUE_TYPES = (
    "missing_media",
    "no_target_zones",
    "missing_music_assistant_service",
    "incompatible_playback_targets",
    "playback_url_signing_failed",
    "playback_url_unreachable",
)


async def async_create_resolution_issues(hass: Any, resolution: AnnouncementResolution) -> None:
    """Create non-fatal Home Assistant repair issues for actionable failures."""

    if resolution.ok:
        await async_clear_resolution_issues(hass, resolution.event_id)
        return

    for issue_type, error in _actionable_errors(resolution):
        await _async_create_issue(hass, resolution.event_id, issue_type, error)


async def async_clear_resolution_issues(hass: Any, event_id: str) -> None:
    """Clear stale repair issues for an event after it resolves cleanly."""

    try:
        from homeassistant.helpers import issue_registry as ir
    except Exception:
        return

    for issue_type in ISSUE_TYPES:
        ir.async_delete_issue(hass, DOMAIN, _issue_id(event_id, issue_type))


def _actionable_errors(resolution: AnnouncementResolution) -> list[tuple[str, str]]:
    actionable: list[tuple[str, str]] = []
    for error in resolution.errors:
        if error.startswith(("missing_media_asset:", "missing_trigger_sound_asset:")):
            actionable.append(("missing_media", error))
        elif error == "no_target_zones":
            actionable.append(("no_target_zones", error))
        elif error.startswith("missing_music_assistant_service:"):
            actionable.append(("missing_music_assistant_service", error))
        elif error.startswith("incompatible_playback_targets:"):
            actionable.append(("incompatible_playback_targets", error))
        elif error.startswith("playback_url_signing_failed:"):
            actionable.append(("playback_url_signing_failed", error))
        elif error.startswith("playback_url_unreachable:"):
            actionable.append(("playback_url_unreachable", error))
    return actionable


async def _async_create_issue(hass: Any, event_id: str, issue_type: str, error: str) -> None:
    try:
        from homeassistant.helpers import issue_registry as ir
        from homeassistant.helpers.issue_registry import IssueSeverity
    except Exception:
        return

    ir.async_create_issue(
        hass,
        DOMAIN,
        _issue_id(event_id, issue_type),
        is_fixable=False,
        severity=IssueSeverity.WARNING,
        translation_key=issue_type,
        translation_placeholders={
            "event_id": event_id,
            "error": error,
        },
    )


def _issue_id(event_id: str, issue_type: str) -> str:
    return f"{event_id}_{issue_type}"
