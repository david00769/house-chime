from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from custom_components.house_chime import (
    SERVICE_INGEST,
    SERVICE_PLAY,
    _register_services,
    _start_approach_wait,
)
from custom_components.house_chime.const import (
    ANNOUNCEMENT_EVENT_PLAYED,
    BUS_EVENT_ANNOUNCEMENT,
    CONF_EVENT_ID,
    DOMAIN,
    EVENT_FRONT_DOOR_DOORBELL,
)
from custom_components.house_chime.models import (
    AnnouncementConfig,
    AnnouncementResolution,
    ApproachDelayConfig,
    DoorGuardConfig,
    EventConfig,
)
from custom_components.house_chime.playback import PlaybackResult
from custom_components.house_chime.status import initial_status
from conftest import FakeState


class FakeStates:
    def __init__(self, states: list[FakeState]) -> None:
        self._states = states

    def async_all(self) -> list[FakeState]:
        return list(self._states)


class FakeServices:
    def __init__(self) -> None:
        self.handlers = {}
        self.calls = []

    def has_service(self, domain: str, service: str) -> bool:
        return (
            (domain, service) in self.handlers
            or (domain, service)
            == ("music_assistant", "play_announcement")
        )

    def async_register(self, domain: str, service: str, handler, **_kwargs) -> None:
        self.handlers[(domain, service)] = handler

    async def async_call(self, domain: str, service: str, data: dict, **kwargs) -> None:
        self.calls.append((domain, service, data, kwargs))


class FakeBus:
    def __init__(self) -> None:
        self.events = []

    def async_fire(self, event_type: str, data: dict) -> None:
        self.events.append((event_type, data))


def fake_hass(config: AnnouncementConfig, states: list[FakeState]):
    services = FakeServices()
    bus = FakeBus()
    data = {
        "config": config,
        "status": initial_status(
            config,
            {state.entity_id: state.state for state in states},
        ),
        "last_resolution": None,
        "last_triggered_by_event": {},
        "door_suppression_until": None,
        "approach_wait_started_at": None,
        "approach_wait_until": None,
        "approach_wait_cancel_timer": None,
    }
    hass = SimpleNamespace(
        services=services,
        states=FakeStates(states),
        bus=bus,
        data={DOMAIN: {"entry-1": data}},
    )
    _register_services(hass)
    return hass, data


class DoorGuardServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_doorbell_cancels_pending_approach_before_resolution(self) -> None:
        config = AnnouncementConfig(
            approach_delay=ApproachDelayConfig(
                "binary_sensor.front_door_person",
                30,
            ),
            events=[
                EventConfig(id="front_door_approach", name="Approach")
            ],
        )
        hass, data = fake_hass(
            config,
            [FakeState("binary_sensor.front_door_person", "on")],
        )
        data["approach_wait_started_at"] = "2026-08-01T00:00:00+00:00"
        data["approach_wait_until"] = "2026-08-01T00:00:30+00:00"

        with patch(
            "custom_components.house_chime._resolve_from_service_call",
            new=AsyncMock(
                return_value=AnnouncementResolution(
                    event_id=EVENT_FRONT_DOOR_DOORBELL,
                    ok=True,
                    suppressed=True,
                    suppression_reason="duplicate_event",
                )
            ),
        ):
            await hass.services.handlers[(DOMAIN, SERVICE_PLAY)](
                SimpleNamespace(data={CONF_EVENT_ID: EVENT_FRONT_DOOR_DOORBELL})
            )

        self.assertIsNone(data["approach_wait_until"])
        self.assertEqual(
            data["status"]["last_approach_wait_cancellation_reason"],
            "doorbell_during_wait",
        )
        self.assertEqual(data["last_triggered_by_event"], {})
        self.assertIsNotNone(data["door_suppression_until"])
        self.assertEqual(
            data["door_suppression_reason"],
            "recent_doorbell_activity",
        )

        _start_approach_wait(hass, "entry-1", data)
        self.assertIsNone(data["approach_wait_until"])
        self.assertEqual(
            data["status"]["approach_suppression_reason"],
            "recent_doorbell_activity",
        )

    async def test_policy_ingress_queues_approach_instead_of_playing_now(self) -> None:
        config = AnnouncementConfig(
            approach_delay=ApproachDelayConfig(
                "binary_sensor.front_door_person",
                30,
            ),
            events=[
                EventConfig(id="front_door_approach", name="Approach")
            ],
        )
        hass, data = fake_hass(
            config,
            [FakeState("binary_sensor.front_door_person", "on")],
        )

        result = await hass.services.handlers[(DOMAIN, SERVICE_INGEST)](
            SimpleNamespace(data={CONF_EVENT_ID: "front_door_approach"})
        )

        self.assertTrue(result["ok"])
        self.assertTrue(result["queued"])
        self.assertIsNotNone(result["wait_until"])
        self.assertEqual(hass.services.calls, [])

    async def test_suppressed_play_never_dispatches_or_updates_duplicate_history(
        self,
    ) -> None:
        config = AnnouncementConfig(
            door_guard=DoorGuardConfig("binary_sensor.front_door", 180),
            events=[EventConfig(id="front_door_approach", name="Approach")],
        )
        hass, data = fake_hass(
            config,
            [FakeState("binary_sensor.front_door", "on", "Front Door")],
        )

        with patch(
            "custom_components.house_chime.async_available_media_for_resolution",
            new=AsyncMock(return_value=set()),
        ):
            result = await hass.services.handlers[(DOMAIN, SERVICE_PLAY)](
                SimpleNamespace(data={CONF_EVENT_ID: "front_door_approach"})
            )

        self.assertTrue(result["ok"])
        self.assertTrue(result["suppressed"])
        self.assertEqual(result["suppression_reason"], "front_door_open")
        self.assertEqual(hass.services.calls, [])
        self.assertEqual(data["last_triggered_by_event"], {})

    async def test_partial_group_dispatch_is_recorded_as_played_with_warning(
        self,
    ) -> None:
        config = AnnouncementConfig()
        hass, data = fake_hass(config, [])
        resolution = AnnouncementResolution(
            event_id="front_door_approach",
            ok=True,
            media_path="media-source://media_source/local/announcements/approach.mp3",
            target_player_entity_ids=["media_player.first", "media_player.second"],
        )

        with (
            patch(
                "custom_components.house_chime._resolve_from_service_call",
                new=AsyncMock(return_value=resolution),
            ),
            patch(
                "custom_components.house_chime.play_music_assistant_announcement",
                new=AsyncMock(
                    return_value=PlaybackResult(
                        dispatched_group_count=1,
                        cancelled_reason="recent_front_door_activity",
                        suppression_until="2026-08-01T00:03:00+00:00",
                    )
                ),
            ),
        ):
            result = await hass.services.handlers[(DOMAIN, SERVICE_PLAY)](
                SimpleNamespace(data={CONF_EVENT_ID: "front_door_approach"})
            )

        self.assertFalse(result["suppressed"])
        self.assertEqual(
            result["suppression_reason"],
            "recent_front_door_activity",
        )
        self.assertEqual(
            result["warnings"],
            ["door_guard_partial_dispatch:1"],
        )
        self.assertIn("front_door_approach", data["last_triggered_by_event"])
        self.assertTrue(
            any(
                event_type == BUS_EVENT_ANNOUNCEMENT
                and event_data["type"] == ANNOUNCEMENT_EVENT_PLAYED
                for event_type, event_data in hass.bus.events
            )
        )
