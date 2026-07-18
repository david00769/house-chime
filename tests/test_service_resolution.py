from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from custom_components.house_chime import _resolve_from_service_call
from custom_components.house_chime.const import (
    CONF_EVENT_ID,
    CONF_SKIP_DUPLICATE_SUPPRESSION,
)
from custom_components.house_chime.models import (
    AnnouncementConfig,
    EventConfig,
    PersonConfig,
    VoicePersonality,
    ZoneConfig,
)


class FakeState:
    def __init__(self, entity_id: str, state: str) -> None:
        self.entity_id = entity_id
        self.state = state


class FakeStates:
    def __init__(self, states: list[FakeState]) -> None:
        self._states = states

    def async_all(self) -> list[FakeState]:
        return list(self._states)


class FakeHass:
    def __init__(self) -> None:
        self.states = FakeStates(
            [
                FakeState("person.david", "home"),
                FakeState("media_player.great_room", "idle"),
            ]
        )


def service_config() -> AnnouncementConfig:
    return AnnouncementConfig(
        people=[
            PersonConfig(
                id="david",
                name="David",
                entity_id="person.david",
                default_voice_id="samantha",
            )
        ],
        person_priority=["david"],
        zones=[ZoneConfig(entity_id="media_player.great_room", selected=True)],
        voices=[
            VoicePersonality(
                id="samantha",
                name="Samantha",
                source="approved_media",
                media_by_event={
                    "front_door_doorbell": "media-source://media_source/local/announcements/doorbell.mp3"
                },
            )
        ],
        events=[
            EventConfig(
                id="front_door_doorbell",
                name="Doorbell",
                default_voice_id="samantha",
                duplicate_window_seconds=45,
            )
        ],
    )


class ServiceResolutionTest(unittest.IsolatedAsyncioTestCase):
    async def test_service_resolution_respects_duplicate_suppression_by_default(self) -> None:
        now = datetime.now()
        data = {
            "config": service_config(),
            "last_triggered_by_event": {
                "front_door_doorbell": (now - timedelta(seconds=10)).isoformat()
            },
        }
        call = SimpleNamespace(data={CONF_EVENT_ID: "front_door_doorbell"})

        with patch(
            "custom_components.house_chime.async_available_media_for_resolution",
            return_value=set(),
        ):
            resolution = await _resolve_from_service_call(FakeHass(), data, call)

        self.assertFalse(resolution.ok)
        self.assertTrue(resolution.suppressed)
        self.assertEqual(
            resolution.errors,
            ["duplicate_suppressed:front_door_doorbell"],
        )

    async def test_service_resolution_can_skip_duplicate_suppression_for_manual_tests(self) -> None:
        now = datetime.now()
        media_path = "media-source://media_source/local/announcements/doorbell.mp3"
        data = {
            "config": service_config(),
            "last_triggered_by_event": {
                "front_door_doorbell": (now - timedelta(seconds=10)).isoformat()
            },
        }
        call = SimpleNamespace(
            data={
                CONF_EVENT_ID: "front_door_doorbell",
                CONF_SKIP_DUPLICATE_SUPPRESSION: True,
            }
        )

        with patch(
            "custom_components.house_chime.async_available_media_for_resolution",
            return_value={media_path},
        ):
            resolution = await _resolve_from_service_call(FakeHass(), data, call)

        self.assertTrue(resolution.ok)
        self.assertFalse(resolution.suppressed)
        self.assertEqual(resolution.target_player_entity_ids, ["media_player.great_room"])


if __name__ == "__main__":
    unittest.main()
