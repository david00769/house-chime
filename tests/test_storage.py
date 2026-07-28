from __future__ import annotations

import unittest

from custom_components.house_chime.storage import migrate_config_dict


class StorageTest(unittest.TestCase):
    def test_migration_seeds_required_keys(self) -> None:
        migrated, changed = migrate_config_dict({})

        self.assertTrue(changed)
        self.assertEqual(migrated["version"], 3)
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
        self.assertEqual(migrated["version"], 3)
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
        self.assertEqual(migrated["version"], 3)
        self.assertTrue(migrated["people"][0]["playback_enabled_when_home"])


if __name__ == "__main__":
    unittest.main()
