from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from custom_components.house_chime import (
    _expire_door_guard,
    _initial_door_suppression_until,
    _update_door_guard_state,
)
from custom_components.house_chime.const import BUS_EVENT_ANNOUNCEMENT, DOMAIN
from custom_components.house_chime.models import AnnouncementConfig, DoorGuardConfig
from custom_components.house_chime.status import initial_status
from conftest import FakeState


class FakeStates:
    def __init__(self, states: list[FakeState]) -> None:
        self._states = states

    def async_all(self) -> list[FakeState]:
        return list(self._states)

    def set(self, entity_id: str, state: str) -> None:
        self._states = [FakeState(entity_id, state, "Front Door")]


class FakeBus:
    def __init__(self) -> None:
        self.events = []

    def async_fire(self, event_type, data) -> None:
        self.events.append((event_type, data))


def configured_runtime(*, cooldown_seconds: int = 180, sensor_state: str = "off"):
    config = AnnouncementConfig(
        door_guard=DoorGuardConfig(
            sensor_entity_id="binary_sensor.front_door",
            cooldown_seconds=cooldown_seconds,
        )
    )
    states = FakeStates(
        [FakeState("binary_sensor.front_door", sensor_state, "Front Door")]
    )
    data = {
        "config": config,
        "status": initial_status(
            config,
            {"binary_sensor.front_door": sensor_state},
        ),
        "door_suppression_until": None,
        "door_guard_cancel_timer": None,
    }
    hass = SimpleNamespace(
        states=states,
        bus=FakeBus(),
        data={DOMAIN: {"entry-1": data}},
    )
    return hass, data


def test_startup_open_starts_fresh_cooldown_but_closed_does_not() -> None:
    config = AnnouncementConfig(
        door_guard=DoorGuardConfig("binary_sensor.front_door", 180)
    )
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)

    open_deadline = _initial_door_suppression_until(
        config,
        {"binary_sensor.front_door": "on"},
        now=now,
    )
    closed_deadline = _initial_door_suppression_until(
        config,
        {"binary_sensor.front_door": "off"},
        now=now,
    )

    assert open_deadline == (now + timedelta(seconds=180)).isoformat()
    assert closed_deadline is None


def test_each_closed_to_open_transition_restarts_and_extends_deadline() -> None:
    hass, data = configured_runtime()
    first_open = datetime(2026, 8, 1, tzinfo=timezone.utc)
    hass.states.set("binary_sensor.front_door", "on")

    _update_door_guard_state(
        hass,
        "entry-1",
        data,
        old_state="off",
        new_state="on",
        now=first_open,
    )
    first_deadline = data["door_suppression_until"]
    assert first_deadline == (first_open + timedelta(seconds=180)).isoformat()

    _update_door_guard_state(
        hass,
        "entry-1",
        data,
        old_state="on",
        new_state="on",
        now=first_open + timedelta(seconds=30),
    )
    assert data["door_suppression_until"] == first_deadline

    hass.states.set("binary_sensor.front_door", "off")
    _update_door_guard_state(
        hass,
        "entry-1",
        data,
        old_state="on",
        new_state="off",
        now=first_open + timedelta(seconds=60),
    )
    assert data["door_suppression_until"] == first_deadline

    second_open = first_open + timedelta(seconds=90)
    hass.states.set("binary_sensor.front_door", "on")
    _update_door_guard_state(
        hass,
        "entry-1",
        data,
        old_state="off",
        new_state="on",
        now=second_open,
    )
    assert data["door_suppression_until"] == (
        second_open + timedelta(seconds=180)
    ).isoformat()


def test_zero_cooldown_suppresses_only_while_sensor_is_open() -> None:
    hass, data = configured_runtime(cooldown_seconds=0)
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    hass.states.set("binary_sensor.front_door", "on")

    _update_door_guard_state(
        hass,
        "entry-1",
        data,
        old_state="off",
        new_state="on",
        now=now,
    )

    assert data["door_suppression_until"] is None
    assert data["status"]["approach_suppression_active"] is True

    hass.states.set("binary_sensor.front_door", "off")
    _update_door_guard_state(
        hass,
        "entry-1",
        data,
        old_state="on",
        new_state="off",
        now=now + timedelta(seconds=1),
    )
    assert data["status"]["approach_suppression_active"] is False


def test_expiry_clears_deadline_and_live_status_without_replay() -> None:
    hass, data = configured_runtime()
    deadline = datetime(2026, 8, 1, 0, 3, tzinfo=timezone.utc)
    data["door_suppression_until"] = deadline.isoformat()

    _expire_door_guard(
        hass,
        "entry-1",
        deadline.isoformat(),
        now=deadline,
    )

    assert data["door_suppression_until"] is None
    assert data["status"]["approach_suppression_active"] is False
    assert data["status"]["approach_suppression_until"] is None
    assert all(
        event_type != BUS_EVENT_ANNOUNCEMENT
        for event_type, _event_data in hass.bus.events
    )
