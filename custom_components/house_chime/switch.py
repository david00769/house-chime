"""Per-person playback controls for House Chime."""

from __future__ import annotations

from typing import Any

try:
    from homeassistant.components.switch import SwitchEntity
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant, callback
    from homeassistant.helpers.dispatcher import async_dispatcher_connect
except (ModuleNotFoundError, ImportError):
    ConfigEntry = Any
    HomeAssistant = Any

    class SwitchEntity:
        """Fallback base for local tests without Home Assistant installed."""

        def async_write_ha_state(self) -> None:
            return None

        def async_on_remove(self, remove_callback):
            self._remove_callback = remove_callback

    def callback(func):
        return func

    def async_dispatcher_connect(*args: Any, **kwargs: Any):
        return lambda: None

from .const import (
    CONF_PERSON_ID,
    CONF_PLAYBACK_ENABLED,
    DOMAIN,
    SIGNAL_STATUS_UPDATED,
)
from .models import PersonConfig

SERVICE_SET_PERSON_PLAYBACK = "set_person_playback"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    """Expose one preference switch for each configured household person."""

    config = hass.data[DOMAIN][entry.entry_id]["config"]
    async_add_entities(
        HouseChimePersonPlaybackSwitch(hass, entry, person) for person in config.people
    )


class HouseChimePersonPlaybackSwitch(SwitchEntity):
    """Persist whether one person wants shared announcements while home."""

    _attr_has_entity_name = False
    _attr_icon = "mdi:volume-high"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, person: PersonConfig) -> None:
        self.hass = hass
        self.entry = entry
        self.person_id = person.id
        self._attr_name = f"House Chime {person.name} playback"
        self._attr_unique_id = f"{entry.entry_id}_{person.id}_playback"

    @property
    def is_on(self) -> bool:
        person = self._person
        return bool(person and person.playback_enabled_when_home)

    async def async_added_to_hass(self) -> None:
        """Refresh the switch when a service changes the persisted preference."""

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_STATUS_UPDATED,
                self._handle_status_update,
            )
        )

    @callback
    def _handle_status_update(self) -> None:
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable this person's shared announcements while home."""

        await self._set_playback_enabled(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable this person's shared announcements while home."""

        await self._set_playback_enabled(False)

    @property
    def _person(self) -> PersonConfig | None:
        config = self.hass.data[DOMAIN][self.entry.entry_id]["config"]
        return next((item for item in config.people if item.id == self.person_id), None)

    async def _set_playback_enabled(self, enabled: bool) -> None:
        await self.hass.services.async_call(
            DOMAIN,
            SERVICE_SET_PERSON_PLAYBACK,
            {
                CONF_PERSON_ID: self.person_id,
                CONF_PLAYBACK_ENABLED: enabled,
            },
            blocking=True,
        )
        self.async_write_ha_state()
