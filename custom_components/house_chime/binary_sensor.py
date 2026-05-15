"""Binary sensor platform for House Chime."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, SIGNAL_STATUS_UPDATED
from .status import BINARY_SENSOR_DESCRIPTIONS, StatusEntityDescription


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    """Set up status binary sensors."""

    async_add_entities(
        HouseChimeStatusBinarySensor(hass, entry, description)
        for description in BINARY_SENSOR_DESCRIPTIONS
    )


class HouseChimeStatusBinarySensor(BinarySensorEntity):
    """Boolean status sensor backed by integration runtime state."""

    _attr_has_entity_name = True

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        description: StatusEntityDescription,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.description = description
        self._attr_name = description.name
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_icon = description.icon

    @property
    def is_on(self) -> bool:
        return bool(self._status.get(self.description.key))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if self.description.key == "last_resolution_valid":
            return {"last_resolution": self._status.get("last_resolution")}
        return {}

    async def async_added_to_hass(self) -> None:
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

    @property
    def _status(self) -> dict[str, Any]:
        return self.hass.data[DOMAIN][self.entry.entry_id]["status"]
