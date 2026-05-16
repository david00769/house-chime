from __future__ import annotations

import unittest

from custom_components.house_chime.models import AnnouncementConfig, AnnouncementResolution
from custom_components.house_chime.status import (
    SENSOR_DESCRIPTIONS,
    initial_status,
    record_resolution,
    status_entity_name,
    status_native_value,
)


class StatusTest(unittest.TestCase):
    def test_status_entity_names_are_house_chime_prefixed(self) -> None:
        self.assertEqual(
            status_entity_name(SENSOR_DESCRIPTIONS[0]),
            "House Chime Last resolved event",
        )

    def test_record_resolution_updates_lovelace_status_fields(self) -> None:
        status = initial_status(AnnouncementConfig(default_context_id="david"))
        resolution = AnnouncementResolution(
            event_id="front_door_approach",
            ok=True,
            active_context_id="david",
            media_path="media-source://media_source/local/announcements/front-door.mp3",
            target_player_entity_ids=["media_player.great_room"],
            quiet_active=True,
        )

        record_resolution(status, resolution, outcome="played")

        self.assertEqual(status["last_resolved_event"], "front_door_approach")
        self.assertEqual(status["last_played_event"], "front_door_approach")
        self.assertEqual(status["active_household_context"], "david")
        self.assertEqual(status["selected_target_zones"], ["media_player.great_room"])
        self.assertEqual(status["last_media_path"], "media-source://media_source/local/announcements/front-door.mp3")
        self.assertTrue(status["quiet_mode_active"])
        self.assertTrue(status["last_resolution_valid"])

    def test_record_failure_updates_failure_fields(self) -> None:
        status = initial_status(AnnouncementConfig())
        resolution = AnnouncementResolution(
            event_id="front_door_package",
            ok=False,
            errors=["missing_media_asset:test.mp3"],
        )

        record_resolution(status, resolution, outcome="failed")

        self.assertEqual(status["last_failed_event"], "front_door_package")
        self.assertEqual(status["last_failure_reason"], "missing_media_asset:test.mp3")
        self.assertFalse(status["last_resolution_valid"])

    def test_selected_target_zones_uses_short_state(self) -> None:
        self.assertEqual(
            status_native_value(
                "selected_target_zones",
                ["media_player.great_room", "media_player.bedroom"],
            ),
            "2 speakers selected",
        )

    def test_long_failure_reason_uses_short_state(self) -> None:
        value = "incompatible_playback_targets:" + ",".join(
            f"media_player.zone_{index}:missing_play_media" for index in range(20)
        )

        self.assertEqual(
            status_native_value("last_failure_reason", value),
            "incompatible_playback_targets (see details)",
        )


if __name__ == "__main__":
    unittest.main()
