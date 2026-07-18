from __future__ import annotations

from types import SimpleNamespace
import unittest

from custom_components.house_chime import _set_person_playback
from custom_components.house_chime.models import AnnouncementConfig, PersonConfig


class FakeConfigEntries:
    def __init__(self) -> None:
        self.updated_options = None

    def async_update_entry(self, entry, *, options) -> None:
        self.updated_options = options
        entry.options = options


class PersonPlaybackServiceTest(unittest.TestCase):
    def test_updates_and_persists_a_configured_person_preference(self) -> None:
        entry = SimpleNamespace(options={})
        hass = SimpleNamespace(config_entries=FakeConfigEntries())
        config = AnnouncementConfig(
            people=[PersonConfig(id="resident", name="Resident", entity_id="person.resident")]
        )
        data = {"entry": entry, "config": config}

        result = _set_person_playback(hass, data, "resident", False)

        self.assertEqual(
            result,
            {"ok": True, "person_id": "resident", "playback_enabled": False},
        )
        self.assertFalse(config.people[0].playback_enabled_when_home)
        self.assertFalse(
            hass.config_entries.updated_options["active_config"]["people"][0][
                "playback_enabled_when_home"
            ]
        )

    def test_rejects_an_unknown_person_without_persisting(self) -> None:
        hass = SimpleNamespace(config_entries=FakeConfigEntries())
        data = {
            "entry": SimpleNamespace(options={}),
            "config": AnnouncementConfig(),
        }

        result = _set_person_playback(hass, data, "unknown", False)

        self.assertEqual(result, {"ok": False, "errors": ["unknown_person:unknown"]})
        self.assertIsNone(hass.config_entries.updated_options)


if __name__ == "__main__":
    unittest.main()
