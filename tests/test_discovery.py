from __future__ import annotations

import unittest

from custom_components.house_chime.discovery import (
    discover_device_trackers,
    discover_helpers,
    discover_media_players,
    discover_people,
    is_music_assistant_announcement_player,
    is_recommended_media_player,
)


class State:
    def __init__(
        self,
        entity_id: str,
        state: str,
        name: str | None = None,
        attributes: dict | None = None,
    ) -> None:
        self.entity_id = entity_id
        self.state = state
        self.attributes = dict(attributes or {})
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

    def test_ranks_music_assistant_announcement_players_first(self) -> None:
        states = [
            State(
                "media_player.tv",
                "idle",
                "TV",
                {
                    "app_id": "music_assistant",
                    "source": "Music Assistant Queue",
                    "mass_player_type": "player",
                },
            ),
            State("media_player.juke_great_room", "idle", "Juke Great Room"),
            State(
                "media_player.great_room",
                "idle",
                "Great Room",
                {"app_id": "music_assistant", "source": "Music Assistant Queue"},
            ),
        ]

        players = discover_media_players(states)

        self.assertEqual(
            [item.entity_id for item in players],
            [
                "media_player.juke_great_room",
                "media_player.great_room",
                "media_player.tv",
            ],
        )
        self.assertTrue(is_recommended_media_player(players[0]))
        self.assertTrue(is_music_assistant_announcement_player(players[0]))
        self.assertFalse(is_recommended_media_player(players[1]))
        self.assertFalse(is_recommended_media_player(players[2]))

    def test_generic_music_assistant_metadata_is_not_recommended(self) -> None:
        player = discover_media_players(
            [
                State(
                    "media_player.bathroom_homepod_2",
                    "idle",
                    "Bathroom HomePod",
                    {
                        "app_id": "music_assistant",
                        "source": "Music Assistant Queue",
                        "mass_player_type": "player",
                    },
                )
            ]
        )[0]

        self.assertFalse(is_recommended_media_player(player))
        self.assertFalse(is_music_assistant_announcement_player(player))


if __name__ == "__main__":
    unittest.main()
