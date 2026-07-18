"""Announcement resolver.

This module is intentionally pure Python so it can be tested outside a running
Home Assistant instance. The HA service layer should call this before touching
Music Assistant/Juke playback.
"""

from __future__ import annotations

from datetime import datetime, time

from .const import STATE_HOME, STATE_UNAVAILABLE, STATE_UNKNOWN
from .models import AnnouncementConfig, AnnouncementResolution, ResolverRuntime


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

    if _is_duplicate(event_id, event.duplicate_window_seconds, runtime, now):
        resolution.ok = False
        resolution.suppressed = True
        resolution.errors.append(f"duplicate_suppressed:{event_id}")
        return resolution

    people = {person.id: person for person in config.people if person.in_scope}
    active_context_id = _active_context_id(config, people, runtime.states)
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

    return resolution


def _active_context_id(
    config: AnnouncementConfig,
    people: dict[str, object],
    states: dict[str, str],
) -> str | None:
    priority = config.person_priority or list(people)
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
