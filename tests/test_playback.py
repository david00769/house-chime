from __future__ import annotations

import sys
from datetime import timedelta
from types import ModuleType
import unittest

from custom_components.house_chime.models import AnnouncementResolution
from custom_components.house_chime.playback import (
    PlaybackMediaError,
    play_music_assistant_announcement,
)


class FakeState:
    def __init__(self, entity_id: str, state: str, attributes: dict) -> None:
        self.entity_id = entity_id
        self.state = state
        self.attributes = attributes


class FakeStates:
    def __init__(self) -> None:
        self._states = {
            "media_player.great_room": FakeState(
                "media_player.great_room",
                "playing",
                {"volume_level": 0.3, "source": "AirPlay"},
            ),
            "media_player.bedroom": FakeState(
                "media_player.bedroom",
                "idle",
                {"volume_level": 0.2, "source": "Juke"},
            ),
        }

    def get(self, entity_id: str):
        return self._states.get(entity_id)


class FakeServices:
    def __init__(self, states: FakeStates) -> None:
        self.states = states
        self.calls = []

    async def async_call(
        self,
        domain: str,
        service: str,
        data: dict,
        blocking: bool = False,
        target: dict | None = None,
    ) -> None:
        self.calls.append((domain, service, data, blocking, target))
        if domain == "music_assistant" and service == "play_announcement":
            for entity_id in target["entity_id"]:
                self.states._states[entity_id].attributes["source"] = "Announcement"
        if domain == "media_player" and service == "select_source":
            raise ValueError("select_source unsupported")


class FakeHass:
    def __init__(self) -> None:
        self.states = FakeStates()
        self.services = FakeServices(self.states)
        self.config = type("Config", (), {"internal_url": "http://ha.local:8123"})()
        self.probe_status = 200

    async def async_probe_playback_url(self, url: str) -> int:
        return self.probe_status


class FakeSignPathHass(FakeHass):
    async def async_sign_path(self, path: str, expiration: int = 300) -> str:
        return f"{path}?authSig=test-signature&expires={expiration}"


class PlaybackTest(unittest.IsolatedAsyncioTestCase):
    async def test_playback_uses_simultaneous_targets_and_restores_volume(self) -> None:
        hass = FakeHass()
        resolution = AnnouncementResolution(
            event_id="front_door_approach",
            ok=True,
            media_path="media-source://media_source/local/announcements/front-door.mp3",
            target_player_entity_ids=["media_player.great_room", "media_player.bedroom"],
            volume_level=0.8,
        )

        warnings = await play_music_assistant_announcement(hass, resolution)

        music_calls = [
            call for call in hass.services.calls if call[0] == "music_assistant"
        ]
        self.assertEqual(len(music_calls), 1)
        self.assertEqual(
            music_calls[0][4]["entity_id"],
            ["media_player.great_room", "media_player.bedroom"],
        )
        self.assertEqual(
            music_calls[0][2]["url"],
            "http://ha.local:8123/media/local/announcements/front-door.mp3",
        )
        self.assertEqual(music_calls[0][2]["announce_volume"], 80)

        volume_calls = [
            call for call in hass.services.calls if call[0:2] == ("media_player", "volume_set")
        ]
        self.assertEqual(volume_calls[0][2]["volume_level"], 0.3)
        self.assertEqual(volume_calls[1][2]["volume_level"], 0.2)
        self.assertIn("source_restore_unsupported:media_player.great_room", warnings)

    async def test_playback_passes_trigger_sound_as_pre_announce(self) -> None:
        hass = FakeHass()
        resolution = AnnouncementResolution(
            event_id="front_door_doorbell",
            ok=True,
            media_path="media-source://media_source/local/announcements/voice.mp3",
            trigger_sound_path="media-source://media_source/local/announcements/doorbell.mp3",
            target_player_entity_ids=["media_player.great_room"],
            volume_level=0.5,
        )

        await play_music_assistant_announcement(hass, resolution)

        music_call = [
            call for call in hass.services.calls if call[0] == "music_assistant"
        ][0]
        self.assertTrue(music_call[2]["use_pre_announce"])
        self.assertEqual(
            music_call[2]["pre_announce_url"],
            "http://ha.local:8123/media/local/announcements/doorbell.mp3",
        )

    async def test_playback_uses_signed_paths_when_home_assistant_supports_them(self) -> None:
        from custom_components.house_chime import playback

        original_signed_path = playback._signed_path

        async def fake_signed_path(hass, path):
            return await hass.async_sign_path(path)

        playback._signed_path = fake_signed_path
        try:
            hass = FakeSignPathHass()
            resolution = AnnouncementResolution(
                event_id="front_door_doorbell",
                ok=True,
                media_path="media-source://media_source/local/announcements/voice.mp3",
                target_player_entity_ids=["media_player.great_room"],
                volume_level=0.5,
            )

            await play_music_assistant_announcement(hass, resolution)
        finally:
            playback._signed_path = original_signed_path

        music_call = [
            call for call in hass.services.calls if call[0] == "music_assistant"
        ][0]
        self.assertEqual(
            music_call[2]["url"],
            "http://ha.local:8123/media/local/announcements/voice.mp3?authSig=test-signature&expires=300",
        )

    async def test_signing_helper_receives_timedelta_expiration(self) -> None:
        from custom_components.house_chime import playback

        module_names = [
            "homeassistant",
            "homeassistant.components",
            "homeassistant.components.http",
            "homeassistant.components.http.auth",
        ]
        originals = {name: sys.modules.get(name) for name in module_names}
        calls = []

        homeassistant = ModuleType("homeassistant")
        components = ModuleType("homeassistant.components")
        http = ModuleType("homeassistant.components.http")
        auth = ModuleType("homeassistant.components.http.auth")

        def fake_async_sign_path(hass, path, expiration, use_content_user=False):
            calls.append((path, expiration, use_content_user))
            return f"{path}?authSig=test-signature"

        auth.async_sign_path = fake_async_sign_path
        sys.modules.update(
            {
                "homeassistant": homeassistant,
                "homeassistant.components": components,
                "homeassistant.components.http": http,
                "homeassistant.components.http.auth": auth,
            }
        )
        try:
            signed = await playback._signed_path(FakeHass(), "/media/local/test.mp3")
        finally:
            for name, original in originals.items():
                if original is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = original

        self.assertEqual(signed, "/media/local/test.mp3?authSig=test-signature")
        self.assertEqual(calls, [("/media/local/test.mp3", timedelta(seconds=300), True)])

    async def test_playback_fails_before_music_assistant_when_url_is_unreachable(self) -> None:
        hass = FakeHass()
        hass.probe_status = 401
        resolution = AnnouncementResolution(
            event_id="front_door_doorbell",
            ok=True,
            media_path="media-source://media_source/local/announcements/voice.mp3",
            target_player_entity_ids=["media_player.great_room"],
            volume_level=0.5,
        )

        with self.assertRaises(PlaybackMediaError) as err:
            await play_music_assistant_announcement(hass, resolution)

        self.assertIn("playback_url_unreachable:media:http_401", str(err.exception))
        music_calls = [
            call for call in hass.services.calls if call[0] == "music_assistant"
        ]
        self.assertEqual(music_calls, [])


if __name__ == "__main__":
    unittest.main()
