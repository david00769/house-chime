from __future__ import annotations

import sys
import types
import unittest

from custom_components.house_chime.models import AnnouncementResolution
from custom_components.house_chime.repairs import (
    ISSUE_TYPES,
    _actionable_errors,
    async_create_resolution_issues,
)


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
                "incompatible_playback_targets:media_player.juke_zone:unavailable",
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
                    "incompatible_playback_targets:media_player.juke_zone:unavailable",
                ),
                (
                    "playback_url_signing_failed",
                    "playback_url_signing_failed:AttributeError",
                ),
            ],
        )

    def test_successful_resolution_clears_stale_event_issues(self) -> None:
        deleted: list[tuple[object, str, str]] = []
        issue_registry = types.ModuleType("homeassistant.helpers.issue_registry")
        issue_registry.async_delete_issue = (
            lambda hass, domain, issue_id: deleted.append((hass, domain, issue_id))
        )
        helpers = types.ModuleType("homeassistant.helpers")
        helpers.issue_registry = issue_registry
        homeassistant = types.ModuleType("homeassistant")
        homeassistant.helpers = helpers

        originals = {
            name: sys.modules.get(name)
            for name in (
                "homeassistant",
                "homeassistant.helpers",
                "homeassistant.helpers.issue_registry",
            )
        }
        sys.modules["homeassistant"] = homeassistant
        sys.modules["homeassistant.helpers"] = helpers
        sys.modules["homeassistant.helpers.issue_registry"] = issue_registry
        try:
            resolution = AnnouncementResolution(
                event_id="front_door_approach",
                ok=True,
            )

            self.loop.run_until_complete(async_create_resolution_issues("hass", resolution))
        finally:
            for name, original in originals.items():
                if original is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = original

        self.assertEqual(
            deleted,
            [
                ("hass", "house_chime", f"front_door_approach_{issue_type}")
                for issue_type in ISSUE_TYPES
            ],
        )

    def setUp(self) -> None:
        import asyncio

        self.loop = asyncio.new_event_loop()

    def tearDown(self) -> None:
        self.loop.close()


if __name__ == "__main__":
    unittest.main()
