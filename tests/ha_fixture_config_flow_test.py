from __future__ import annotations

import asyncio
from types import SimpleNamespace

from custom_components.house_chime.config_flow import HouseChimeConfigFlow, HouseChimeOptionsFlow
from custom_components.house_chime.const import CONF_ACTIVE_CONFIG, DEFAULT_EVENTS
from custom_components.house_chime.models import AnnouncementConfig
from conftest import FakeState, make_fake_hass


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
    flow = HouseChimeOptionsFlow(entry)
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
            "priority_order": "scarlett, david",
            "default_context_id": "__none__",
            "fallback_trackers": "david=device_tracker.david_phone",
        }
        )
    )

    active_config = result["data"][CONF_ACTIVE_CONFIG]
    assert result["type"] == "create_entry"
    assert [person["id"] for person in active_config["people"]] == ["david", "scarlett"]
    assert active_config["person_priority"] == ["scarlett", "david"]
    assert active_config["people"][0]["fallback_tracker_entity_ids"] == [
        "device_tracker.david_phone"
    ]


def test_options_flow_voice_media_step_persists_local_media_paths() -> None:
    config = AnnouncementConfig()
    entry = SimpleNamespace(data={CONF_ACTIVE_CONFIG: config.to_dict()}, options={})
    flow = HouseChimeOptionsFlow(entry)
    flow.hass = make_fake_hass([])

    result = asyncio.run(
        flow.async_step_voice_media(
        {
            "samantha_front_door_approach_media_path": (
                "media-source://media_source/local/announcements/front-door.mp3"
            ),
            "samantha_front_door_package_media_path": (
                "media-source://media_source/local/announcements/package.mp3"
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
