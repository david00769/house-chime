from __future__ import annotations

import unittest

from custom_components.house_chime.models import AnnouncementConfig, AnnouncementResolution, ZoneConfig
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
        status = initial_status(
            AnnouncementConfig(
                default_context_id="david",
                zones=[],
            )
        )
        resolution = AnnouncementResolution(
            event_id="front_door_approach",
            ok=True,
            active_context_id="david",
            present_person_ids=["david", "claudette"],
            playback_enabled_person_ids=["david"],
            playback_disabled_person_ids=["claudette"],
            media_path="media-source://media_source/local/announcements/front-door.mp3",
            target_player_entity_ids=["media_player.great_room"],
            quiet_active=True,
        )

        record_resolution(status, resolution, outcome="played")

        self.assertEqual(status["last_resolved_event"], "front_door_approach")
        self.assertEqual(status["last_played_event"], "front_door_approach")
        self.assertEqual(status["active_household_context"], "david")
        self.assertEqual(status["last_media_path"], "media-source://media_source/local/announcements/front-door.mp3")
        self.assertTrue(status["quiet_mode_active"])
        self.assertTrue(status["last_resolution_valid"])
        self.assertEqual(status["present_household_people"], ["david", "claudette"])
        self.assertEqual(status["playback_enabled_people"], ["david"])
        self.assertEqual(status["playback_disabled_people"], ["claudette"])

    def test_intentional_person_preference_suppression_is_not_a_failure(self) -> None:
        status = initial_status(AnnouncementConfig())
        resolution = AnnouncementResolution(
            event_id="front_door_doorbell",
            ok=True,
            suppressed=True,
            present_person_ids=["resident"],
            playback_disabled_person_ids=["resident"],
            suppression_reason="all_present_people_muted",
        )

        record_resolution(status, resolution, outcome="suppressed")

        self.assertTrue(status["last_resolution_valid"])
        self.assertIsNone(status["last_failure_reason"])
        self.assertEqual(status["last_suppression_reason"], "all_present_people_muted")

    def test_record_resolution_keeps_configured_selected_zones_stable(self) -> None:
        config = AnnouncementConfig(
            default_context_id="david",
            zones=[ZoneConfig(entity_id="media_player.living_room_3", selected=True)],
        )
        status = initial_status(config)
        resolution = AnnouncementResolution(
            event_id="front_door_doorbell",
            ok=False,
            suppressed=True,
            errors=["duplicate_suppressed:front_door_doorbell"],
        )

        record_resolution(status, resolution, outcome="failed")

        self.assertEqual(status["selected_target_zones"], ["media_player.living_room_3"])
        self.assertEqual(status["active_household_context"], "david")

    def test_duplicate_suppression_preserves_last_operator_context(self) -> None:
        status = initial_status(
            AnnouncementConfig(
                default_context_id="david",
                zones=[
                    ZoneConfig(entity_id="media_player.living_room_3", selected=True),
                    ZoneConfig(entity_id="media_player.whole_house", selected=True),
                ],
            )
        )
        record_resolution(
            status,
            AnnouncementResolution(
                event_id="front_door_doorbell",
                ok=True,
                active_context_id="david",
                media_path="media-source://media_source/local/announcements/doorbell.mp3",
                quiet_active=True,
            ),
            outcome="played",
        )

        record_resolution(
            status,
            AnnouncementResolution(
                event_id="front_door_doorbell",
                ok=False,
                suppressed=True,
                errors=["duplicate_suppressed:front_door_doorbell"],
            ),
            outcome="failed",
        )

        self.assertEqual(
            status["selected_target_zones"],
            ["media_player.living_room_3", "media_player.whole_house"],
        )
        self.assertEqual(status["active_household_context"], "david")
        self.assertEqual(
            status["last_media_path"],
            "media-source://media_source/local/announcements/doorbell.mp3",
        )
        self.assertTrue(status["quiet_mode_active"])
        self.assertFalse(status["last_resolution_valid"])
        self.assertEqual(
            status["last_failure_reason"],
            "duplicate_suppressed:front_door_doorbell",
        )

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
