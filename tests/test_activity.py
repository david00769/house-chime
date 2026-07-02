from __future__ import annotations

import unittest

from custom_components.house_chime.activity import (
    announcement_event_data,
    fire_announcement_event,
)
from custom_components.house_chime.const import (
    ANNOUNCEMENT_EVENT_PLAYED,
    BUS_EVENT_ANNOUNCEMENT,
)
from custom_components.house_chime.models import AnnouncementResolution


class FakeBus:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def async_fire(self, event_type: str, data: dict) -> None:
        self.events.append((event_type, data))


class FakeHass:
    def __init__(self) -> None:
        self.bus = FakeBus()


class ActivityTest(unittest.TestCase):
    def test_announcement_event_data_uses_single_normalized_shape(self) -> None:
        resolution = AnnouncementResolution(
            event_id="front_door_package",
            ok=True,
            active_context_id="david",
            target_player_entity_ids=["media_player.great_room"],
            quiet_active=True,
        )

        data = announcement_event_data(
            ANNOUNCEMENT_EVENT_PLAYED,
            resolution,
            source="play",
        )

        self.assertEqual(data["type"], "played")
        self.assertEqual(data["event_id"], "front_door_package")
        self.assertEqual(data["active_context_id"], "david")
        self.assertEqual(data["target_player_entity_ids"], ["media_player.great_room"])
        self.assertTrue(data["quiet_active"])

    def test_fire_announcement_event_only_uses_canonical_bus_event(self) -> None:
        hass = FakeHass()
        resolution = AnnouncementResolution(event_id="front_door_package", ok=True)

        fire_announcement_event(
            hass,
            ANNOUNCEMENT_EVENT_PLAYED,
            resolution,
            source="play",
        )

        self.assertEqual(len(hass.bus.events), 1)
        self.assertEqual(hass.bus.events[0][0], BUS_EVENT_ANNOUNCEMENT)


if __name__ == "__main__":
    unittest.main()
