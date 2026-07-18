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
    ANNOUNCEMENT_EVENT_SUPPRESSED,
    BUS_EVENT_STATUS_UPDATED,
    CONF_ACTIVE_CONFIG,
    CONF_ENTITY_IDS,
    CONF_EVENT_ID,
    CONF_PERSON_ID,
    CONF_PLAYBACK_ENABLED,
    CONF_PLAYBACK_ROUTES,
    CONF_SOURCE,
    CONF_SKIP_DUPLICATE_SUPPRESSION,
    CONF_TARGET_PLAYER_ENTITY_ID,
    CONF_ZONE_ENTITY_IDS,
    DOMAIN,
    PLATFORMS,
    SIGNAL_STATUS_UPDATED,
)
from .discovery import (
    discover_device_trackers,
    discover_media_players,
    discover_people,
    is_selectable_announcement_player,
)
from .media import async_available_media_for_resolution
from .models import AnnouncementConfig, ResolverRuntime, ZoneConfig
from .playback import PlaybackMediaError, play_music_assistant_announcement
from .repairs import async_create_resolution_issues
from .resolver import resolve_announcement
from .routes import (
    apply_playback_routes,
    normalise_playback_routes,
    validate_playback_routes,
)
from .status import initial_status, record_resolution, refresh_presence_status
from .storage import migrate_config_dict

SERVICE_DISCOVER = "discover"
SERVICE_RESOLVE = "resolve"
SERVICE_PLAY = "play"
SERVICE_SET_SPEAKERS = "set_speakers"
SERVICE_SET_PLAYBACK_ROUTES = "set_playback_routes"
SERVICE_SET_PERSON_PLAYBACK = "set_person_playback"


def _ensure_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


EVENT_SCHEMA = (
    vol.Schema(
        {
            vol.Required(CONF_EVENT_ID): cv.string,
            vol.Optional(CONF_SKIP_DUPLICATE_SUPPRESSION, default=False): cv.boolean,
        }
    )
    if vol is not None and cv is not None
    else None
)

SET_SPEAKERS_SCHEMA = (
    vol.Schema(
        {
            vol.Required(CONF_ENTITY_IDS): cv.entity_ids,
        }
    )
    if vol is not None and cv is not None
    else None
)

PLAYBACK_ROUTE_SCHEMA = (
    vol.Schema(
        {
            vol.Required(CONF_TARGET_PLAYER_ENTITY_ID): cv.entity_id,
            vol.Required(CONF_SOURCE): cv.string,
            vol.Required(CONF_ZONE_ENTITY_IDS): cv.entity_ids,
        }
    )
    if vol is not None and cv is not None
    else None
)

SET_PLAYBACK_ROUTES_SCHEMA = (
    vol.Schema(
        {
            vol.Required(CONF_PLAYBACK_ROUTES): vol.All(
                _ensure_list,
                [PLAYBACK_ROUTE_SCHEMA],
            ),
        }
    )
    if vol is not None and PLAYBACK_ROUTE_SCHEMA is not None
    else None
)

SET_PERSON_PLAYBACK_SCHEMA = (
    vol.Schema(
        {
            vol.Required(CONF_PERSON_ID): cv.string,
            vol.Required(CONF_PLAYBACK_ENABLED): cv.boolean,
        }
    )
    if vol is not None and cv is not None
    else None
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up from a config entry."""

    hass.data.setdefault(DOMAIN, {})
    configured_options = entry.options.get(CONF_ACTIVE_CONFIG)
    config_dict, changed = migrate_config_dict(
        configured_options or entry.data.get(CONF_ACTIVE_CONFIG)
    )
    if changed:
        if configured_options:
            options = dict(entry.options)
            options[CONF_ACTIVE_CONFIG] = config_dict
            hass.config_entries.async_update_entry(entry, options=options)
        else:
            entry_data = dict(entry.data)
            entry_data[CONF_ACTIVE_CONFIG] = config_dict
            hass.config_entries.async_update_entry(entry, data=entry_data)
    config = AnnouncementConfig.from_dict(config_dict)
    hass.data[DOMAIN][entry.entry_id] = {
        "entry": entry,
        "config": config,
        "status": initial_status(config, _state_map(hass)),
        "last_resolution": None,
        "last_triggered_by_event": {},
    }
    entry.async_on_unload(
        hass.bus.async_listen(
            "state_changed",
            lambda event: _handle_presence_state_change(hass, entry.entry_id, event),
        )
    )
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
        for service in (
            SERVICE_DISCOVER,
            SERVICE_RESOLVE,
            SERVICE_PLAY,
            SERVICE_SET_SPEAKERS,
            SERVICE_SET_PLAYBACK_ROUTES,
            SERVICE_SET_PERSON_PLAYBACK,
        ):
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
        outcome = "suppressed" if resolution.suppressed else "resolved"
        _record_and_publish_status(hass, data, resolution, outcome=outcome)
        await async_create_resolution_issues(hass, resolution)
        fire_announcement_event(
            hass,
            ANNOUNCEMENT_EVENT_SUPPRESSED if resolution.suppressed else ANNOUNCEMENT_EVENT_RESOLVED,
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
        if resolution.suppressed:
            _record_and_publish_status(hass, data, resolution, outcome="suppressed")
            fire_announcement_event(
                hass,
                ANNOUNCEMENT_EVENT_SUPPRESSED,
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
        route_errors = await apply_playback_routes(hass, data["config"], resolution)
        if route_errors:
            resolution.ok = False
            resolution.errors.extend(route_errors)
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

    async def handle_set_speakers(call: ServiceCall) -> dict[str, Any]:
        data = _first_entry_data(hass)
        result = _set_selected_speakers(hass, data, call.data[CONF_ENTITY_IDS])
        _publish_status_updated(hass, data)
        return result

    async def handle_set_playback_routes(call: ServiceCall) -> dict[str, Any]:
        data = _first_entry_data(hass)
        result = _set_playback_routes(
            hass,
            data,
            call.data[CONF_PLAYBACK_ROUTES],
        )
        _publish_status_updated(hass, data)
        return result

    async def handle_set_person_playback(call: ServiceCall) -> dict[str, Any]:
        data = _first_entry_data(hass)
        result = _set_person_playback(
            hass,
            data,
            call.data[CONF_PERSON_ID],
            call.data[CONF_PLAYBACK_ENABLED],
        )
        if result["ok"]:
            _refresh_presence_status(hass, data)
        _publish_status_updated(hass, data)
        return result

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
        SERVICE_SET_SPEAKERS,
        handle_set_speakers,
        schema=SET_SPEAKERS_SCHEMA,
        **response_kwargs,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_PLAYBACK_ROUTES,
        handle_set_playback_routes,
        schema=SET_PLAYBACK_ROUTES_SCHEMA,
        **response_kwargs,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_PERSON_PLAYBACK,
        handle_set_person_playback,
        schema=SET_PERSON_PLAYBACK_SCHEMA,
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
    last_triggered_by_event = (
        {}
        if call.data.get(CONF_SKIP_DUPLICATE_SUPPRESSION, False)
        else data["last_triggered_by_event"]
    )
    runtime = ResolverRuntime(
        states=states,
        available_media=None,
        last_triggered_by_event=last_triggered_by_event,
    )
    preliminary = resolve_announcement(config, call.data[CONF_EVENT_ID], runtime)
    available_media = await async_available_media_for_resolution(hass, preliminary)
    validated_runtime = ResolverRuntime(
        states=states,
        available_media=available_media,
        last_triggered_by_event=last_triggered_by_event,
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
    _publish_status_updated(hass, data)


def _state_map(hass: HomeAssistant) -> dict[str, str]:
    """Return a small, serialisable snapshot of current Home Assistant states."""

    return {state.entity_id: state.state for state in hass.states.async_all()}


def _presence_entity_ids(config: AnnouncementConfig) -> set[str]:
    """Return the presence entities that affect House Chime's live status."""

    entity_ids = set()
    for person in config.people:
        if not person.in_scope:
            continue
        if person.entity_id:
            entity_ids.add(person.entity_id)
        entity_ids.update(person.fallback_tracker_entity_ids)
    return entity_ids


def _refresh_presence_status(hass: HomeAssistant, data: dict[str, Any]) -> None:
    """Synchronise dashboard presence status with current Home Assistant state."""

    refresh_presence_status(data["status"], data["config"], _state_map(hass))


def _handle_presence_state_change(hass: HomeAssistant, entry_id: str, event: Any) -> None:
    """Publish new presence data when a configured person or tracker changes."""

    data = hass.data.get(DOMAIN, {}).get(entry_id)
    if data is None:
        return
    entity_id = event.data.get("entity_id")
    if entity_id not in _presence_entity_ids(data["config"]):
        return
    _refresh_presence_status(hass, data)
    _publish_status_updated(hass, data)


def _publish_status_updated(hass: HomeAssistant, data: dict[str, Any]) -> None:
    """Notify status entities after their backing status dictionary changes."""

    if async_dispatcher_send is not None:
        async_dispatcher_send(hass, SIGNAL_STATUS_UPDATED)
    hass.bus.async_fire(BUS_EVENT_STATUS_UPDATED, {"entry_id": _entry_id_for_data(hass, data)})


def _set_selected_speakers(
    hass: HomeAssistant,
    data: dict[str, Any],
    entity_ids: list[str],
) -> dict[str, Any]:
    """Replace selected announcement speakers with compatible live targets."""

    config: AnnouncementConfig = data["config"]
    requested = list(dict.fromkeys(str(entity_id) for entity_id in entity_ids))
    selectable_zones = [
        record
        for record in discover_media_players(hass.states.async_all())
        if is_selectable_announcement_player(record)
    ]
    selectable_by_entity = {record.entity_id: record for record in selectable_zones}
    invalid = [
        entity_id for entity_id in requested if entity_id not in selectable_by_entity
    ]

    if invalid:
        return {
            "ok": False,
            "errors": [f"incompatible_speaker:{entity_id}" for entity_id in invalid],
            "selected_target_zones": [
                zone.entity_id for zone in config.zones if zone.selected
            ],
            "available_target_entity_ids": list(selectable_by_entity),
        }

    current_zones_by_entity = {zone.entity_id: zone for zone in config.zones}
    selected = set(requested)
    config.zones = [
        ZoneConfig(
            entity_id=record.entity_id,
            name=record.name,
            selected=record.entity_id in selected,
            quiet_excluded=current_zones_by_entity.get(
                record.entity_id,
                ZoneConfig(record.entity_id),
            ).quiet_excluded,
        )
        for record in selectable_zones
    ]
    selected_target_zones = [
        zone.entity_id for zone in config.zones if zone.selected
    ]
    data["status"]["selected_target_zones"] = selected_target_zones
    data["status"]["last_failure_reason"] = None
    _persist_entry_config(hass, data, config)
    return {
        "ok": True,
        "selected_target_zones": selected_target_zones,
        "available_target_entity_ids": list(selectable_by_entity),
    }


def _set_playback_routes(
    hass: HomeAssistant,
    data: dict[str, Any],
    route_data: list[dict[str, Any]],
) -> dict[str, Any]:
    """Replace saved source routes used before announcement playback."""

    config: AnnouncementConfig = data["config"]
    routes, errors = normalise_playback_routes(route_data)
    errors.extend(validate_playback_routes(hass, routes))
    if errors:
        return {
            "ok": False,
            "errors": errors,
            "playback_routes": [route.to_dict() for route in config.playback_routes],
        }

    config.playback_routes = routes
    _persist_entry_config(hass, data, config)
    return {
        "ok": True,
        "playback_routes": [route.to_dict() for route in config.playback_routes],
    }


def _set_person_playback(
    hass: HomeAssistant,
    data: dict[str, Any],
    person_id: str,
    playback_enabled: bool,
) -> dict[str, Any]:
    """Persist a configured person's at-home playback preference."""

    config: AnnouncementConfig = data["config"]
    person = next((item for item in config.people if item.id == person_id), None)
    if person is None:
        return {
            "ok": False,
            "errors": [f"unknown_person:{person_id}"],
        }
    person.playback_enabled_when_home = bool(playback_enabled)
    _persist_entry_config(hass, data, config)
    return {
        "ok": True,
        "person_id": person.id,
        "playback_enabled": person.playback_enabled_when_home,
    }


def _persist_entry_config(
    hass: HomeAssistant,
    data: dict[str, Any],
    config: AnnouncementConfig,
) -> None:
    """Persist changed House Chime config through the config-entry API."""

    entry = data.get("entry")
    if entry is None:
        return
    options = dict(getattr(entry, "options", {}) or {})
    options[CONF_ACTIVE_CONFIG] = config.to_dict()
    hass.config_entries.async_update_entry(entry, options=options)


def _entry_id_for_data(hass: HomeAssistant, entry_data: dict[str, Any]) -> str | None:
    """Return the config entry id for an in-memory House Chime entry."""

    for entry_id, data in hass.data.get(DOMAIN, {}).items():
        if data is entry_data:
            return entry_id
    return None
