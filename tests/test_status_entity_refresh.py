from __future__ import annotations

from types import SimpleNamespace

import custom_components.house_chime as house_chime
from custom_components.house_chime.binary_sensor import HouseChimeStatusBinarySensor
from custom_components.house_chime.const import BUS_EVENT_STATUS_UPDATED, CONF_ACTIVE_CONFIG, DOMAIN
from custom_components.house_chime.models import AnnouncementConfig, AnnouncementResolution, ZoneConfig
from custom_components.house_chime.sensor import HouseChimeStatusSensor
from custom_components.house_chime.status import BINARY_SENSOR_DESCRIPTIONS, SENSOR_DESCRIPTIONS
from conftest import FakeState


ANNOUNCEMENT_FEATURES = 512 | 1048576


class FakeBus:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def async_fire(self, event_type: str, data: dict) -> None:
        self.events.append((event_type, data))


class FakeServices:
    def has_service(self, domain: str, service: str) -> bool:
        return (domain, service) == ("music_assistant", "play_announcement")


class FakeStates:
    def __init__(self, states: list[FakeState]) -> None:
        self._states = states

    def async_all(self) -> list[FakeState]:
        return list(self._states)


class FakeConfigEntries:
    def __init__(self) -> None:
        self.updated_options: dict | None = None

    def async_update_entry(self, entry: SimpleNamespace, *, options: dict) -> None:
        entry.options = options
        self.updated_options = options


def ma_attrs(extra: dict | None = None) -> dict:
    attributes = {
        "app_id": "music_assistant",
        "source": "Music Assistant Queue",
        "mass_player_type": "player",
        "supported_features": ANNOUNCEMENT_FEATURES,
    }
    if extra:
        attributes.update(extra)
    return attributes


def test_record_and_publish_status_fires_entry_scoped_bus_event() -> None:
    status = {}
    entry_data = {"status": status}
    hass = SimpleNamespace(
        bus=FakeBus(),
        data={DOMAIN: {"entry-1": entry_data}},
        services=FakeServices(),
    )
    resolution = AnnouncementResolution(
        event_id="front_door_doorbell",
        ok=True,
        media_path="media-source://media_source/local/announcements/doorbell.mp3",
        target_player_entity_ids=["media_player.whole_house"],
    )

    house_chime._record_and_publish_status(hass, entry_data, resolution, outcome="played")

    assert status["last_played_event"] == "front_door_doorbell"
    assert hass.bus.events == [(BUS_EVENT_STATUS_UPDATED, {"entry_id": "entry-1"})]


def test_status_sensor_repaints_for_matching_bus_event() -> None:
    entry = SimpleNamespace(entry_id="entry-1")
    hass = SimpleNamespace(data={DOMAIN: {"entry-1": {"status": {}}}})
    entity = HouseChimeStatusSensor(hass, entry, SENSOR_DESCRIPTIONS[0])
    calls = []
    entity.async_write_ha_state = lambda: calls.append("write")

    entity._handle_status_event(SimpleNamespace(data={"entry_id": "entry-1"}))
    entity._handle_status_event(SimpleNamespace(data={"entry_id": "other"}))

    assert calls == ["write"]


def test_status_binary_sensor_repaints_for_matching_bus_event() -> None:
    entry = SimpleNamespace(entry_id="entry-1")
    hass = SimpleNamespace(data={DOMAIN: {"entry-1": {"status": {}}}})
    entity = HouseChimeStatusBinarySensor(hass, entry, BINARY_SENSOR_DESCRIPTIONS[0])
    calls = []
    entity.async_write_ha_state = lambda: calls.append("write")

    entity._handle_status_event(SimpleNamespace(data={"entry_id": "entry-1"}))
    entity._handle_status_event(SimpleNamespace(data={"entry_id": "other"}))

    assert calls == ["write"]


def test_set_selected_speakers_persists_compatible_music_assistant_targets() -> None:
    entry = SimpleNamespace(entry_id="entry-1", options={"keep": True})
    config = AnnouncementConfig(
        zones=[
            ZoneConfig("media_player.whole_house", "Whole House", selected=True),
            ZoneConfig("media_player.main_floor_2", "Main Floor", quiet_excluded=True),
        ]
    )
    config_entries = FakeConfigEntries()
    hass = SimpleNamespace(
        config_entries=config_entries,
        states=FakeStates(
            [
                FakeState("media_player.main_floor_2", "idle", "Main Floor", ma_attrs()),
                FakeState("media_player.upper_level_airplay", "idle", "Upper Level", ma_attrs()),
                FakeState("media_player.whole_house", "idle", "Whole House", ma_attrs()),
                FakeState("media_player.raw_juke_input", "on", "Raw Juke", {"supported_features": 2432}),
            ]
        ),
    )
    data = {
        "entry": entry,
        "config": config,
        "status": {"selected_target_zones": ["media_player.whole_house"]},
    }

    result = house_chime._set_selected_speakers(
        hass,
        data,
        ["media_player.main_floor_2", "media_player.upper_level_airplay"],
    )

    assert result["ok"] is True
    assert result["selected_target_zones"] == [
        "media_player.main_floor_2",
        "media_player.upper_level_airplay",
    ]
    assert data["status"]["selected_target_zones"] == result["selected_target_zones"]
    assert config_entries.updated_options["keep"] is True
    persisted_zones = config_entries.updated_options[CONF_ACTIVE_CONFIG]["zones"]
    assert [
        zone["entity_id"] for zone in persisted_zones if zone["selected"]
    ] == result["selected_target_zones"]
    assert next(
        zone for zone in persisted_zones if zone["entity_id"] == "media_player.main_floor_2"
    )["quiet_excluded"] is True


def test_set_selected_speakers_rejects_incompatible_targets_without_mutating_config() -> None:
    entry = SimpleNamespace(entry_id="entry-1", options={})
    config = AnnouncementConfig(
        zones=[ZoneConfig("media_player.whole_house", "Whole House", selected=True)]
    )
    config_entries = FakeConfigEntries()
    hass = SimpleNamespace(
        config_entries=config_entries,
        states=FakeStates(
            [
                FakeState("media_player.whole_house", "idle", "Whole House", ma_attrs()),
                FakeState("media_player.main_floor_airplay", "unavailable", "Main Floor", ma_attrs()),
            ]
        ),
    )
    data = {
        "entry": entry,
        "config": config,
        "status": {"selected_target_zones": ["media_player.whole_house"]},
    }

    result = house_chime._set_selected_speakers(
        hass,
        data,
        ["media_player.main_floor_airplay"],
    )

    assert result == {
        "ok": False,
        "errors": ["incompatible_speaker:media_player.main_floor_airplay"],
        "selected_target_zones": ["media_player.whole_house"],
        "available_target_entity_ids": ["media_player.whole_house"],
    }
    assert [zone.entity_id for zone in config.zones if zone.selected] == [
        "media_player.whole_house"
    ]
    assert config_entries.updated_options is None
