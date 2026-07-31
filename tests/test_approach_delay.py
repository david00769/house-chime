from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
import unittest

from custom_components.house_chime import (
    SERVICE_PLAY,
    _complete_approach_wait,
    _refresh_for_state_change,
    _start_approach_wait,
)
from custom_components.house_chime.approach_delay import (
    approach_sensor_warning,
    approach_wait_cancellation_reason,
    approach_wait_deadline,
)
from custom_components.house_chime.pending_policy import (
    approach_pending_policy,
    interaction_suppression_deadline,
)
from custom_components.house_chime.const import (
    ANNOUNCEMENT_EVENT_SUPPRESSED,
    BUS_EVENT_ANNOUNCEMENT,
    DOMAIN,
    EVENT_FRONT_DOOR_APPROACH,
)
from custom_components.house_chime.models import (
    AnnouncementConfig,
    ApproachDelayConfig,
    DoorGuardConfig,
    EventConfig,
)
from custom_components.house_chime.status import initial_status
from conftest import FakeState


class MutableStates:
    def __init__(self, states: list[FakeState]) -> None:
        self._states = {state.entity_id: state for state in states}

    def async_all(self) -> list[FakeState]:
        return list(self._states.values())

    def set(self, entity_id: str, state: str) -> None:
        current = self._states.get(entity_id)
        self._states[entity_id] = FakeState(
            entity_id,
            state,
            getattr(current, "name", None),
        )


class FakeBus:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def async_fire(self, event_type: str, data: dict) -> None:
        self.events.append((event_type, data))


class FakeServices:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict, dict]] = []

    def has_service(self, domain: str, service: str) -> bool:
        return (domain, service) == (
            "music_assistant",
            "play_announcement",
        )

    async def async_call(
        self,
        domain: str,
        service: str,
        data: dict,
        **kwargs,
    ) -> None:
        self.calls.append((domain, service, data, kwargs))


def fake_runtime(
    config: AnnouncementConfig,
    states: list[FakeState],
):
    state_store = MutableStates(states)
    state_map = {state.entity_id: state.state for state in states}
    data = {
        "config": config,
        "status": initial_status(config, state_map),
        "last_resolution": None,
        "last_triggered_by_event": {},
        "door_suppression_until": None,
        "door_guard_cancel_timer": None,
        "approach_wait_started_at": None,
        "approach_wait_until": None,
        "approach_wait_cancel_timer": None,
    }
    hass = SimpleNamespace(
        states=state_store,
        services=FakeServices(),
        bus=FakeBus(),
        data={DOMAIN: {"entry-1": data}},
    )
    return hass, data


def configured_rules() -> AnnouncementConfig:
    return AnnouncementConfig(
        approach_delay=ApproachDelayConfig(
            "binary_sensor.front_door_person",
            30,
        ),
        door_guard=DoorGuardConfig("binary_sensor.front_door", 180),
        events=[
            EventConfig(
                id=EVENT_FRONT_DOOR_APPROACH,
                name="Approach",
                enabled=True,
            )
        ],
    )


class ApproachDelayPolicyTest(unittest.TestCase):
    def test_deadline_and_continuous_presence_reasons(self) -> None:
        config = ApproachDelayConfig("binary_sensor.front_door_person", 30)
        now = datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc)

        self.assertEqual(
            approach_wait_deadline(config, now=now),
            "2026-08-01T00:00:30+00:00",
        )
        self.assertIsNone(
            approach_wait_cancellation_reason(
                config,
                {"binary_sensor.front_door_person": "on"},
            )
        )
        self.assertEqual(
            approach_wait_cancellation_reason(
                config,
                {"binary_sensor.front_door_person": "off"},
            ),
            "person_left_before_delay",
        )
        self.assertEqual(
            approach_sensor_warning(config, {}),
            "approach_sensor_missing:binary_sensor.front_door_person",
        )

    def test_approach_adapts_to_reusable_pending_policy(self) -> None:
        config = configured_rules()
        policy = approach_pending_policy(config)
        now = datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc)

        self.assertEqual(policy.event_id, EVENT_FRONT_DOOR_APPROACH)
        self.assertEqual(policy.hold_seconds, 30)
        self.assertIn("front_door_doorbell", policy.cancel_event_ids)
        self.assertEqual(
            interaction_suppression_deadline(policy, now=now),
            "2026-08-01T00:03:00+00:00",
        )


class ApproachDelayRuntimeTest(unittest.IsolatedAsyncioTestCase):
    async def test_wait_starts_once_and_completion_calls_play(self) -> None:
        config = configured_rules()
        hass, data = fake_runtime(
            config,
            [
                FakeState("binary_sensor.front_door_person", "on"),
                FakeState("binary_sensor.front_door", "off"),
            ],
        )
        now = datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc)
        data["status"]["last_approach_wait_cancellation_reason"] = (
            "person_left_before_delay"
        )

        _start_approach_wait(hass, "entry-1", data, now=now)
        original_deadline = data["approach_wait_until"]
        _start_approach_wait(
            hass,
            "entry-1",
            data,
            now=datetime(2026, 8, 1, 0, 0, 10, tzinfo=timezone.utc),
        )

        self.assertEqual(original_deadline, "2026-08-01T00:00:30+00:00")
        self.assertEqual(data["approach_wait_until"], original_deadline)
        self.assertTrue(data["status"]["approach_waiting"])
        self.assertIsNone(
            data["status"]["last_approach_wait_cancellation_reason"]
        )

        await _complete_approach_wait(hass, "entry-1", original_deadline)

        self.assertIsNone(data["approach_wait_until"])
        self.assertFalse(data["status"]["approach_waiting"])
        self.assertIsNone(
            data["status"]["last_approach_wait_cancellation_reason"]
        )
        self.assertEqual(
            hass.services.calls,
            [
                (
                    DOMAIN,
                    SERVICE_PLAY,
                    {"event_id": EVENT_FRONT_DOOR_APPROACH},
                    {"blocking": True},
                )
            ],
        )

    async def test_person_leaving_cancels_without_duplicate_history(self) -> None:
        config = configured_rules()
        hass, data = fake_runtime(
            config,
            [
                FakeState("binary_sensor.front_door_person", "on"),
                FakeState("binary_sensor.front_door", "off"),
            ],
        )
        _start_approach_wait(
            hass,
            "entry-1",
            data,
            now=datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc),
        )
        hass.states.set("binary_sensor.front_door_person", "off")

        _refresh_for_state_change(
            hass,
            "entry-1",
            "binary_sensor.front_door_person",
            "on",
            "off",
        )

        self.assertIsNone(data["approach_wait_until"])
        self.assertEqual(
            data["status"]["last_approach_wait_cancellation_reason"],
            "person_left_before_delay",
        )
        self.assertEqual(data["last_triggered_by_event"], {})
        self.assertTrue(
            any(
                event_type == BUS_EVENT_ANNOUNCEMENT
                and event_data["type"] == ANNOUNCEMENT_EVENT_SUPPRESSED
                and event_data["suppression_reason"]
                == "person_left_before_delay"
                for event_type, event_data in hass.bus.events
            )
        )

    async def test_front_door_open_cancels_and_starts_configured_quiet_time(
        self,
    ) -> None:
        config = configured_rules()
        hass, data = fake_runtime(
            config,
            [
                FakeState("binary_sensor.front_door_person", "on"),
                FakeState("binary_sensor.front_door", "off"),
            ],
        )
        _start_approach_wait(
            hass,
            "entry-1",
            data,
            now=datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc),
        )
        hass.states.set("binary_sensor.front_door", "on")

        _refresh_for_state_change(
            hass,
            "entry-1",
            "binary_sensor.front_door",
            "off",
            "on",
        )

        self.assertIsNone(data["approach_wait_until"])
        self.assertEqual(
            data["status"]["last_approach_wait_cancellation_reason"],
            "front_door_open_during_wait",
        )
        self.assertIsNotNone(data["door_suppression_until"])
        self.assertEqual(
            data["status"]["approach_suppression_reason"],
            "front_door_open",
        )
