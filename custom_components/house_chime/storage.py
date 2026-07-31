"""Config storage and migration helpers."""

from __future__ import annotations

from typing import Any

from .const import DEFAULT_EVENTS, DEFAULT_VOICES

CURRENT_CONFIG_VERSION = 5

DEFAULT_EVENT_NAMES = {
    "front_door_approach": "Front door approach",
    "front_door_package": "Front door package",
    "front_door_doorbell": "Doorbell press",
}

DEFAULT_VOICE_NAMES = {
    "eve": ("Eve", "xai"),
    "leo": ("Leo", "xai"),
    "pierce": ("Pierce", "chatterbox"),
    "samantha": ("Samantha", "chatterbox"),
}


def migrate_config_dict(data: dict[str, Any] | None) -> tuple[dict[str, Any], bool]:
    """Migrate a stored announcement config dictionary.

    Returns `(migrated_data, changed)`. V1 is intentionally small, but keeping
    this helper from the start gives future versions a stable upgrade path.
    """

    config = dict(data or {})
    changed = False

    if "version" not in config:
        config["version"] = 1
        changed = True

    if config["version"] > CURRENT_CONFIG_VERSION:
        raise ValueError(
            f"Unsupported House Chime config version {config['version']}"
        )

    if config["version"] < 2:
        config["version"] = 2
        changed = True

    if config["version"] < 3:
        for zone in config.get("zones", []):
            if "volume_multiplier" not in zone:
                zone["volume_multiplier"] = 1.0
                changed = True
        config["version"] = 3
        changed = True

    if config["version"] < 4:
        config.setdefault(
            "door_guard",
            {
                "sensor_entity_id": None,
                "cooldown_seconds": 180,
            },
        )
        config["version"] = 4
        changed = True

    if config["version"] < 5:
        config.setdefault(
            "approach_delay",
            {
                "sensor_entity_id": None,
                "delay_seconds": 30,
            },
        )
        config["version"] = 5
        changed = True

    if config["version"] < CURRENT_CONFIG_VERSION:
        config["version"] = CURRENT_CONFIG_VERSION
        changed = True

    config.setdefault("people", [])
    for person in config["people"]:
        if "playback_enabled_when_home" not in person:
            person["playback_enabled_when_home"] = True
            changed = True
    config.setdefault("person_priority", [])
    config.setdefault("default_context_id", None)
    config.setdefault("zones", [])
    config.setdefault("playback_routes", [])
    if not config.get("voices"):
        config["voices"] = [
            {
                "id": voice_id,
                "name": DEFAULT_VOICE_NAMES[voice_id][0],
                "source": DEFAULT_VOICE_NAMES[voice_id][1],
                "media_by_event": {},
            }
            for voice_id in DEFAULT_VOICES
        ]
        changed = True
    if not config.get("events"):
        config["events"] = [
            {
                "id": event_id,
                "name": DEFAULT_EVENT_NAMES[event_id],
                "enabled": event_id != "front_door_doorbell",
                "voice_by_context": {},
                "default_voice_id": "samantha",
                "common_trigger_sound": None,
                "trigger_sound_by_context": {},
                "duplicate_window_seconds": 45,
            }
            for event_id in DEFAULT_EVENTS
        ]
        changed = True
    else:
        for event in config["events"]:
            if "bridge_helper_entity_id" in event:
                event.pop("bridge_helper_entity_id", None)
                changed = True
    config.setdefault(
        "quiet",
        {
            "enabled": False,
            "start": "22:00",
            "end": "08:00",
            "volume_multiplier": 0.5,
            "excluded_zone_entity_ids": [],
            "zone_start": None,
            "zone_end": None,
        },
    )
    config.setdefault("normal_volume", 0.8)
    raw_approach_delay = config.get("approach_delay")
    if not isinstance(raw_approach_delay, dict):
        raw_approach_delay = {}
    try:
        delay_seconds = int(raw_approach_delay.get("delay_seconds", 30))
    except (TypeError, ValueError):
        delay_seconds = 30
    normalised_approach_delay = {
        "sensor_entity_id": raw_approach_delay.get("sensor_entity_id") or None,
        "delay_seconds": max(0, min(300, delay_seconds)),
    }
    if config.get("approach_delay") != normalised_approach_delay:
        config["approach_delay"] = normalised_approach_delay
        changed = True
    raw_door_guard = config.get("door_guard")
    if not isinstance(raw_door_guard, dict):
        raw_door_guard = {}
    try:
        cooldown_seconds = int(raw_door_guard.get("cooldown_seconds", 180))
    except (TypeError, ValueError):
        cooldown_seconds = 180
    normalised_door_guard = {
        "sensor_entity_id": raw_door_guard.get("sensor_entity_id") or None,
        "cooldown_seconds": max(0, min(3600, cooldown_seconds)),
    }
    if config.get("door_guard") != normalised_door_guard:
        config["door_guard"] = normalised_door_guard
        changed = True
    return config, changed
