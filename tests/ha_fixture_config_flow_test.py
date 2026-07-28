from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from custom_components.house_chime.config_flow import HouseChimeConfigFlow, HouseChimeOptionsFlow
from custom_components.house_chime.const import CONF_ACTIVE_CONFIG, DEFAULT_EVENTS
from custom_components.house_chime.models import AnnouncementConfig, PersonConfig, ZoneConfig
from conftest import FakeState, make_fake_hass

ANNOUNCEMENT_FEATURES = 512 | 1048576


def make_options_flow(entry: SimpleNamespace) -> HouseChimeOptionsFlow:
    flow = HouseChimeOptionsFlow()
    flow.config_entry = entry
    return flow


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


def test_config_flow_creates_seeded_house_chime_entry() -> None:
    flow = HouseChimeConfigFlow()

    result = asyncio.run(flow.async_step_user({"name": "House Chime"}))

    assert result["type"] == "create_entry"
    assert result["title"] == "House Chime"
    active_config = result["data"][CONF_ACTIVE_CONFIG]
    assert [voice["id"] for voice in active_config["voices"]] == [
        "eve",
        "leo",
        "pierce",
        "samantha",
    ]
    assert [event["id"] for event in active_config["events"]] == list(DEFAULT_EVENTS)


def test_options_flow_people_step_uses_discovered_people_fixture() -> None:
    entry = SimpleNamespace(data={CONF_ACTIVE_CONFIG: AnnouncementConfig().to_dict()}, options={})
    flow = make_options_flow(entry)
    flow.hass = make_fake_hass(
        [
            FakeState("person.david", "home", "David"),
            FakeState("person.scarlett", "not_home", "Scarlett"),
            FakeState("device_tracker.david_phone", "home", "David Phone"),
        ]
    )

    result = asyncio.run(
        flow.async_step_people(
        {
            "selected_people": ["person.david", "person.scarlett"],
        }
        )
    )

    active_config = result["data"][CONF_ACTIVE_CONFIG]
    assert result["type"] == "create_entry"
    assert [person["id"] for person in active_config["people"]] == ["david", "scarlett"]
    assert active_config["person_priority"] == ["david", "scarlett"]
    assert active_config["people"][0]["fallback_tracker_entity_ids"] == []


def test_options_flow_priority_step_preserves_rank_fields() -> None:
    config = AnnouncementConfig(
        people=[
            PersonConfig(id="david", name="David", entity_id="person.david"),
            PersonConfig(id="scarlett", name="Scarlett", entity_id="person.scarlett"),
        ]
    )
    entry = SimpleNamespace(data={CONF_ACTIVE_CONFIG: config.to_dict()}, options={})
    flow = make_options_flow(entry)
    flow.hass = make_fake_hass([])

    result = asyncio.run(
        flow.async_step_priority(
            {
                "priority_people": ["scarlett", "david"],
                "default_context_id": "david",
            }
        )
    )

    active_config = result["data"][CONF_ACTIVE_CONFIG]
    assert active_config["person_priority"] == ["scarlett", "david"]
    assert active_config["default_context_id"] == "david"


def test_options_flow_init_uses_guided_setup_menu() -> None:
    entry = SimpleNamespace(data={CONF_ACTIVE_CONFIG: AnnouncementConfig().to_dict()}, options={})
    flow = make_options_flow(entry)

    result = asyncio.run(flow.async_step_init())

    assert result["menu_options"] == [
        "people",
        "preferences",
        "personalisation",
        "priority",
        "playback",
        "media",
        "events",
        "quiet",
        "additional",
        "review",
    ]


def test_options_flow_playback_menu_contains_volume_and_second_level_target_controls() -> None:
    entry = SimpleNamespace(data={CONF_ACTIVE_CONFIG: AnnouncementConfig().to_dict()}, options={})
    flow = make_options_flow(entry)

    result = asyncio.run(flow.async_step_playback())

    assert result["menu_options"] == ["zones", "volume", "zone_levels"]


def test_options_flow_volume_step_persists_daytime_level_and_preview() -> None:
    config = AnnouncementConfig()
    entry = SimpleNamespace(data={CONF_ACTIVE_CONFIG: config.to_dict()}, options={})
    flow = make_options_flow(entry)
    flow.hass = make_fake_hass([])

    form = asyncio.run(flow.async_step_volume())
    assert form["step_id"] == "volume"
    assert form["description_placeholders"]["quiet_preview"] == "Daytime 80%; quiet 40%."

    result = asyncio.run(flow.async_step_volume({"normal_volume": 0.6}))
    assert result["data"][CONF_ACTIVE_CONFIG]["normal_volume"] == 0.6


def test_options_flow_zone_level_second_level_persists_multiplier() -> None:
    config = AnnouncementConfig(
        zones=[ZoneConfig("media_player.bedroom", "Bedroom", selected=True)]
    )
    entry = SimpleNamespace(data={CONF_ACTIVE_CONFIG: config.to_dict()}, options={})
    flow = make_options_flow(entry)
    flow.hass = make_fake_hass([])

    selection = asyncio.run(flow.async_step_zone_levels({"entity_id": "media_player.bedroom"}))
    assert selection["step_id"] == "zone_level_detail"
    assert selection["description_placeholders"] == {
        "zone_name": "Bedroom",
        "day_preview": "80%",
        "quiet_preview": "40%",
    }

    result = asyncio.run(flow.async_step_zone_level_detail({"volume_multiplier": 0.5}))
    assert result["data"][CONF_ACTIVE_CONFIG]["zones"][0]["volume_multiplier"] == 0.5


def test_config_flow_options_flow_uses_framework_config_entry_property() -> None:
    entry = SimpleNamespace(data={CONF_ACTIVE_CONFIG: AnnouncementConfig().to_dict()}, options={})
    flow = HouseChimeConfigFlow.async_get_options_flow(entry)
    flow.config_entry = entry

    result = asyncio.run(flow.async_step_init())

    assert isinstance(flow, HouseChimeOptionsFlow)
    assert result["type"] == "menu"


def test_options_flow_does_not_assign_home_assistant_config_entry_property() -> None:
    class FlowWithReadOnlyConfigEntry(HouseChimeOptionsFlow):
        @property
        def config_entry(self):
            return SimpleNamespace(data={}, options={})

    flow = FlowWithReadOnlyConfigEntry()

    assert flow._config().to_dict()["version"] == 3


def test_options_flow_media_step_persists_media_selector_paths() -> None:
    config = AnnouncementConfig()
    entry = SimpleNamespace(data={CONF_ACTIVE_CONFIG: config.to_dict()}, options={})
    flow = make_options_flow(entry)
    flow.hass = make_fake_hass([])

    result = asyncio.run(
        flow.async_step_media(
        {
            "front_door_approach_common_trigger_sound": {
                "media_content_id": "media-source://media_source/local/chimes/doorbell.mp3"
            },
            "samantha_front_door_approach_media_path": (
                {
                    "media_content_id": (
                        "media-source://media_source/local/announcements/front-door.mp3"
                    )
                }
            ),
            "samantha_front_door_package_media_path": (
                {
                    "media_content_id": (
                        "media-source://media_source/local/announcements/package.mp3"
                    )
                }
            ),
        }
        )
    )

    voices = result["data"][CONF_ACTIVE_CONFIG]["voices"]
    samantha = next(voice for voice in voices if voice["id"] == "samantha")
    assert samantha["media_by_event"] == {
        "front_door_approach": "media-source://media_source/local/announcements/front-door.mp3",
        "front_door_package": "media-source://media_source/local/announcements/package.mp3",
    }
    approach = next(
        event for event in result["data"][CONF_ACTIVE_CONFIG]["events"]
        if event["id"] == "front_door_approach"
    )
    assert approach["common_trigger_sound"] == (
        "media-source://media_source/local/chimes/doorbell.mp3"
    )


def test_options_flow_event_step_preserves_personalisation() -> None:
    config = AnnouncementConfig(
        people=[
            PersonConfig(id="david", name="David", entity_id="person.david"),
            PersonConfig(id="scarlett", name="Scarlett", entity_id="person.scarlett"),
        ]
    )
    entry = SimpleNamespace(data={CONF_ACTIVE_CONFIG: config.to_dict()}, options={})
    flow = make_options_flow(entry)
    flow.hass = make_fake_hass([])

    result = asyncio.run(
        flow.async_step_event_front_door_package(
            {
                "enabled": True,
                "default_voice_id": "samantha",
            }
        )
    )

    package = next(
        event for event in result["data"][CONF_ACTIVE_CONFIG]["events"]
        if event["id"] == "front_door_package"
    )
    approach = next(
        event for event in result["data"][CONF_ACTIVE_CONFIG]["events"]
        if event["id"] == "front_door_approach"
    )
    assert package["enabled"] is True
    assert package["default_voice_id"] == "samantha"
    assert package["voice_by_context"] == {}
    assert approach["voice_by_context"] == {}


def test_options_flow_person_preferences_and_personalisation_are_selected_by_person() -> None:
    config = AnnouncementConfig(
        people=[PersonConfig(id="resident", name="Resident", entity_id="person.resident")]
    )
    entry = SimpleNamespace(data={CONF_ACTIVE_CONFIG: config.to_dict()}, options={})
    flow = make_options_flow(entry)
    flow.hass = make_fake_hass([FakeState("device_tracker.resident_phone", "home", "Phone")])

    preference_form = asyncio.run(flow.async_step_preferences({"person_id": "resident"}))
    assert preference_form["step_id"] == "person_preference"
    preference_result = asyncio.run(
        flow.async_step_person_preference(
            {
                "playback_enabled_when_home": False,
                "fallback_tracker_entity_ids": ["device_tracker.resident_phone"],
            }
        )
    )
    person = preference_result["data"][CONF_ACTIVE_CONFIG]["people"][0]
    assert person["playback_enabled_when_home"] is False
    assert person["fallback_tracker_entity_ids"] == ["device_tracker.resident_phone"]

    personalisation_form = asyncio.run(
        flow.async_step_personalisation(
            {"person_id": "resident", "event_id": "front_door_package"}
        )
    )
    assert personalisation_form["step_id"] == "personalisation_detail"
    personalisation_result = asyncio.run(
        flow.async_step_personalisation_detail(
            {
                "voice_id": "pierce",
                "trigger_sound": {
                    "media_content_id": "media-source://media_source/local/chimes/package.mp3"
                },
            }
        )
    )
    package = next(
        event
        for event in personalisation_result["data"][CONF_ACTIVE_CONFIG]["events"]
        if event["id"] == "front_door_package"
    )
    assert package["voice_by_context"] == {"resident": "pierce"}
    assert package["trigger_sound_by_context"] == {
        "resident": "media-source://media_source/local/chimes/package.mp3"
    }


def test_options_flow_quiet_step_persists_bedtime_zone_rules() -> None:
    config = AnnouncementConfig()
    config.quiet.excluded_zone_entity_ids = ["media_player.bedroom"]
    config.quiet.zone_start = "21:00"
    config.quiet.zone_end = "07:00"
    entry = SimpleNamespace(data={CONF_ACTIVE_CONFIG: config.to_dict()}, options={})
    flow = make_options_flow(entry)
    flow.hass = make_fake_hass(
        [
            FakeState(
                "media_player.bedroom",
                "idle",
                "Bedroom",
                ma_attrs(),
            )
        ]
    )

    result = asyncio.run(
        flow.async_step_quiet(
            {
                "enabled": True,
                "start": "22:00",
                "end": "08:00",
                "volume_multiplier": 0.5,
                "quiet_excluded_zones": ["media_player.bedroom"],
                "zone_start": "21:00",
                "zone_end": "07:00",
            }
        )
    )

    quiet = result["data"][CONF_ACTIVE_CONFIG]["quiet"]
    assert quiet["enabled"] is True
    assert quiet["excluded_zone_entity_ids"] == ["media_player.bedroom"]
    assert quiet["zone_start"] == "21:00"


def test_options_flow_zones_shows_available_juke_airplay2_music_assistant_targets() -> None:
    entry = SimpleNamespace(data={CONF_ACTIVE_CONFIG: AnnouncementConfig().to_dict()}, options={})
    flow = make_options_flow(entry)
    flow.hass = make_fake_hass(
        [
            FakeState(
                "media_player.main_floor_2",
                "idle",
                "Main Floor",
                ma_attrs(),
            ),
            FakeState(
                "media_player.upper_level_airplay",
                "idle",
                "Upper Level",
                ma_attrs(),
            ),
            FakeState(
                "media_player.whole_house",
                "idle",
                "Whole House (AirPlay)",
                ma_attrs(),
            ),
            FakeState(
                "media_player.master",
                "idle",
                "Master Bedroom (AirPlay)",
                ma_attrs(),
            ),
            FakeState(
                "media_player.main_floor_airplay",
                "unavailable",
                "Main Floor (AirPlay)",
                ma_attrs(),
            ),
            FakeState(
                "media_player.sugarloaf_juke_main_floor_input",
                "on",
                "Sugarloaf Juke Main Floor Input",
                {
                    "device_class": "receiver",
                    "source": "Airplay2",
                    "supported_features": 2432,
                },
            ),
        ]
    )

    result = asyncio.run(flow.async_step_zones())
    selected_field = next(iter(result["data_schema"].schema.values()))
    options = selected_field.config.kwargs["options"]

    assert [option["value"] for option in options] == [
        "media_player.main_floor_2",
        "media_player.master",
        "media_player.upper_level_airplay",
        "media_player.whole_house",
    ]
    assert result["description_placeholders"] == {
        "recommended_count": "4",
        "total_count": "6",
        "missing_selected_zones": "None.",
        "suggested_replacements": "None.",
    }


def test_options_flow_zones_labels_include_entity_ids() -> None:
    entry = SimpleNamespace(data={CONF_ACTIVE_CONFIG: AnnouncementConfig().to_dict()}, options={})
    flow = make_options_flow(entry)
    flow.hass = make_fake_hass(
        [
            FakeState(
                "media_player.whole_house",
                "idle",
                "Whole House",
                ma_attrs(),
            ),
            FakeState(
                "media_player.whole_house_airplay",
                "idle",
                "Whole House",
                ma_attrs(),
            ),
        ]
    )

    result = asyncio.run(flow.async_step_zones())
    selected_field = next(iter(result["data_schema"].schema.values()))
    options = selected_field.config.kwargs["options"]

    assert [option["label"] for option in options] == [
        "Whole House (media_player.whole_house)",
        "Whole House (media_player.whole_house_airplay)",
    ]


def test_options_flow_zones_surfaces_missing_selected_speaker_suggestions() -> None:
    config = AnnouncementConfig(
        zones=[
            ZoneConfig(
                entity_id="media_player.whole_house",
                name="Whole House",
                selected=True,
            ),
            ZoneConfig(
                entity_id="media_player.great_room",
                name="Great Room",
                selected=True,
            ),
        ],
    )
    entry = SimpleNamespace(data={CONF_ACTIVE_CONFIG: config.to_dict()}, options={})
    flow = make_options_flow(entry)
    flow.hass = make_fake_hass(
        [
            FakeState(
                "media_player.great_room",
                "idle",
                "Great Room",
                ma_attrs({"mass_player_id": "great_room"}),
            ),
            FakeState(
                "media_player.living_room_3",
                "idle",
                "Whole House",
                ma_attrs({"mass_player_id": "living_room_3"}),
            ),
        ]
    )

    result = asyncio.run(flow.async_step_zones())
    selected_field_marker = next(iter(result["data_schema"].schema.keys()))

    assert selected_field_marker.default() == [
        "media_player.great_room",
    ]
    assert result["description_placeholders"]["missing_selected_zones"] == (
        "Whole House (media_player.whole_house)"
    )
    assert result["description_placeholders"]["suggested_replacements"] == (
        "Whole House (media_player.whole_house) -> "
        "Whole House (media_player.living_room_3)"
    )


def test_options_flow_zones_does_not_offer_unavailable_saved_speakers() -> None:
    config = AnnouncementConfig(
        zones=[
            ZoneConfig(
                entity_id="media_player.main_floor_airplay",
                name="Main Floor (AirPlay)",
                selected=True,
            ),
        ],
    )
    entry = SimpleNamespace(data={CONF_ACTIVE_CONFIG: config.to_dict()}, options={})
    flow = make_options_flow(entry)
    flow.hass = make_fake_hass(
        [
            FakeState(
                "media_player.main_floor_airplay",
                "unavailable",
                "Main Floor (AirPlay)",
                ma_attrs(),
            ),
            FakeState(
                "media_player.main_floor_2",
                "idle",
                "Main Floor",
                ma_attrs(),
            ),
        ]
    )

    result = asyncio.run(flow.async_step_zones())
    selected_field_marker = next(iter(result["data_schema"].schema.keys()))
    selected_field = next(iter(result["data_schema"].schema.values()))
    options = selected_field.config.kwargs["options"]

    assert selected_field_marker.default() == []
    assert [option["value"] for option in options] == ["media_player.main_floor_2"]
    assert result["description_placeholders"]["missing_selected_zones"] == (
        "Main Floor (AirPlay) (media_player.main_floor_airplay)"
    )
    assert result["description_placeholders"]["suggested_replacements"] == (
        "Main Floor (AirPlay) (media_player.main_floor_airplay) -> "
        "Main Floor (media_player.main_floor_2)"
    )


def test_options_flow_zones_all_alias_uses_single_speakers_form() -> None:
    entry = SimpleNamespace(data={CONF_ACTIVE_CONFIG: AnnouncementConfig().to_dict()}, options={})
    flow = make_options_flow(entry)
    flow.hass = make_fake_hass(
        [
            FakeState("media_player.main_floor_2", "idle", "Main Floor", ma_attrs()),
            FakeState("media_player.radio", "unavailable", "Radio", ma_attrs()),
        ]
    )

    result = asyncio.run(flow.async_step_zones_all())
    selected_field = next(iter(result["data_schema"].schema.values()))

    assert result["step_id"] == "zones"
    assert [option["value"] for option in selected_field.config.kwargs["options"]] == [
        "media_player.main_floor_2"
    ]


def test_options_flow_zones_filters_to_compatible_targets_and_keeps_bedtime_controls_out_of_advanced() -> None:
    entry = SimpleNamespace(data={CONF_ACTIVE_CONFIG: AnnouncementConfig().to_dict()}, options={})
    flow = make_options_flow(entry)
    flow.hass = make_fake_hass(
        [
            FakeState("media_player.tv", "idle", "TV"),
            FakeState("media_player.radio", "unavailable", "Radio", ma_attrs()),
            FakeState("media_player.main_floor_2", "idle", "Main Floor", ma_attrs()),
        ]
    )

    zones_result = asyncio.run(flow.async_step_zones())
    zones_field = next(iter(zones_result["data_schema"].schema.values()))
    assert [option["value"] for option in zones_field.config.kwargs["options"]] == [
        "media_player.main_floor_2"
    ]
    assert zones_result["description_placeholders"] == {
        "recommended_count": "1",
        "total_count": "3",
        "missing_selected_zones": "None.",
        "suggested_replacements": "None.",
    }

    additional_result = asyncio.run(flow.async_step_additional())
    additional_fields = {
        getattr(field, "schema", field): validator
        for field, validator in additional_result["data_schema"].schema.items()
    }
    assert "selected_zones_all" not in additional_fields
    assert "quiet_excluded_zones" not in additional_fields


def test_options_flow_additional_persists_duplicate_windows_without_changing_quiet_rules() -> None:
    config = AnnouncementConfig(
        people=[PersonConfig(id="david", name="David", entity_id="person.david")],
        zones=[ZoneConfig(entity_id="media_player.great_room", name="Great Room", selected=True)],
    )
    entry = SimpleNamespace(data={CONF_ACTIVE_CONFIG: config.to_dict()}, options={})
    flow = make_options_flow(entry)
    flow.hass = make_fake_hass(
        [
            FakeState("device_tracker.david_phone", "home", "David Phone"),
            FakeState(
                "media_player.great_room",
                "idle",
                "Great Room",
                ma_attrs({"mass_player_id": "great_room"}),
            ),
        ]
    )

    result = asyncio.run(
        flow.async_step_additional(
            {
                "front_door_approach_duplicate_window_seconds": 45,
                "front_door_package_duplicate_window_seconds": 60,
                "front_door_doorbell_duplicate_window_seconds": 45,
            }
        )
    )

    active_config = result["data"][CONF_ACTIVE_CONFIG]
    assert active_config["quiet"]["excluded_zone_entity_ids"] == []
    assert active_config["quiet"]["zone_start"] is None
    package = next(event for event in active_config["events"] if event["id"] == "front_door_package")
    assert "bridge_helper_entity_id" not in package
    assert package["duplicate_window_seconds"] == 60


def test_options_flow_review_reports_non_audible_setup_status() -> None:
    config = AnnouncementConfig(
        people=[PersonConfig(id="david", name="David", entity_id="person.david")],
        person_priority=["david"],
    )
    entry = SimpleNamespace(data={CONF_ACTIVE_CONFIG: config.to_dict()}, options={})
    flow = make_options_flow(entry)
    flow.hass = make_fake_hass([FakeState("person.david", "home", "David")])

    result = asyncio.run(flow.async_step_review())

    assert result["type"] == "form"
    assert result["step_id"] == "review"
    assert "Approach: needs setup" in result["description_placeholders"]["summary"]
    assert "missing_media_mapping" in result["description_placeholders"]["summary"]


def test_default_translated_labels_do_not_expose_raw_setup_keys() -> None:
    translations = json.loads(
        Path("custom_components/house_chime/translations/en.json").read_text()
    )
    labels = []

    def collect_strings(value):
        if isinstance(value, dict):
            for item in value.values():
                collect_strings(item)
        elif isinstance(value, list):
            for item in value:
                collect_strings(item)
        elif isinstance(value, str):
            labels.append(value)

    collect_strings(translations["options"]["step"])

    forbidden = ("front_door_", "_media_path", "priority_order", "fallback_trackers")
    assert not [
        label for label in labels
        if any(raw in label for raw in forbidden)
    ]
    assert "Speakers (Music Assistant)" not in labels
    assert "Speakers (Compatible targets)" not in labels
    assert "Compatible announcement speakers" not in labels
