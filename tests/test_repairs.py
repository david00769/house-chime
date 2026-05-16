from __future__ import annotations

import unittest

from custom_components.house_chime.models import AnnouncementResolution
from custom_components.house_chime.repairs import _actionable_errors


class RepairsTest(unittest.TestCase):
    def test_actionable_errors_map_to_repair_issue_types(self) -> None:
        resolution = AnnouncementResolution(
            event_id="front_door_package",
            ok=False,
            errors=[
                "missing_media_asset:media-source://media_source/local/announcements/package.mp3",
                "missing_trigger_sound_asset:media-source://media_source/local/announcements/chime.mp3",
                "no_target_zones",
                "missing_music_assistant_service:music_assistant.play_announcement",
                "incompatible_playback_targets:media_player.juke_zone:missing_announce",
                "playback_url_signing_failed:AttributeError",
                "event_disabled:front_door_package",
            ],
        )

        self.assertEqual(
            _actionable_errors(resolution),
            [
                (
                    "missing_media",
                    "missing_media_asset:media-source://media_source/local/announcements/package.mp3",
                ),
                (
                    "missing_media",
                    "missing_trigger_sound_asset:media-source://media_source/local/announcements/chime.mp3",
                ),
                ("no_target_zones", "no_target_zones"),
                (
                    "missing_music_assistant_service",
                    "missing_music_assistant_service:music_assistant.play_announcement",
                ),
                (
                    "incompatible_playback_targets",
                    "incompatible_playback_targets:media_player.juke_zone:missing_announce",
                ),
                (
                    "playback_url_signing_failed",
                    "playback_url_signing_failed:AttributeError",
                ),
            ],
        )


if __name__ == "__main__":
    unittest.main()
