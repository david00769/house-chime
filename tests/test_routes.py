from __future__ import annotations

import unittest
from types import SimpleNamespace

import custom_components.house_chime as house_chime
from custom_components.house_chime.const import CONF_ACTIVE_CONFIG
from custom_components.house_chime.models import (
    AnnouncementConfig,
    AnnouncementResolution,
    PlaybackRouteConfig,
)
from custom_components.house_chime.routes import apply_playback_routes
from conftest import FakeState

ANNOUNCEMENT_FEATURES = 512 | 1048576
SELECT_SOURCE_FEATURE = 2048


class FakeStates:
    def __init__(self, states: list[FakeState]) -> None:
        self._states = {state.entity_id: state for state in states}

    def async_all(self) -> list[FakeState]:
        return list(self._states.values())


class FakeServices:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict, bool]] = []

    async def async_call(
        self,
        domain: str,
        service: str,
        data: dict,
        blocking: bool = False,
        target: dict | None = None,
    ) -> None:
        self.calls.append((domain, service, data, blocking))


class FakeConfigEntries:
    def __init__(self) -> None:
        self.updated_options: dict | None = None

    def async_update_entry(self, entry: SimpleNamespace, *, options: dict) -> None:
        entry.options = options
        self.updated_options = options


def ma_attrs() -> dict:
    return {
        "app_id": "music_assistant",
        "source": "Music Assistant Queue",
        "mass_player_type": "player",
        "supported_features": ANNOUNCEMENT_FEATURES,
    }


def route_zone_attrs(source: str, source_list: list[str] | None = None) -> dict:
    return {
        "source": source,
        "source_list": source_list or ["Main Floor", "Upper Level", "Whole House"],
        "supported_features": SELECT_SOURCE_FEATURE,
    }


def fake_hass(states: list[FakeState], config_entries: FakeConfigEntries | None = None):
    return SimpleNamespace(
        config_entries=config_entries or FakeConfigEntries(),
        services=FakeServices(),
        states=FakeStates(states),
    )


class RoutesTest(unittest.TestCase):
    def test_set_playback_routes_persists_valid_routes(self) -> None:
        config = AnnouncementConfig()
        entry = SimpleNamespace(entry_id="entry-1", options={"keep": True})
        config_entries = FakeConfigEntries()
        hass = fake_hass(
            [
                FakeState("media_player.whole_house", "idle", "Whole House", ma_attrs()),
                FakeState(
                    "media_player.great_room_zone",
                    "on",
                    "Great Room Zone",
                    route_zone_attrs("Main Floor"),
                ),
                FakeState(
                    "media_player.living_room_zone",
                    "on",
                    "Living Room Zone",
                    route_zone_attrs("Main Floor"),
                ),
            ],
            config_entries,
        )
        data = {"entry": entry, "config": config, "status": {}}

        result = house_chime._set_playback_routes(
            hass,
            data,
            [
                {
                    "target_player_entity_id": "media_player.whole_house",
                    "source": "Whole House",
                    "zone_entity_ids": [
                        "media_player.great_room_zone",
                        "media_player.great_room_zone",
                        "media_player.living_room_zone",
                    ],
                }
            ],
        )

        assert result == {
            "ok": True,
            "playback_routes": [
                {
                    "target_player_entity_id": "media_player.whole_house",
                    "source": "Whole House",
                    "zone_entity_ids": [
                        "media_player.great_room_zone",
                        "media_player.living_room_zone",
                    ],
                }
            ],
        }
        assert config_entries.updated_options["keep"] is True
        assert (
            config_entries.updated_options[CONF_ACTIVE_CONFIG]["playback_routes"]
            == result["playback_routes"]
        )

    def test_set_playback_routes_rejects_invalid_source_without_mutating_config(self) -> None:
        existing_route = PlaybackRouteConfig(
            "media_player.whole_house",
            "Whole House",
            ["media_player.great_room_zone"],
        )
        config = AnnouncementConfig(playback_routes=[existing_route])
        entry = SimpleNamespace(entry_id="entry-1", options={})
        config_entries = FakeConfigEntries()
        hass = fake_hass(
            [
                FakeState("media_player.main_floor", "idle", "Main Floor", ma_attrs()),
                FakeState(
                    "media_player.great_room_zone",
                    "on",
                    "Great Room Zone",
                    route_zone_attrs("Main Floor", ["Main Floor"]),
                ),
            ],
            config_entries,
        )
        data = {"entry": entry, "config": config, "status": {}}

        result = house_chime._set_playback_routes(
            hass,
            data,
            [
                {
                    "target_player_entity_id": "media_player.main_floor",
                    "source": "Whole House",
                    "zone_entity_ids": ["media_player.great_room_zone"],
                }
            ],
        )

        assert result == {
            "ok": False,
            "errors": [
                "invalid_route_source:"
                "media_player.main_floor:media_player.great_room_zone:Whole House"
            ],
            "playback_routes": [existing_route.to_dict()],
        }
        assert config.playback_routes == [existing_route]
        assert config_entries.updated_options is None


class ApplyRoutesTest(unittest.IsolatedAsyncioTestCase):
    async def test_apply_playback_routes_selects_sources_for_selected_targets(self) -> None:
        hass = fake_hass(
            [
                FakeState(
                    "media_player.great_room_zone",
                    "on",
                    "Great Room Zone",
                    route_zone_attrs("Main Floor"),
                ),
                FakeState(
                    "media_player.living_room_zone",
                    "on",
                    "Living Room Zone",
                    route_zone_attrs("Whole House"),
                ),
            ]
        )
        config = AnnouncementConfig(
            playback_routes=[
                PlaybackRouteConfig(
                    "media_player.whole_house",
                    "Whole House",
                    [
                        "media_player.great_room_zone",
                        "media_player.living_room_zone",
                    ],
                )
            ]
        )
        resolution = AnnouncementResolution(
            event_id="front_door_doorbell",
            ok=True,
            target_player_entity_ids=["media_player.whole_house"],
        )

        errors = await apply_playback_routes(hass, config, resolution)

        assert errors == []
        assert hass.services.calls == [
            (
                "media_player",
                "select_source",
                {
                    "entity_id": "media_player.great_room_zone",
                    "source": "Whole House",
                },
                True,
            )
        ]

    async def test_apply_playback_routes_reports_unavailable_output_zone(self) -> None:
        hass = fake_hass(
            [
                FakeState(
                    "media_player.great_room_zone",
                    "unavailable",
                    "Great Room Zone",
                    route_zone_attrs("Main Floor"),
                ),
            ]
        )
        config = AnnouncementConfig(
            playback_routes=[
                PlaybackRouteConfig(
                    "media_player.whole_house",
                    "Whole House",
                    ["media_player.great_room_zone"],
                )
            ]
        )
        resolution = AnnouncementResolution(
            event_id="front_door_doorbell",
            ok=True,
            target_player_entity_ids=["media_player.whole_house"],
        )

        errors = await apply_playback_routes(hass, config, resolution)

        assert errors == [
            "invalid_route_zone:"
            "media_player.whole_house:media_player.great_room_zone:unavailable"
        ]
        assert hass.services.calls == []


if __name__ == "__main__":
    unittest.main()
