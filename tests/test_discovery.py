from __future__ import annotations

import unittest

from custom_components.house_chime.discovery import (
    discover_device_trackers,
    discover_helpers,
    discover_media_players,
    discover_people,
)


class State:
    def __init__(self, entity_id: str, state: str, name: str | None = None) -> None:
        self.entity_id = entity_id
        self.state = state
        self.attributes = {}
        if name:
            self.attributes["friendly_name"] = name


class DiscoveryTest(unittest.TestCase):
    def test_discovers_relevant_ha_entities(self) -> None:
        states = [
            State("person.david", "home", "David"),
            State("device_tracker.david_phone", "home", "David Phone"),
            State("media_player.great_room", "idle", "Great Room"),
            State("input_boolean.google_package_arrived", "off", "Google package arrived"),
            State("sensor.temperature", "72"),
        ]

        self.assertEqual([item.entity_id for item in discover_people(states)], ["person.david"])
        self.assertEqual(
            [item.entity_id for item in discover_device_trackers(states)],
            ["device_tracker.david_phone"],
        )
        self.assertEqual(
            [item.entity_id for item in discover_media_players(states)],
            ["media_player.great_room"],
        )
        self.assertEqual(
            [item.entity_id for item in discover_helpers(states)],
            ["input_boolean.google_package_arrived"],
        )


if __name__ == "__main__":
    unittest.main()
