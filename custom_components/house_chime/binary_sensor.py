"""Binary sensor platform for House Chime."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import BUS_EVENT_STATUS_UPDATED, DOMAIN, SIGNAL_STATUS_UPDATED
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
    _attr_entity_category = EntityCategory.DIAGNOSTIC

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
    def device_info(self) -> dict[str, Any]:
        """Group integration diagnostics under one native Home Assistant device."""

        return {
            "identifiers": {(DOMAIN, self.entry.entry_id)},
            "name": getattr(self.entry, "title", None) or "House Chime",
            "manufacturer": "House Chime",
            "model": "Announcement controller",
        }

    @property
    def is_on(self) -> bool:
        return bool(self._status.get(self.description.key))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if self.description.key == "last_resolution_valid":
            return {"last_resolution": self._status.get("last_resolution")}
        if self.description.key == "approach_suppression_active":
            return {
                "sensor_entity_id": self._status.get("door_guard_sensor_entity_id"),
                "sensor_state": self._status.get("door_guard_sensor_state"),
                "suppression_reason": self._status.get("approach_suppression_reason"),
                "suppression_until": self._status.get("approach_suppression_until"),
                "warning": self._status.get("door_guard_warning"),
            }
        if self.description.key == "approach_waiting":
            return {
                "sensor_entity_id": self._status.get(
                    "approach_delay_sensor_entity_id"
                ),
                "sensor_state": self._status.get("approach_delay_sensor_state"),
                "delay_seconds": self._status.get("approach_delay_seconds"),
                "wait_started_at": self._status.get("approach_wait_started_at"),
                "wait_until": self._status.get("approach_wait_until"),
                "last_cancellation_reason": self._status.get(
                    "last_approach_wait_cancellation_reason"
                ),
                "warning": self._status.get("approach_delay_warning"),
            }
        return {}

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_STATUS_UPDATED,
                self._handle_status_update,
            )
        )
        self.async_on_remove(
            self.hass.bus.async_listen(
                BUS_EVENT_STATUS_UPDATED,
                self._handle_status_event,
            )
        )

    @callback
    def _handle_status_event(self, event) -> None:
        data = getattr(event, "data", {}) or {}
        if data.get("entry_id") in (None, self.entry.entry_id):
            self.async_write_ha_state()

    @callback
    def _handle_status_update(self) -> None:
        self.async_write_ha_state()

    @property
    def _status(self) -> dict[str, Any]:
        return self.hass.data[DOMAIN][self.entry.entry_id]["status"]
