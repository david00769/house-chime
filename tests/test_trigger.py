from __future__ import annotations

import asyncio
from types import SimpleNamespace
import unittest

from custom_components.house_chime.const import (
    ANNOUNCEMENT_EVENT_PLAYED,
    BUS_EVENT_ANNOUNCEMENT,
    CONF_EVENT_ID,
    CONF_EVENT_TYPE,
)
from custom_components.house_chime.trigger import AnnouncementActivityTrigger


class FakeBus:
    def __init__(self) -> None:
        self.listeners: dict[str, list] = {}

    def async_listen(self, event_type: str, callback):
        self.listeners.setdefault(event_type, []).append(callback)

        def remove() -> None:
            self.listeners[event_type].remove(callback)

        return remove

    def fire(self, event_type: str, data: dict) -> None:
        for callback in list(self.listeners.get(event_type, [])):
            callback(SimpleNamespace(data=data))


class FakeHass:
    def __init__(self) -> None:
        self.bus = FakeBus()


class TriggerTest(unittest.TestCase):
    def test_announcement_activity_trigger_filters_type_and_event(self) -> None:
        hass = FakeHass()
        trigger = AnnouncementActivityTrigger(
            hass,
            {
                "options": {
                    CONF_EVENT_TYPE: ANNOUNCEMENT_EVENT_PLAYED,
                    CONF_EVENT_ID: "front_door_package",
                }
            },
        )
        calls = []

        async def attach():
            return await trigger.async_attach_runner(
                lambda payload, description: calls.append((payload, description))
            )

        remove = asyncio.run(attach())

        hass.bus.fire(
            BUS_EVENT_ANNOUNCEMENT,
            {"type": "play_failed", "event_id": "front_door_package"},
        )
        hass.bus.fire(
            BUS_EVENT_ANNOUNCEMENT,
            {"type": ANNOUNCEMENT_EVENT_PLAYED, "event_id": "front_door_approach"},
        )
        hass.bus.fire(
            BUS_EVENT_ANNOUNCEMENT,
            {"type": ANNOUNCEMENT_EVENT_PLAYED, "event_id": "front_door_package"},
        )
        remove()

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0]["event_id"], "front_door_package")
        self.assertEqual(
            calls[0][1],
            "House Chime played for front_door_package",
        )


if __name__ == "__main__":
    unittest.main()
