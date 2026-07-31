"""Event platform for House Chime Activity entries."""

from __future__ import annotations

from typing import Any

try:
    from homeassistant.components.event import EventEntity
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant, callback
except (ModuleNotFoundError, ImportError):
    ConfigEntry = Any
    HomeAssistant = Any

    class EventEntity:
        """Fallback base for local tests without Home Assistant installed."""

        def async_on_remove(self, remove_callback):
            self._remove_callback = remove_callback

        def _trigger_event(self, event_type: str, event_data: dict[str, Any] | None = None) -> None:
            self._last_event_type = event_type
            self._last_event_data = event_data or {}

        def async_write_ha_state(self) -> None:
            return None

    def callback(func):
        return func

from .const import ANNOUNCEMENT_EVENT_TYPES, BUS_EVENT_ANNOUNCEMENT


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    """Set up the House Chime event entity."""

    async_add_entities([HouseChimeAnnouncementEvent(hass, entry)])


class HouseChimeAnnouncementEvent(EventEntity):
    """Event entity that records House Chime announcement activity."""

    _attr_has_entity_name = False
    _attr_name = "House Chime Announcement activity"
    _attr_icon = "mdi:bell-ring"
    _attr_event_types = list(ANNOUNCEMENT_EVENT_TYPES)

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_announcement_activity"

    async def async_added_to_hass(self) -> None:
        """Subscribe to normalized House Chime events."""

        remove = self.hass.bus.async_listen(BUS_EVENT_ANNOUNCEMENT, self._handle_event)
        if hasattr(self, "async_on_remove"):
            self.async_on_remove(remove)

    @callback
    def _handle_event(self, event) -> None:
        """Record one normalized House Chime event."""

        data = dict(getattr(event, "data", {}) or {})
        event_type = data.get("type")
        if event_type not in ANNOUNCEMENT_EVENT_TYPES:
            return
        event_data = {key: value for key, value in data.items() if key != "type"}
        self._trigger_event(event_type, event_data)
        self.async_write_ha_state()
