"""Sensor platform for House Chime."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import BUS_EVENT_STATUS_UPDATED, DOMAIN, SIGNAL_STATUS_UPDATED
from .status import (
    SENSOR_DESCRIPTIONS,
    StatusEntityDescription,
    status_native_value,
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    """Set up status sensors."""

    async_add_entities(
        HouseChimeStatusSensor(hass, entry, description)
        for description in SENSOR_DESCRIPTIONS
    )


class HouseChimeStatusSensor(SensorEntity):
    """Status sensor backed by integration runtime state."""

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
        if description.key in {"approach_suppression_until", "approach_wait_until"}:
            self._attr_device_class = SensorDeviceClass.TIMESTAMP

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
    def native_value(self) -> Any:
        return status_native_value(
            self.description.key,
            self._status.get(self.description.key),
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if self.description.key == "selected_target_zones":
            return {"zones": self._status.get("selected_target_zones", [])}
        if self.description.key == "last_failure_reason":
            return {
                "reason_code": self._status.get("last_failure_reason"),
                "last_resolution": self._status.get("last_resolution"),
            }
        if self.description.key == "approach_suppression_until":
            return {
                "active": self._status.get("approach_suppression_active"),
                "sensor_entity_id": self._status.get("door_guard_sensor_entity_id"),
                "sensor_state": self._status.get("door_guard_sensor_state"),
                "suppression_reason": self._status.get("approach_suppression_reason"),
                "warning": self._status.get("door_guard_warning"),
            }
        if self.description.key == "approach_wait_until":
            return {
                "waiting": self._status.get("approach_waiting"),
                "sensor_entity_id": self._status.get(
                    "approach_delay_sensor_entity_id"
                ),
                "sensor_state": self._status.get("approach_delay_sensor_state"),
                "delay_seconds": self._status.get("approach_delay_seconds"),
                "wait_started_at": self._status.get("approach_wait_started_at"),
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
