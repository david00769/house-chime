from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from custom_components.house_chime.models import (
    AnnouncementConfig,
    EventConfig,
    PersonConfig,
    QuietConfig,
    ResolverRuntime,
    VoicePersonality,
    ZoneConfig,
)
from custom_components.house_chime.resolver import resolve_announcement


def sample_config() -> AnnouncementConfig:
    return AnnouncementConfig(
        people=[
            PersonConfig(
                id="david",
                name="David",
                entity_id="person.david",
                default_voice_id="samantha",
            ),
            PersonConfig(
                id="claudette",
                name="Claudette",
                entity_id="person.claudette",
                default_voice_id="pierce",
            ),
        ],
        person_priority=["david", "claudette"],
        default_context_id="claudette",
        zones=[
            ZoneConfig(entity_id="media_player.great_room", selected=True),
            ZoneConfig(entity_id="media_player.bedroom", selected=True, quiet_excluded=True),
            ZoneConfig(entity_id="media_player.pool_deck", selected=False),
        ],
        voices=[
            VoicePersonality(
                id="samantha",
                name="Samantha",
                source="chatterbox",
                media_by_event={
                    "front_door_approach": "media-source://media_source/local/announcements/samantha-front-door.mp3"
                },
            ),
            VoicePersonality(
                id="pierce",
                name="Pierce",
                source="chatterbox",
                media_by_event={
                    "front_door_package": "media-source://media_source/local/announcements/pierce-package.mp3"
                },
            ),
        ],
        events=[
            EventConfig(
                id="front_door_approach",
                name="Front door approach",
                default_voice_id="samantha",
                common_trigger_sound="media-source://media_source/local/announcements/axel-f.mp3",
            ),
            EventConfig(
                id="front_door_package",
                name="Front door package",
                default_voice_id="pierce",
            ),
        ],
        quiet=QuietConfig(enabled=True, start="22:00", end="08:00", volume_multiplier=0.5),
        normal_volume=0.8,
    )


class ResolverTest(unittest.TestCase):
    def test_resolves_active_person_voice_media_and_targets(self) -> None:
        config = sample_config()
        runtime = ResolverRuntime(
            states={
                "person.david": "home",
                "person.claudette": "home",
                "media_player.great_room": "idle",
                "media_player.bedroom": "idle",
            },
            available_media={
                "media-source://media_source/local/announcements/samantha-front-door.mp3",
                "media-source://media_source/local/announcements/axel-f.mp3",
            },
        )

        resolution = resolve_announcement(
            config,
            "front_door_approach",
            runtime,
            now=datetime.fromisoformat("2026-05-15T14:00:00"),
        )

        self.assertTrue(resolution.ok)
        self.assertEqual(resolution.active_context_id, "david")
        self.assertEqual(resolution.voice_id, "samantha")
        self.assertEqual(
            resolution.media_path,
            "media-source://media_source/local/announcements/samantha-front-door.mp3",
        )
        self.assertEqual(
            resolution.trigger_sound_path,
            "media-source://media_source/local/announcements/axel-f.mp3",
        )
        self.assertEqual(
            resolution.target_player_entity_ids,
            ["media_player.great_room", "media_player.bedroom"],
        )
        self.assertEqual(resolution.volume_level, 0.8)
        self.assertEqual(
            resolution.target_volume_levels,
            {
                "media_player.great_room": 0.8,
                "media_player.bedroom": 0.8,
            },
        )
        self.assertEqual(resolution.present_person_ids, ["david", "claudette"])
        self.assertEqual(resolution.playback_enabled_person_ids, ["david", "claudette"])

    def test_muted_priority_person_does_not_silence_enabled_person(self) -> None:
        config = sample_config()
        config.people[0].playback_enabled_when_home = False
        runtime = ResolverRuntime(
            states={
                "person.david": "home",
                "person.claudette": "home",
                "media_player.great_room": "idle",
                "media_player.bedroom": "idle",
            },
            available_media={
                "media-source://media_source/local/announcements/pierce-package.mp3",
            },
        )

        resolution = resolve_announcement(
            config,
            "front_door_package",
            runtime,
            now=datetime.fromisoformat("2026-05-15T14:00:00"),
        )

        self.assertTrue(resolution.ok)
        self.assertFalse(resolution.suppressed)
        self.assertEqual(resolution.active_context_id, "claudette")
        self.assertEqual(resolution.playback_enabled_person_ids, ["claudette"])
        self.assertEqual(resolution.playback_disabled_person_ids, ["david"])

    def test_all_present_people_muted_is_an_intentional_suppression(self) -> None:
        config = sample_config()
        for person in config.people:
            person.playback_enabled_when_home = False
        runtime = ResolverRuntime(
            states={
                "person.david": "home",
                "person.claudette": "home",
            }
        )

        resolution = resolve_announcement(
            config,
            "front_door_package",
            runtime,
            now=datetime.fromisoformat("2026-05-15T14:00:00"),
        )

        self.assertTrue(resolution.ok)
        self.assertTrue(resolution.suppressed)
        self.assertEqual(resolution.suppression_reason, "all_present_people_muted")
        self.assertEqual(resolution.playback_disabled_person_ids, ["david", "claudette"])

    def test_quiet_window_reduces_volume_and_excludes_quiet_zone(self) -> None:
        config = sample_config()
        runtime = ResolverRuntime(
            states={
                "person.david": "home",
                "media_player.great_room": "idle",
                "media_player.bedroom": "idle",
            },
            available_media={
                "media-source://media_source/local/announcements/samantha-front-door.mp3",
                "media-source://media_source/local/announcements/axel-f.mp3",
            },
        )

        resolution = resolve_announcement(
            config,
            "front_door_approach",
            runtime,
            now=datetime.fromisoformat("2026-05-15T23:15:00"),
        )

        self.assertTrue(resolution.ok)
        self.assertTrue(resolution.quiet_active)
        self.assertEqual(resolution.volume_level, 0.4)
        self.assertEqual(resolution.target_volume_levels, {"media_player.great_room": 0.4})
        self.assertEqual(resolution.target_player_entity_ids, ["media_player.great_room"])
        self.assertEqual(resolution.quiet_excluded_zone_entity_ids, ["media_player.bedroom"])

    def test_target_multiplier_softens_only_the_configured_speaker(self) -> None:
        config = sample_config()
        config.zones[1].volume_multiplier = 0.5
        runtime = ResolverRuntime(
            states={
                "person.david": "home",
                "media_player.great_room": "idle",
                "media_player.bedroom": "idle",
            },
            available_media={
                "media-source://media_source/local/announcements/samantha-front-door.mp3",
                "media-source://media_source/local/announcements/axel-f.mp3",
            },
        )

        resolution = resolve_announcement(
            config,
            "front_door_approach",
            runtime,
            now=datetime.fromisoformat("2026-05-15T14:00:00"),
        )

        self.assertTrue(resolution.ok)
        self.assertEqual(resolution.volume_level, 0.8)
        self.assertEqual(
            resolution.target_volume_levels,
            {
                "media_player.great_room": 0.8,
                "media_player.bedroom": 0.4,
            },
        )

    def test_missing_media_asset_fails_loudly(self) -> None:
        config = sample_config()
        runtime = ResolverRuntime(
            states={"person.david": "home", "media_player.great_room": "idle"},
            available_media=set(),
        )

        resolution = resolve_announcement(
            config,
            "front_door_approach",
            runtime,
            now=datetime.fromisoformat("2026-05-15T14:00:00"),
        )

        self.assertFalse(resolution.ok)
        self.assertIn(
            "missing_media_asset:media-source://media_source/local/announcements/samantha-front-door.mp3",
            resolution.errors,
        )

    def test_missing_trigger_sound_asset_fails_loudly(self) -> None:
        config = sample_config()
        runtime = ResolverRuntime(
            states={"person.david": "home", "media_player.great_room": "idle"},
            available_media={
                "media-source://media_source/local/announcements/samantha-front-door.mp3"
            },
        )

        resolution = resolve_announcement(
            config,
            "front_door_approach",
            runtime,
            now=datetime.fromisoformat("2026-05-15T14:00:00"),
        )

        self.assertFalse(resolution.ok)
        self.assertIn(
            "missing_trigger_sound_asset:media-source://media_source/local/announcements/axel-f.mp3",
            resolution.errors,
        )

    def test_duplicate_window_suppresses_event(self) -> None:
        config = sample_config()
        now = datetime.fromisoformat("2026-05-15T14:00:00")
        runtime = ResolverRuntime(
            states={"person.david": "home", "media_player.great_room": "idle"},
            last_triggered_by_event={
                "front_door_approach": (now - timedelta(seconds=10)).isoformat()
            },
        )

        resolution = resolve_announcement(config, "front_door_approach", runtime, now=now)

        self.assertFalse(resolution.ok)
        self.assertTrue(resolution.suppressed)
        self.assertIn("duplicate_suppressed:front_door_approach", resolution.errors)

    def test_unavailable_zone_warns_and_is_removed_from_targets(self) -> None:
        config = sample_config()
        runtime = ResolverRuntime(
            states={
                "person.david": "home",
                "media_player.great_room": "unavailable",
                "media_player.bedroom": "idle",
            }
        )

        resolution = resolve_announcement(
            config,
            "front_door_approach",
            runtime,
            now=datetime.fromisoformat("2026-05-15T14:00:00"),
        )

        self.assertTrue(resolution.ok)
        self.assertEqual(resolution.target_player_entity_ids, ["media_player.bedroom"])
        self.assertIn("unavailable_zone:media_player.great_room", resolution.warnings)

    def test_missing_zone_warns_and_is_removed_from_targets(self) -> None:
        config = sample_config()
        runtime = ResolverRuntime(
            states={
                "person.david": "home",
                "media_player.bedroom": "idle",
            }
        )

        resolution = resolve_announcement(
            config,
            "front_door_approach",
            runtime,
            now=datetime.fromisoformat("2026-05-15T14:00:00"),
        )

        self.assertTrue(resolution.ok)
        self.assertEqual(resolution.target_player_entity_ids, ["media_player.bedroom"])
        self.assertIn("missing_zone:media_player.great_room", resolution.warnings)


if __name__ == "__main__":
    unittest.main()
