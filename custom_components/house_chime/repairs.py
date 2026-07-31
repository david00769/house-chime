"""Repair issue helpers for House Chime."""

from __future__ import annotations

from typing import Any

from .const import DOMAIN
from .const import EVENT_FRONT_DOOR_APPROACH, STATE_UNAVAILABLE, STATE_UNKNOWN
from .models import AnnouncementConfig, AnnouncementResolution

ISSUE_TYPES = (
    "missing_media",
    "no_target_zones",
    "missing_music_assistant_service",
    "incompatible_playback_targets",
    "playback_url_signing_failed",
    "playback_url_unreachable",
)

SETUP_ISSUE_TYPES = (
    "delayed_approach_setup_required",
    "approach_sensor_problem",
    "door_sensor_problem",
)


async def async_sync_setup_issues(
    hass: Any,
    config: AnnouncementConfig,
    states: dict[str, str],
) -> None:
    """Synchronise actionable setup and sensor-health Repair issues."""

    try:
        from homeassistant.helpers import issue_registry as ir
        from homeassistant.helpers.issue_registry import IssueSeverity
    except Exception:
        return

    approach_enabled = any(
        event.id == EVENT_FRONT_DOOR_APPROACH and event.enabled
        for event in config.events
    )
    approach_sensor = config.approach_delay.sensor_entity_id
    problems: dict[str, str | None] = {
        "delayed_approach_setup_required": (
            "Choose the person-presence sensor and replace any legacy immediate "
            "Approach automation with house_chime.ingest_event."
            if approach_enabled and not approach_sensor
            else None
        ),
        "approach_sensor_problem": _sensor_problem(approach_sensor, states),
        "door_sensor_problem": _sensor_problem(
            config.door_guard.sensor_entity_id,
            states,
        ),
    }
    for issue_type, problem in problems.items():
        issue_id = f"setup_{issue_type}"
        if not problem:
            ir.async_delete_issue(hass, DOMAIN, issue_id)
            continue
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=IssueSeverity.WARNING,
            translation_key=issue_type,
            translation_placeholders={"problem": problem},
        )


def _sensor_problem(entity_id: str | None, states: dict[str, str]) -> str | None:
    """Return an operator-facing sensor problem, or None when usable/unset."""

    if not entity_id:
        return None
    state = states.get(entity_id)
    if state is None:
        return f"{entity_id} no longer exists"
    if state in {STATE_UNAVAILABLE, STATE_UNKNOWN}:
        return f"{entity_id} is {state}"
    return None


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
