"""Minimal Home Assistant test stubs for config-flow unit tests."""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _install_homeassistant_stubs() -> None:
    if "homeassistant" in sys.modules:
        return

    homeassistant = types.ModuleType("homeassistant")
    config_entries = types.ModuleType("homeassistant.config_entries")
    components = types.ModuleType("homeassistant.components")
    sensor_component = types.ModuleType("homeassistant.components.sensor")
    core = types.ModuleType("homeassistant.core")
    const = types.ModuleType("homeassistant.const")
    helpers = types.ModuleType("homeassistant.helpers")
    config_validation = types.ModuleType("homeassistant.helpers.config_validation")
    dispatcher = types.ModuleType("homeassistant.helpers.dispatcher")
    selector = types.ModuleType("homeassistant.helpers.selector")

    class ConfigFlow:
        VERSION = 1

        def __init_subclass__(cls, **kwargs: Any) -> None:
            super().__init_subclass__()

        def async_show_form(self, *, step_id: str, data_schema=None, description_placeholders=None, errors=None):
            return {
                "type": "form",
                "step_id": step_id,
                "data_schema": data_schema,
                "description_placeholders": description_placeholders or {},
                "errors": errors or {},
            }

        def async_create_entry(self, *, title: str, data: dict[str, Any]):
            return {"type": "create_entry", "title": title, "data": data}

    class OptionsFlow:
        def async_show_menu(self, *, step_id: str, menu_options: list[str]):
            return {"type": "menu", "step_id": step_id, "menu_options": menu_options}

        def async_show_form(self, *, step_id: str, data_schema=None, description_placeholders=None, errors=None):
            return {
                "type": "form",
                "step_id": step_id,
                "data_schema": data_schema,
                "description_placeholders": description_placeholders or {},
                "errors": errors or {},
            }

        def async_create_entry(self, *, title: str, data: dict[str, Any]):
            return {"type": "create_entry", "title": title, "data": data}

    class ConfigEntry:
        pass

    @dataclass
    class SelectOptionDict(dict):
        value: str
        label: str

        def __post_init__(self) -> None:
            dict.__init__(self, value=self.value, label=self.label)

    class SelectSelectorMode:
        DROPDOWN = "dropdown"

    class SelectSelectorConfig:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

    class SelectSelector:
        def __init__(self, config: SelectSelectorConfig) -> None:
            self.config = config

        def __call__(self, value: Any) -> Any:
            return value

    class MediaSelectorConfig:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

    class MediaSelector:
        def __init__(self, config: MediaSelectorConfig | None = None) -> None:
            self.config = config

        def __call__(self, value: Any) -> Any:
            return value

    class SensorEntity:
        pass

    class HomeAssistant:
        pass

    class SupportsResponse:
        OPTIONAL = "optional"

    def callback(func):
        return func

    def async_dispatcher_connect(*args: Any, **kwargs: Any):
        return lambda: None

    def async_dispatcher_send(*args: Any, **kwargs: Any):
        return None

    config_entries.ConfigFlow = ConfigFlow
    config_entries.OptionsFlow = OptionsFlow
    config_entries.ConfigEntry = ConfigEntry
    const.CONF_NAME = "name"
    selector.SelectOptionDict = SelectOptionDict
    selector.SelectSelectorMode = SelectSelectorMode
    selector.SelectSelectorConfig = SelectSelectorConfig
    selector.SelectSelector = SelectSelector
    selector.MediaSelectorConfig = MediaSelectorConfig
    selector.MediaSelector = MediaSelector
    sensor_component.SensorEntity = SensorEntity
    core.HomeAssistant = HomeAssistant
    core.SupportsResponse = SupportsResponse
    core.callback = callback
    config_validation.string = str
    dispatcher.async_dispatcher_connect = async_dispatcher_connect
    dispatcher.async_dispatcher_send = async_dispatcher_send
    helpers.config_validation = config_validation
    components.sensor = sensor_component
    helpers.dispatcher = dispatcher
    helpers.selector = selector
    homeassistant.config_entries = config_entries
    homeassistant.components = components
    homeassistant.const = const
    homeassistant.helpers = helpers

    sys.modules["homeassistant"] = homeassistant
    sys.modules["homeassistant.config_entries"] = config_entries
    sys.modules["homeassistant.components"] = components
    sys.modules["homeassistant.components.sensor"] = sensor_component
    sys.modules["homeassistant.core"] = core
    sys.modules["homeassistant.const"] = const
    sys.modules["homeassistant.helpers"] = helpers
    sys.modules["homeassistant.helpers.config_validation"] = config_validation
    sys.modules["homeassistant.helpers.dispatcher"] = dispatcher
    sys.modules["homeassistant.helpers.selector"] = selector


_install_homeassistant_stubs()


@dataclass
class FakeState:
    entity_id: str
    state: str
    name: str | None = None
    extra_attributes: dict[str, Any] | None = None

    @property
    def attributes(self) -> dict[str, Any]:
        attributes = dict(self.extra_attributes or {})
        if self.name:
            attributes["friendly_name"] = self.name
        return attributes


class FakeStates:
    def __init__(self, states: list[FakeState]) -> None:
        self._states = states

    def async_all(self) -> list[FakeState]:
        return list(self._states)


def make_fake_hass(states: list[FakeState]):
    return SimpleNamespace(states=FakeStates(states))
