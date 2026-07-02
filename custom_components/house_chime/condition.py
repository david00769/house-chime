"""Purpose-specific automation conditions for House Chime."""

from __future__ import annotations

from typing import Any

try:
    from homeassistant.const import CONF_OPTIONS, CONF_STATE
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers import config_validation as cv
    from homeassistant.helpers.condition import Condition, ConditionConfig
    from homeassistant.helpers.typing import ConfigType
    import voluptuous as vol
except (ModuleNotFoundError, ImportError):
    CONF_OPTIONS = "options"
    CONF_STATE = "state"
    HomeAssistant = Any
    ConditionConfig = dict[str, Any]
    ConfigType = dict[str, Any]

    class Condition:
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
        def Required(key, default=None):
            return key

        @staticmethod
        def Optional(key, default=None):
            return key

        @staticmethod
        def In(values):
            return lambda value: value if value in values else value

    vol = _Vol()

from .const import CONF_EVENT_ID, DOMAIN
from .models import AnnouncementConfig, ResolverRuntime
from .resolver import resolve_announcement

CONDITION_READY = "ready"
CONDITION_EVENT_ENABLED = "event_enabled"
CONDITION_EVENT_CAN_RESOLVE = "event_can_resolve"
CONDITION_QUIET_MODE = "quiet_mode"

QUIET_STATES = ("active", "inactive")

_EMPTY_SCHEMA = vol.Schema({})
_EVENT_SCHEMA = vol.Schema({vol.Required(CONF_EVENT_ID): cv.string})
_QUIET_SCHEMA = vol.Schema({vol.Required(CONF_STATE): vol.In(QUIET_STATES)})


async def async_get_conditions(hass: HomeAssistant) -> dict[str, type[Condition]]:
    """Return conditions provided by House Chime."""

    return {
        CONDITION_READY: ReadyCondition,
        CONDITION_EVENT_ENABLED: EventEnabledCondition,
        CONDITION_EVENT_CAN_RESOLVE: EventCanResolveCondition,
        CONDITION_QUIET_MODE: QuietModeCondition,
    }


class HouseChimeCondition(Condition):
    """Base class for House Chime automation conditions."""

    _options_schema = _EMPTY_SCHEMA

    @classmethod
    async def async_validate_config(cls, hass: HomeAssistant, config: ConfigType) -> ConfigType:
        """Validate condition config and keep options normalized."""

        normalized = dict(config)
        options = _condition_options(normalized)
        normalized[CONF_OPTIONS] = cls._options_schema(options)
        return normalized

    def __init__(self, hass: HomeAssistant, config: ConditionConfig) -> None:
        try:
            super().__init__(hass, config)
        except TypeError:
            super().__init__()
            self.hass = hass
        self.config = config
        self.options = _condition_options(config)

    def async_check(self, **kwargs: Any) -> bool:
        """Evaluate the condition."""

        return self._async_check(**kwargs)

    def _async_check(self, **kwargs: Any) -> bool:
        raise NotImplementedError

    @property
    def _entry_data(self) -> dict[str, Any] | None:
        entries = getattr(self.hass, "data", {}).get(DOMAIN, {})
        if not entries:
            return None
        return next(iter(entries.values()))


class ReadyCondition(HouseChimeCondition):
    """Return true when House Chime is loaded and ready."""

    def _async_check(self, **kwargs: Any) -> bool:
        data = self._entry_data
        if not data:
            return False
        return bool(data.get("status", {}).get("integration_ready"))


class EventEnabledCondition(HouseChimeCondition):
    """Return true when a House Chime event is enabled."""

    _options_schema = _EVENT_SCHEMA

    def _async_check(self, **kwargs: Any) -> bool:
        data = self._entry_data
        if not data:
            return False
        config: AnnouncementConfig = data["config"]
        event_id = self.options[CONF_EVENT_ID]
        return any(event.id == event_id and event.enabled for event in config.events)


class EventCanResolveCondition(HouseChimeCondition):
    """Return true when the configured event can resolve without playing audio."""

    _options_schema = _EVENT_SCHEMA

    def _async_check(self, **kwargs: Any) -> bool:
        data = self._entry_data
        if not data:
            return False
        event_id = self.options[CONF_EVENT_ID]
        states = {state.entity_id: state.state for state in self.hass.states.async_all()}
        resolution = resolve_announcement(
            data["config"],
            event_id,
            ResolverRuntime(
                states=states,
                available_media=None,
                last_triggered_by_event=data.get("last_triggered_by_event", {}),
            ),
        )
        return resolution.ok


class QuietModeCondition(HouseChimeCondition):
    """Return true when quiet mode matches the requested state."""

    _options_schema = _QUIET_SCHEMA

    def _async_check(self, **kwargs: Any) -> bool:
        data = self._entry_data
        if not data:
            return False
        quiet_active = bool(data.get("status", {}).get("quiet_mode_active"))
        return quiet_active if self.options[CONF_STATE] == "active" else not quiet_active


def _condition_options(config: Any) -> dict[str, Any]:
    if isinstance(config, dict):
        return dict(config.get(CONF_OPTIONS) or {})
    return dict(getattr(config, "options", None) or {})
