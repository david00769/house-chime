from __future__ import annotations

import asyncio
from types import SimpleNamespace
import unittest

from custom_components.house_chime.const import (
    ANNOUNCEMENT_EVENT_PLAYED,
    BUS_EVENT_ANNOUNCEMENT,
)
from custom_components.house_chime.event import HouseChimeAnnouncementEvent


class FakeBus:
    def __init__(self) -> None:
        self.listeners: dict[str, list] = {}

    def async_listen(self, event_type: str, callback):
        self.listeners.setdefault(event_type, []).append(callback)
        return lambda: self.listeners[event_type].remove(callback)

    def fire(self, event_type: str, data: dict) -> None:
        for callback in list(self.listeners.get(event_type, [])):
            callback(SimpleNamespace(data=data))


class EventEntityTest(unittest.TestCase):
    def test_event_entity_records_normalized_announcement_activity(self) -> None:
        hass = SimpleNamespace(bus=FakeBus())
        entry = SimpleNamespace(entry_id="entry")
        entity = HouseChimeAnnouncementEvent(hass, entry)

        asyncio.run(entity.async_added_to_hass())
        hass.bus.fire(
            BUS_EVENT_ANNOUNCEMENT,
            {
                "type": ANNOUNCEMENT_EVENT_PLAYED,
                "event_id": "front_door_package",
                "source": "play",
            },
        )

        self.assertEqual(entity._last_event_type, ANNOUNCEMENT_EVENT_PLAYED)
        self.assertEqual(entity._last_event_data["event_id"], "front_door_package")
        self.assertNotIn("type", entity._last_event_data)


if __name__ == "__main__":
    unittest.main()
