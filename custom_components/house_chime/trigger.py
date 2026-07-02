"""Purpose-specific automation triggers for House Chime activity."""

from __future__ import annotations

from typing import Any

try:
    from homeassistant.const import CONF_OPTIONS
    from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
    from homeassistant.helpers import config_validation as cv
    from homeassistant.helpers.trigger import Trigger, TriggerActionRunner, TriggerConfig
    from homeassistant.helpers.typing import ConfigType
    import voluptuous as vol
except (ModuleNotFoundError, ImportError):
    CONF_OPTIONS = "options"
    CALLBACK_TYPE = Any
    HomeAssistant = Any
    TriggerActionRunner = Any
    TriggerConfig = dict[str, Any]
    ConfigType = dict[str, Any]

    def callback(func):
        return func

    class Trigger:
        """Fallback base for local tests without Home Assistant installed."""

        def __init__(self, hass: Any, config: Any) -> None:
            self.hass = hass
            self.config = config

    class _Cv:
        string = str

    cv = _Cv()

    class _Vol:
        @staticmethod
        def Schema(schema):
            return lambda value: value

        @staticmethod
        def Optional(key, default=None):
            return key

        @staticmethod
        def In(values):
            return lambda value: value if value in values else value

    vol = _Vol()

from .const import (
    ANNOUNCEMENT_EVENT_TYPES,
    BUS_EVENT_ANNOUNCEMENT,
    CONF_EVENT_ID,
    CONF_EVENT_TYPE,
)

TRIGGER_ANNOUNCEMENT_ACTIVITY = "announcement_activity"

_TRIGGER_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_EVENT_TYPE): vol.In(ANNOUNCEMENT_EVENT_TYPES),
        vol.Optional(CONF_EVENT_ID): cv.string,
    }
)


async def async_get_triggers(hass: HomeAssistant) -> dict[str, type[Trigger]]:
    """Return triggers provided by House Chime."""

    return {TRIGGER_ANNOUNCEMENT_ACTIVITY: AnnouncementActivityTrigger}


class AnnouncementActivityTrigger(Trigger):
    """Trigger when House Chime records announcement activity."""

    @classmethod
    async def async_validate_config(cls, hass: HomeAssistant, config: ConfigType) -> ConfigType:
        """Validate trigger config and keep options normalized."""

        normalized = dict(config)
        options = _trigger_options(normalized)
        normalized[CONF_OPTIONS] = _TRIGGER_SCHEMA(options)
        return normalized

    def __init__(self, hass: HomeAssistant, config: TriggerConfig) -> None:
        try:
            super().__init__(hass, config)
        except TypeError:
            super().__init__()
            self.hass = hass
        self.config = config
        self.options = _trigger_options(config)
        self._event_type = self.options.get(CONF_EVENT_TYPE)
        self._event_id = self.options.get(CONF_EVENT_ID)

    async def async_attach_runner(self, run_action: TriggerActionRunner) -> CALLBACK_TYPE:
        """Attach the trigger to the normalized House Chime event stream."""

        @callback
        def _handle_event(event) -> None:
            data = dict(getattr(event, "data", {}) or {})
            if self._event_type and data.get("type") != self._event_type:
                return
            if self._event_id and data.get(CONF_EVENT_ID) != self._event_id:
                return
            event_type = data.get("type", "activity")
            event_id = data.get(CONF_EVENT_ID, "unknown")
            run_action(
                data,
                f"House Chime {event_type} for {event_id}",
            )

        return self.hass.bus.async_listen(BUS_EVENT_ANNOUNCEMENT, _handle_event)


def _trigger_options(config: Any) -> dict[str, Any]:
    if isinstance(config, dict):
        return dict(config.get(CONF_OPTIONS) or {})
    return dict(getattr(config, "options", None) or {})
