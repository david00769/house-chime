from __future__ import annotations

from copy import deepcopy
import unittest

from custom_components.house_chime.storage import migrate_config_dict


class StorageTest(unittest.TestCase):
    def test_migration_seeds_required_keys(self) -> None:
        migrated, changed = migrate_config_dict({})

        self.assertTrue(changed)
        self.assertEqual(migrated["version"], 4)
        self.assertEqual(migrated["people"], [])
        self.assertEqual(migrated["zones"], [])
        self.assertEqual(migrated["playback_routes"], [])
        self.assertEqual([voice["id"] for voice in migrated["voices"]], ["eve", "leo", "pierce", "samantha"])
        self.assertEqual(
            [event["id"] for event in migrated["events"]],
            ["front_door_approach", "front_door_package", "front_door_doorbell"],
        )
        self.assertEqual(migrated["quiet"]["start"], "22:00")
        self.assertEqual(migrated["quiet"]["end"], "08:00")
        self.assertEqual(migrated["quiet"]["volume_multiplier"], 0.5)
        self.assertEqual(migrated["normal_volume"], 0.8)
        self.assertEqual(
            migrated["door_guard"],
            {"sensor_entity_id": None, "cooldown_seconds": 180},
        )
        self.assertEqual(migrated["zones"], [])

    def test_migration_seeds_selected_zone_volume_multipliers(self) -> None:
        migrated, changed = migrate_config_dict(
            {
                "version": 2,
                "zones": [
                    {
                        "entity_id": "media_player.bedroom",
                        "name": "Bedroom",
                        "selected": True,
                    }
                ],
            }
        )

        self.assertTrue(changed)
        self.assertEqual(migrated["version"], 4)
        self.assertEqual(migrated["zones"][0]["volume_multiplier"], 1.0)

    def test_migration_drops_removed_bridge_helper_fields(self) -> None:
        migrated, changed = migrate_config_dict(
            {
                "version": 1,
                "events": [
                    {
                        "id": "front_door_package",
                        "name": "Package",
                        "bridge_helper_entity_id": "input_boolean.package_arrived",
                    }
                ],
            }
        )

        self.assertTrue(changed)
        self.assertNotIn("bridge_helper_entity_id", migrated["events"][0])

    def test_migration_enables_existing_people_by_default(self) -> None:
        migrated, changed = migrate_config_dict(
            {
                "version": 1,
                "people": [{"id": "resident", "name": "Resident"}],
            }
        )

        self.assertTrue(changed)
        self.assertEqual(migrated["version"], 4)
        self.assertTrue(migrated["people"][0]["playback_enabled_when_home"])

    def test_v3_migration_preserves_existing_configuration_and_adds_door_guard(self) -> None:
        source = {
            "version": 3,
            "people": [
                {
                    "id": "resident",
                    "name": "Resident",
                    "entity_id": "person.resident",
                    "fallback_tracker_entity_ids": [
                        "device_tracker.resident_phone"
                    ],
                    "in_scope": True,
                    "default_voice_id": "pierce",
                    "custom_voice_profile": "warm",
                    "playback_enabled_when_home": False,
                }
            ],
            "person_priority": ["resident"],
            "default_context_id": "resident",
            "normal_volume": 0.65,
            "zones": [
                {
                    "entity_id": "media_player.kitchen",
                    "name": "Kitchen",
                    "selected": True,
                    "quiet_excluded": True,
                    "volume_multiplier": 0.75,
                }
            ],
            "playback_routes": [
                {
                    "target_player_entity_id": "media_player.kitchen",
                    "source": "Announcements",
                    "zone_entity_ids": ["media_player.kitchen_output"],
                }
            ],
            "voices": [
                {
                    "id": "pierce",
                    "name": "Pierce",
                    "source": "approved_media",
                    "media_by_event": {
                        "front_door_approach": (
                            "media-source://media_source/local/approach.mp3"
                        )
                    },
                }
            ],
            "events": [
                {
                    "id": "front_door_approach",
                    "name": "Approach",
                    "enabled": True,
                    "voice_by_context": {"resident": "pierce"},
                    "default_voice_id": "pierce",
                    "common_trigger_sound": (
                        "media-source://media_source/local/chime.mp3"
                    ),
                    "trigger_sound_by_context": {
                        "resident": (
                            "media-source://media_source/local/personal-chime.mp3"
                        )
                    },
                    "duplicate_window_seconds": 90,
                }
            ],
            "quiet": {
                "enabled": True,
                "start": "21:30",
                "end": "07:15",
                "volume_multiplier": 0.35,
                "excluded_zone_entity_ids": ["media_player.kitchen"],
                "zone_start": "22:30",
                "zone_end": "06:30",
            },
        }
        expected_existing = deepcopy(source)
        expected_existing.pop("version")

        migrated, changed = migrate_config_dict(source)

        self.assertTrue(changed)
        self.assertEqual(migrated["version"], 4)
        for key, expected in expected_existing.items():
            self.assertEqual(migrated[key], expected, key)
        self.assertEqual(
            migrated["door_guard"],
            {"sensor_entity_id": None, "cooldown_seconds": 180},
        )

    def test_door_guard_duration_is_normalised_to_the_public_range(self) -> None:
        too_high, high_changed = migrate_config_dict(
            {
                "version": 4,
                "door_guard": {
                    "sensor_entity_id": "",
                    "cooldown_seconds": 5000,
                },
            }
        )
        malformed, malformed_changed = migrate_config_dict(
            {
                "version": 4,
                "door_guard": {
                    "sensor_entity_id": "binary_sensor.front_door",
                    "cooldown_seconds": "not-a-number",
                },
            }
        )

        self.assertTrue(high_changed)
        self.assertEqual(
            too_high["door_guard"],
            {"sensor_entity_id": None, "cooldown_seconds": 3600},
        )
        self.assertTrue(malformed_changed)
        self.assertEqual(
            malformed["door_guard"],
            {
                "sensor_entity_id": "binary_sensor.front_door",
                "cooldown_seconds": 180,
            },
        )


if __name__ == "__main__":
    unittest.main()
