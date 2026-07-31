"""Announcement resolver.

This module is intentionally pure Python so it can be tested outside a running
Home Assistant instance. The HA service layer should call this before touching
Music Assistant/Juke playback.
"""

from __future__ import annotations

from datetime import datetime, time, timezone

from .const import STATE_HOME, STATE_UNAVAILABLE, STATE_UNKNOWN
from .models import AnnouncementConfig, AnnouncementResolution, ResolverRuntime

APPROACH_EVENT_ID = "front_door_approach"


def resolve_household_presence(
    config: AnnouncementConfig,
    states: dict[str, str],
) -> tuple[list[str], list[str], list[str], str | None]:
    """Resolve configured household presence independently of an event.

    Presence is used by both event resolution and dashboard status. Keeping it
    separate prevents a dashboard from showing values left over from the last
    announcement or from integration startup.
    """

    people = {person.id: person for person in config.people if person.in_scope}
    present_person_ids = _present_person_ids(config, people, states)
    enabled_person_ids = [
        person_id
        for person_id in present_person_ids
        if getattr(people[person_id], "playback_enabled_when_home", True)
    ]
    disabled_person_ids = [
        person_id for person_id in present_person_ids if person_id not in enabled_person_ids
    ]

    if present_person_ids and not enabled_person_ids:
        active_context_id = None
    else:
        active_context_id = _active_context_id(
            config,
            people,
            states,
            allowed_person_ids=enabled_person_ids or None,
        )

    return (
        present_person_ids,
        enabled_person_ids,
        disabled_person_ids,
        active_context_id,
    )


def resolve_announcement(
    config: AnnouncementConfig,
    event_id: str,
    runtime: ResolverRuntime,
    *,
    now: datetime | None = None,
) -> AnnouncementResolution:
    """Resolve one announcement event into a playback plan."""

    now = now or datetime.now()
    events = {event.id: event for event in config.events}
    event = events.get(event_id)
    if event is None:
        return AnnouncementResolution(
            event_id=event_id,
            ok=False,
            errors=[f"unknown_event:{event_id}"],
        )

    resolution = AnnouncementResolution(
        event_id=event_id,
        ok=True,
    )

    if not event.enabled:
        resolution.ok = False
        resolution.errors.append(f"event_disabled:{event_id}")
        return resolution

    if event_id == APPROACH_EVENT_ID:
        suppression_reason, suppression_until, warning = evaluate_door_guard(
            config,
            runtime,
            now=now,
        )
        if warning:
            resolution.warnings.append(warning)
        if suppression_reason:
            resolution.suppressed = True
            resolution.suppression_reason = suppression_reason
            resolution.suppression_until = suppression_until
            return resolution

    if _is_duplicate(event_id, event.duplicate_window_seconds, runtime, now):
        resolution.ok = False
        resolution.suppressed = True
        resolution.errors.append(f"duplicate_suppressed:{event_id}")
        return resolution

    people = {person.id: person for person in config.people if person.in_scope}
    (
        present_person_ids,
        enabled_person_ids,
        disabled_person_ids,
        active_context_id,
    ) = resolve_household_presence(config, runtime.states)
    resolution.present_person_ids = present_person_ids
    resolution.playback_enabled_person_ids = enabled_person_ids
    resolution.playback_disabled_person_ids = disabled_person_ids

    # A shared speaker can only play once. If everyone present opts out, this
    # is an intentional suppression, not a failed announcement.
    if present_person_ids and not enabled_person_ids:
        resolution.suppressed = True
        resolution.suppression_reason = "all_present_people_muted"
        return resolution

    resolution.active_context_id = active_context_id

    voice_id = None
    if active_context_id:
        voice_id = event.voice_by_context.get(active_context_id)
        person = people.get(active_context_id)
        if voice_id is None and person is not None:
            voice_id = person.default_voice_id
    voice_id = voice_id or event.default_voice_id
    resolution.voice_id = voice_id

    voices = {voice.id: voice for voice in config.voices}
    voice = voices.get(voice_id or "")
    if voice is None:
        resolution.ok = False
        resolution.errors.append(f"missing_voice:{voice_id or 'none'}")
    else:
        media_path = voice.media_by_event.get(event_id)
        resolution.media_path = media_path
        if not media_path:
            resolution.ok = False
            resolution.errors.append(f"missing_media_mapping:{voice.id}:{event_id}")
        elif runtime.available_media is not None and media_path not in runtime.available_media:
            resolution.ok = False
            resolution.errors.append(f"missing_media_asset:{media_path}")

    if active_context_id:
        resolution.trigger_sound_path = event.trigger_sound_by_context.get(active_context_id)
    resolution.trigger_sound_path = resolution.trigger_sound_path or event.common_trigger_sound
    if (
        resolution.trigger_sound_path
        and runtime.available_media is not None
        and resolution.trigger_sound_path not in runtime.available_media
    ):
        resolution.ok = False
        resolution.errors.append(f"missing_trigger_sound_asset:{resolution.trigger_sound_path}")

    quiet_active = config.quiet.enabled and _time_in_window(now.time(), config.quiet.start, config.quiet.end)
    quiet_zone_active = quiet_active
    if config.quiet.zone_start and config.quiet.zone_end:
        quiet_zone_active = _time_in_window(now.time(), config.quiet.zone_start, config.quiet.zone_end)

    selected_zones = [zone.entity_id for zone in config.zones if zone.selected]
    excluded_zones = set(config.quiet.excluded_zone_entity_ids if quiet_zone_active else [])
    for zone in config.zones:
        if quiet_zone_active and zone.quiet_excluded:
            excluded_zones.add(zone.entity_id)

    targets = [entity_id for entity_id in selected_zones if entity_id not in excluded_zones]
    missing_targets = [
        entity_id
        for entity_id in targets
        if entity_id not in runtime.states
    ]
    unavailable_targets = [
        entity_id
        for entity_id in targets
        if runtime.states.get(entity_id) in {STATE_UNAVAILABLE, STATE_UNKNOWN}
    ]
    removed_targets = set(missing_targets) | set(unavailable_targets)
    targets = [entity_id for entity_id in targets if entity_id not in removed_targets]

    if not targets:
        resolution.ok = False
        resolution.errors.append("no_target_zones")
    if unavailable_targets:
        resolution.warnings.extend(f"unavailable_zone:{entity_id}" for entity_id in unavailable_targets)
    if missing_targets:
        resolution.warnings.extend(f"missing_zone:{entity_id}" for entity_id in missing_targets)

    resolution.target_player_entity_ids = targets
    resolution.quiet_active = quiet_active
    resolution.quiet_excluded_zone_entity_ids = sorted(excluded_zones)
    resolution.volume_level = _clamp_volume(
        config.normal_volume * (config.quiet.volume_multiplier if quiet_active else 1.0)
    )
    zones_by_entity = {zone.entity_id: zone for zone in config.zones}
    resolution.target_volume_levels = {
        entity_id: _clamp_volume(
            resolution.volume_level
            * max(0.0, zones_by_entity[entity_id].volume_multiplier)
        )
        for entity_id in targets
    }

    return resolution


def evaluate_door_guard(
    config: AnnouncementConfig,
    runtime: ResolverRuntime,
    *,
    now: datetime | None = None,
) -> tuple[str | None, str | None, str | None]:
    """Return the active door suppression reason, deadline, and warning.

    Missing and unavailable sensors intentionally fail open. A deadline that
    was already started by a valid open transition remains effective even if
    the sensor later becomes unavailable.
    """

    sensor_entity_id = config.door_guard.sensor_entity_id
    if not sensor_entity_id:
        return None, None, None

    now = now or datetime.now()
    sensor_state = runtime.states.get(sensor_entity_id)
    deadline = _parse_datetime(runtime.door_suppression_until)
    deadline_active = bool(deadline and _datetime_is_after(deadline, now))
    suppression_until = deadline.isoformat() if deadline_active and deadline else None

    warning = None
    if sensor_state is None:
        warning = f"door_guard_sensor_missing:{sensor_entity_id}"
    elif sensor_state in {STATE_UNAVAILABLE, STATE_UNKNOWN}:
        warning = f"door_guard_sensor_{sensor_state}:{sensor_entity_id}"

    if sensor_state == "on":
        return "front_door_open", suppression_until, warning
    if deadline_active:
        return "recent_front_door_activity", suppression_until, warning
    return None, None, warning


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _datetime_is_after(candidate: datetime, reference: datetime) -> bool:
    """Compare datetimes safely across tests and HA timezone-aware runtime."""

    if candidate.tzinfo is None and reference.tzinfo is not None:
        candidate = candidate.replace(tzinfo=timezone.utc)
    elif candidate.tzinfo is not None and reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    return candidate > reference


def _active_context_id(
    config: AnnouncementConfig,
    people: dict[str, object],
    states: dict[str, str],
    *,
    allowed_person_ids: list[str] | None = None,
) -> str | None:
    allowed = set(allowed_person_ids) if allowed_person_ids is not None else None
    priority = config.person_priority or list(people)
    priority = [person_id for person_id in priority if allowed is None or person_id in allowed]
    priority.extend(
        person_id
        for person_id in people
        if person_id not in priority and (allowed is None or person_id in allowed)
    )
    for person_id in priority:
        person = people.get(person_id)
        if person is None:
            continue
        entity_ids = []
        entity_id = getattr(person, "entity_id", None)
        if entity_id:
            entity_ids.append(entity_id)
        entity_ids.extend(getattr(person, "fallback_tracker_entity_ids", []))
        if any(states.get(entity_id) == STATE_HOME for entity_id in entity_ids):
            return person_id
    if config.default_context_id in people:
        return config.default_context_id
    return priority[0] if priority else None


def _present_person_ids(
    config: AnnouncementConfig,
    people: dict[str, object],
    states: dict[str, str],
) -> list[str]:
    """Return configured people currently detected at home in stable priority order."""

    priority = config.person_priority or list(people)
    priority = [person_id for person_id in priority if person_id in people]
    priority.extend(person_id for person_id in people if person_id not in priority)
    present = []
    for person_id in priority:
        person = people[person_id]
        entity_ids = []
        entity_id = getattr(person, "entity_id", None)
        if entity_id:
            entity_ids.append(entity_id)
        entity_ids.extend(getattr(person, "fallback_tracker_entity_ids", []))
        if any(states.get(entity_id) == STATE_HOME for entity_id in entity_ids):
            present.append(person_id)
    return present


def _is_duplicate(
    event_id: str,
    duplicate_window_seconds: int,
    runtime: ResolverRuntime,
    now: datetime,
) -> bool:
    if duplicate_window_seconds <= 0:
        return False
    last_value = runtime.last_triggered_by_event.get(event_id)
    if not last_value:
        return False
    try:
        last_triggered = datetime.fromisoformat(last_value)
    except ValueError:
        return False
    return (now - last_triggered).total_seconds() < duplicate_window_seconds


def _time_in_window(current: time, start_value: str, end_value: str) -> bool:
    start = _parse_time(start_value)
    end = _parse_time(end_value)
    if start <= end:
        return start <= current < end
    return current >= start or current < end


def _parse_time(value: str) -> time:
    hour, minute = value.split(":", 1)
    return time(int(hour), int(minute))


def _clamp_volume(value: float) -> float:
    return max(0.0, min(1.0, round(value, 3)))
