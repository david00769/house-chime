from __future__ import annotations

import unittest

from custom_components.house_chime.condition import (
    EventCanResolveCondition,
    EventEnabledCondition,
    QuietModeCondition,
    ReadyCondition,
)
from custom_components.house_chime.const import CONF_EVENT_ID, DOMAIN
from custom_components.house_chime.models import (
    AnnouncementConfig,
    EventConfig,
    PersonConfig,
    VoicePersonality,
    ZoneConfig,
)
from custom_components.house_chime.storage import migrate_config_dict
from conftest import FakeState, make_fake_hass


def configured_hass(config: AnnouncementConfig, states: list[FakeState], status: dict):
    hass = make_fake_hass(states)
    config_dict, _ = migrate_config_dict(config.to_dict())
    hass.data = {
        DOMAIN: {
            "entry": {
                "config": AnnouncementConfig.from_dict(config_dict),
                "status": status,
                "last_triggered_by_event": {},
            }
        }
    }
    return hass


class ConditionTest(unittest.TestCase):
    def test_ready_condition_uses_integration_status(self) -> None:
        hass = configured_hass(AnnouncementConfig(), [], {"integration_ready": True})

        condition = ReadyCondition(hass, {"options": {}})

        self.assertTrue(condition.async_check())

    def test_event_enabled_condition_reads_configured_event(self) -> None:
        hass = configured_hass(
            AnnouncementConfig(
                events=[
                    EventConfig(
                        id="front_door_package",
                        name="Package",
                        enabled=False,
                    )
                ]
            ),
            [],
            {},
        )

        condition = EventEnabledCondition(
            hass,
            {"options": {CONF_EVENT_ID: "front_door_package"}},
        )

        self.assertFalse(condition.async_check())

    def test_event_can_resolve_condition_uses_resolver_without_playing(self) -> None:
        config = AnnouncementConfig(
            people=[PersonConfig(id="david", name="David", entity_id="person.david")],
            person_priority=["david"],
            zones=[ZoneConfig(entity_id="media_player.great_room", selected=True)],
            voices=[
                VoicePersonality(
                    id="samantha",
                    name="Samantha",
                    source="chatterbox",
                    media_by_event={
                        "front_door_package": "media-source://media_source/local/package.mp3"
                    },
                )
            ],
            events=[
                EventConfig(
                    id="front_door_package",
                    name="Package",
                    default_voice_id="samantha",
                )
            ],
        )
        hass = configured_hass(
            config,
            [
                FakeState("person.david", "home", "David"),
                FakeState("media_player.great_room", "idle", "Great Room"),
            ],
            {},
        )

        condition = EventCanResolveCondition(
            hass,
            {"options": {CONF_EVENT_ID: "front_door_package"}},
        )

        self.assertTrue(condition.async_check())

    def test_quiet_mode_condition_matches_requested_state(self) -> None:
        hass = configured_hass(AnnouncementConfig(), [], {"quiet_mode_active": False})

        condition = QuietModeCondition(hass, {"options": {"state": "inactive"}})

        self.assertTrue(condition.async_check())


if __name__ == "__main__":
    unittest.main()
