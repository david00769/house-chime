"""House Chime integration."""

from __future__ import annotations

from datetime import datetime
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant, ServiceCall
else:
    ConfigEntry = Any
    HomeAssistant = Any
    ServiceCall = Any

try:
    from homeassistant.core import SupportsResponse
    import voluptuous as vol
    import homeassistant.helpers.config_validation as cv
    from homeassistant.helpers.dispatcher import async_dispatcher_send
except ModuleNotFoundError:
    SupportsResponse = None
    vol = None
    cv = None
    async_dispatcher_send = None

from .activity import fire_announcement_event
from .const import (
    ANNOUNCEMENT_EVENT_PLAY_FAILED,
    ANNOUNCEMENT_EVENT_PLAYED,
    ANNOUNCEMENT_EVENT_RESOLVED,
    CONF_ACTIVE_CONFIG,
    CONF_EVENT_ID,
    DOMAIN,
    PLATFORMS,
    SIGNAL_STATUS_UPDATED,
)
from .discovery import (
    discover_device_trackers,
    discover_media_players,
    discover_people,
)
from .media import async_available_media_for_resolution
from .models import AnnouncementConfig, ResolverRuntime
from .playback import PlaybackMediaError, play_music_assistant_announcement
from .repairs import async_create_resolution_issues
from .resolver import resolve_announcement
from .status import initial_status, record_resolution
from .storage import migrate_config_dict

SERVICE_DISCOVER = "discover"
SERVICE_RESOLVE = "resolve"
SERVICE_PLAY = "play"

EVENT_SCHEMA = (
    vol.Schema({vol.Required(CONF_EVENT_ID): cv.string})
    if vol is not None and cv is not None
    else None
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up from a config entry."""

    hass.data.setdefault(DOMAIN, {})
    config_dict, _ = migrate_config_dict(
        entry.options.get(CONF_ACTIVE_CONFIG) or entry.data.get(CONF_ACTIVE_CONFIG)
    )
    config = AnnouncementConfig.from_dict(config_dict)
    hass.data[DOMAIN][entry.entry_id] = {
        "config": config,
        "status": initial_status(config),
        "last_resolution": None,
        "last_triggered_by_event": {},
    }
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    _register_services(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate a config entry."""

    data = dict(entry.data)
    options = dict(entry.options)
    changed = False

    if CONF_ACTIVE_CONFIG in data:
        data[CONF_ACTIVE_CONFIG], data_changed = migrate_config_dict(data[CONF_ACTIVE_CONFIG])
        changed = changed or data_changed
    if CONF_ACTIVE_CONFIG in options:
        options[CONF_ACTIVE_CONFIG], options_changed = migrate_config_dict(options[CONF_ACTIVE_CONFIG])
        changed = changed or options_changed

    if changed:
        hass.config_entries.async_update_entry(entry, data=data, options=options)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if not hass.data.get(DOMAIN):
        for service in (SERVICE_DISCOVER, SERVICE_RESOLVE, SERVICE_PLAY):
            hass.services.async_remove(DOMAIN, service)
    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the integration after options change."""

    await hass.config_entries.async_reload(entry.entry_id)


def _register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_DISCOVER):
        return

    async def handle_discover(call: ServiceCall) -> dict[str, Any]:
        states = list(hass.states.async_all())
        discovery = {
            "people": [item.to_dict() for item in discover_people(states)],
            "device_trackers": [item.to_dict() for item in discover_device_trackers(states)],
            "media_players": [item.to_dict() for item in discover_media_players(states)],
        }
        hass.bus.async_fire(f"{DOMAIN}_discovery", discovery)
        return discovery

    async def handle_resolve(call: ServiceCall) -> dict[str, Any]:
        data = _first_entry_data(hass)
        resolution = await _resolve_from_service_call(hass, data, call)
        data["last_resolution"] = resolution
        _record_and_publish_status(hass, data, resolution, outcome="resolved")
        await async_create_resolution_issues(hass, resolution)
        fire_announcement_event(
            hass,
            ANNOUNCEMENT_EVENT_RESOLVED,
            resolution,
            source="resolve",
        )
        return resolution.to_dict()

    async def handle_play(call: ServiceCall) -> dict[str, Any]:
        data = _first_entry_data(hass)
        resolution = await _resolve_from_service_call(hass, data, call)
        data["last_resolution"] = resolution
        if not resolution.ok:
            _record_and_publish_status(hass, data, resolution, outcome="failed")
            await async_create_resolution_issues(hass, resolution)
            fire_announcement_event(
                hass,
                ANNOUNCEMENT_EVENT_PLAY_FAILED,
                resolution,
                source="play",
            )
            return resolution.to_dict()
        if not hass.services.has_service("music_assistant", "play_announcement"):
            resolution.ok = False
            resolution.errors.append("missing_music_assistant_service:music_assistant.play_announcement")
            _record_and_publish_status(hass, data, resolution, outcome="failed")
            await async_create_resolution_issues(hass, resolution)
            fire_announcement_event(
                hass,
                ANNOUNCEMENT_EVENT_PLAY_FAILED,
                resolution,
                source="play",
            )
            return resolution.to_dict()
        try:
            warnings = await play_music_assistant_announcement(hass, resolution)
        except PlaybackMediaError as err:
            resolution.ok = False
            resolution.errors.append(str(err))
            _record_and_publish_status(hass, data, resolution, outcome="failed")
            await async_create_resolution_issues(hass, resolution)
            fire_announcement_event(
                hass,
                ANNOUNCEMENT_EVENT_PLAY_FAILED,
                resolution,
                source="play",
            )
            return resolution.to_dict()
        except Exception as err:
            resolution.ok = False
            resolution.errors.append(f"music_assistant_playback_failed:{type(err).__name__}")
            _record_and_publish_status(hass, data, resolution, outcome="failed")
            await async_create_resolution_issues(hass, resolution)
            fire_announcement_event(
                hass,
                ANNOUNCEMENT_EVENT_PLAY_FAILED,
                resolution,
                source="play",
            )
            return resolution.to_dict()
        resolution.warnings.extend(warnings)
        data["last_triggered_by_event"][resolution.event_id] = datetime.now().isoformat()
        _record_and_publish_status(hass, data, resolution, outcome="played")
        fire_announcement_event(
            hass,
            ANNOUNCEMENT_EVENT_PLAYED,
            resolution,
            source="play",
        )
        return resolution.to_dict()

    response_kwargs = {}
    if SupportsResponse is not None:
        response_kwargs["supports_response"] = SupportsResponse.OPTIONAL

    hass.services.async_register(DOMAIN, SERVICE_DISCOVER, handle_discover, **response_kwargs)
    hass.services.async_register(
        DOMAIN,
        SERVICE_RESOLVE,
        handle_resolve,
        schema=EVENT_SCHEMA,
        **response_kwargs,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_PLAY,
        handle_play,
        schema=EVENT_SCHEMA,
        **response_kwargs,
    )


def _first_entry_data(hass: HomeAssistant) -> dict[str, Any]:
    entries = hass.data.get(DOMAIN, {})
    if not entries:
        raise ValueError("House Chime is not configured")
    return next(iter(entries.values()))


async def _resolve_from_service_call(
    hass: HomeAssistant,
    data: dict[str, Any],
    call: ServiceCall,
):
    config: AnnouncementConfig = data["config"]
    states = {state.entity_id: state.state for state in hass.states.async_all()}
    runtime = ResolverRuntime(
        states=states,
        available_media=None,
        last_triggered_by_event=data["last_triggered_by_event"],
    )
    preliminary = resolve_announcement(config, call.data[CONF_EVENT_ID], runtime)
    available_media = await async_available_media_for_resolution(hass, preliminary)
    validated_runtime = ResolverRuntime(
        states=states,
        available_media=available_media,
        last_triggered_by_event=data["last_triggered_by_event"],
    )
    return resolve_announcement(config, call.data[CONF_EVENT_ID], validated_runtime)


def _record_and_publish_status(
    hass: HomeAssistant,
    data: dict[str, Any],
    resolution,
    *,
    outcome: str,
) -> None:
    has_music_assistant = hass.services.has_service("music_assistant", "play_announcement")
    record_resolution(
        data["status"],
        resolution,
        outcome=outcome,
        has_music_assistant=has_music_assistant,
    )
    if async_dispatcher_send is not None:
        async_dispatcher_send(hass, SIGNAL_STATUS_UPDATED)
