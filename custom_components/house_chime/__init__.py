"""House Chime integration."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant, ServiceCall
else:
    ConfigEntry = Any
    HomeAssistant = Any
    ServiceCall = Any

try:
    from homeassistant.core import SupportsResponse, callback
    import voluptuous as vol
    import homeassistant.helpers.config_validation as cv
    from homeassistant.helpers.dispatcher import async_dispatcher_send
except ModuleNotFoundError:
    SupportsResponse = None
    vol = None
    cv = None
    async_dispatcher_send = None

    def callback(func):
        return func

try:
    from homeassistant.helpers.event import (
        async_call_later,
        async_track_state_change_event,
    )
except ModuleNotFoundError:
    async_call_later = None
    async_track_state_change_event = None

from .activity import fire_announcement_event
from .approach_delay import (
    approach_sensor_warning,
    approach_wait_cancellation_reason,
    approach_wait_deadline,
)
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
    EVENT_FRONT_DOOR_APPROACH,
    EVENT_FRONT_DOOR_DOORBELL,
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
from .models import (
    AnnouncementConfig,
    AnnouncementResolution,
    ResolverRuntime,
    ZoneConfig,
)
from .playback import PlaybackMediaError, play_music_assistant_announcement
from .pending_policy import approach_pending_policy, interaction_suppression_deadline
from .repairs import async_create_resolution_issues, async_sync_setup_issues
from .resolver import evaluate_door_guard, resolve_announcement
from .routes import (
    apply_playback_routes,
    normalise_playback_routes,
    validate_playback_routes,
)
from .status import initial_status, record_resolution, refresh_presence_status
from .storage import migrate_config_dict

SERVICE_DISCOVER = "discover"
SERVICE_RESOLVE = "resolve"
SERVICE_INGEST = "ingest_event"
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
    states = _state_map(hass)
    door_suppression_until = _initial_door_suppression_until(config, states)
    hass.data[DOMAIN][entry.entry_id] = {
        "entry": entry,
        "config": config,
        "status": initial_status(config, states),
        "last_resolution": None,
        "last_triggered_by_event": {},
        "door_suppression_until": door_suppression_until,
        "door_suppression_reason": (
            "recent_front_door_activity" if door_suppression_until else None
        ),
        "door_guard_cancel_timer": None,
        "approach_wait_started_at": None,
        "approach_wait_until": None,
        "approach_wait_cancel_timer": None,
    }
    data = hass.data[DOMAIN][entry.entry_id]
    entry.runtime_data = data
    _refresh_door_guard_status(hass, data)
    _refresh_approach_delay_status(hass, data)
    _schedule_door_guard_expiry(hass, entry.entry_id, data)
    tracked_entity_ids = _tracked_entity_ids(config)

    @callback
    def handle_tracked_state_change(event: Any) -> None:
        _handle_state_change(hass, entry.entry_id, event)

    if tracked_entity_ids and async_track_state_change_event is not None:
        entry.async_on_unload(
            async_track_state_change_event(
                hass,
                tracked_entity_ids,
                handle_tracked_state_change,
            )
        )
    elif tracked_entity_ids:
        entry.async_on_unload(
            hass.bus.async_listen(
                "state_changed",
                handle_tracked_state_change,
            )
        )
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    _register_services(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await async_sync_setup_issues(hass, config, states)
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
    data = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    cancel_timer = data.get("door_guard_cancel_timer") if data else None
    if callable(cancel_timer):
        cancel_timer()
    approach_cancel_timer = data.get("approach_wait_cancel_timer") if data else None
    if callable(approach_cancel_timer):
        approach_cancel_timer()
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if not hass.data.get(DOMAIN):
        for service in (
            SERVICE_DISCOVER,
            SERVICE_RESOLVE,
            SERVICE_INGEST,
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
        if call.data[CONF_EVENT_ID] == EVENT_FRONT_DOOR_DOORBELL:
            _start_encounter_suppression(
                hass,
                data,
                reason="recent_doorbell_activity",
            )
            _cancel_approach_wait(
                hass,
                data,
                reason="doorbell_during_wait",
                record=True,
            )
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
            playback_result = await play_music_assistant_announcement(
                hass,
                resolution,
                should_cancel=lambda: _active_door_suppression(
                    hass,
                    data,
                    event_id=resolution.event_id,
                ),
            )
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
        resolution.warnings.extend(playback_result.warnings)
        if playback_result.cancelled_reason:
            resolution.suppression_reason = playback_result.cancelled_reason
            resolution.suppression_until = playback_result.suppression_until
            if playback_result.dispatched_group_count == 0:
                resolution.suppressed = True
                _record_and_publish_status(hass, data, resolution, outcome="suppressed")
                fire_announcement_event(
                    hass,
                    ANNOUNCEMENT_EVENT_SUPPRESSED,
                    resolution,
                    source="play",
                )
                return resolution.to_dict()
            resolution.warnings.append(
                f"door_guard_partial_dispatch:{playback_result.dispatched_group_count}"
            )
        data["last_triggered_by_event"][resolution.event_id] = datetime.now().isoformat()
        _record_and_publish_status(hass, data, resolution, outcome="played")
        fire_announcement_event(
            hass,
            ANNOUNCEMENT_EVENT_PLAYED,
            resolution,
            source="play",
        )
        return resolution.to_dict()

    async def handle_ingest(call: ServiceCall) -> dict[str, Any]:
        """Accept source events while preserving delayed-event policy."""

        data = _first_entry_data(hass)
        event_id = call.data[CONF_EVENT_ID]
        if event_id != EVENT_FRONT_DOOR_APPROACH:
            return await handle_play(call)

        config: AnnouncementConfig = data["config"]
        policy = approach_pending_policy(config)
        if not policy.trigger_entity_id:
            return {
                "event_id": event_id,
                "ok": False,
                "queued": False,
                "suppressed": False,
                "errors": ["approach_delay_not_configured"],
            }
        cancellation_reason = approach_wait_cancellation_reason(
            config.approach_delay,
            _state_map(hass),
        )
        if cancellation_reason:
            _record_approach_delay_suppression(
                hass,
                data,
                reason=cancellation_reason,
                suppression_until=None,
            )
            return {
                "event_id": event_id,
                "ok": True,
                "queued": False,
                "suppressed": True,
                "suppression_reason": cancellation_reason,
            }
        _start_approach_wait(hass, _entry_id_for_data(hass, data), data)
        return {
            "event_id": event_id,
            "ok": True,
            "queued": bool(data.get("approach_wait_until")),
            "suppressed": not bool(data.get("approach_wait_until")),
            "wait_until": data.get("approach_wait_until"),
            "suppression_reason": data["status"].get("approach_suppression_reason"),
        }

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
        SERVICE_INGEST,
        handle_ingest,
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
        door_suppression_until=data.get("door_suppression_until"),
        door_suppression_reason=data.get("door_suppression_reason"),
    )
    preliminary = resolve_announcement(config, call.data[CONF_EVENT_ID], runtime)
    available_media = await async_available_media_for_resolution(hass, preliminary)
    validated_runtime = ResolverRuntime(
        states=states,
        available_media=available_media,
        last_triggered_by_event=last_triggered_by_event,
        door_suppression_until=data.get("door_suppression_until"),
        door_suppression_reason=data.get("door_suppression_reason"),
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


def _tracked_entity_ids(config: AnnouncementConfig) -> set[str]:
    """Return only entities that can change this entry's runtime policy."""

    entity_ids = _presence_entity_ids(config)
    if config.door_guard.sensor_entity_id:
        entity_ids.add(config.door_guard.sensor_entity_id)
    if config.approach_delay.sensor_entity_id:
        entity_ids.add(config.approach_delay.sensor_entity_id)
    return entity_ids


def _refresh_presence_status(hass: HomeAssistant, data: dict[str, Any]) -> None:
    """Synchronise dashboard presence status with current Home Assistant state."""

    refresh_presence_status(data["status"], data["config"], _state_map(hass))


@callback
def _handle_state_change(hass: HomeAssistant, entry_id: str, event: Any) -> None:
    """Apply a tracked entity change from Home Assistant's event loop."""

    entity_id = event.data.get("entity_id")
    old_state = getattr(event.data.get("old_state"), "state", None)
    new_state = getattr(event.data.get("new_state"), "state", None)
    _refresh_for_state_change(
        hass,
        entry_id,
        entity_id,
        old_state,
        new_state,
    )


def _refresh_for_state_change(
    hass: HomeAssistant,
    entry_id: str,
    entity_id: str | None,
    old_state: str | None,
    new_state: str | None,
) -> None:
    """Apply runtime changes for one relevant Home Assistant entity."""

    data = hass.data.get(DOMAIN, {}).get(entry_id)
    if data is None:
        return
    changed = False
    if entity_id in _presence_entity_ids(data["config"]):
        _refresh_presence_status(hass, data)
        changed = True
    if entity_id == data["config"].door_guard.sensor_entity_id:
        _update_door_guard_state(
            hass,
            entry_id,
            data,
            old_state=old_state,
            new_state=new_state,
        )
        if new_state == "on" and old_state != "on":
            _cancel_approach_wait(
                hass,
                data,
                reason="front_door_open_during_wait",
                suppression_until=data.get("door_suppression_until"),
                record=True,
            )
        changed = True
    if entity_id == data["config"].approach_delay.sensor_entity_id:
        if new_state == "on" and old_state != "on":
            _start_approach_wait(hass, entry_id, data)
        elif new_state != "on":
            cancellation_reason = approach_wait_cancellation_reason(
                data["config"].approach_delay,
                _state_map(hass),
            )
            _cancel_approach_wait(
                hass,
                data,
                reason=cancellation_reason or "person_left_before_delay",
                record=True,
            )
        _refresh_approach_delay_status(hass, data)
        changed = True
    if changed:
        _publish_status_updated(hass, data)
        _schedule_setup_issue_sync(hass, data)


def _schedule_setup_issue_sync(hass: HomeAssistant, data: dict[str, Any]) -> None:
    """Refresh Repair issues after a tracked sensor changes health."""

    coroutine = async_sync_setup_issues(hass, data["config"], _state_map(hass))
    if hasattr(hass, "async_create_task"):
        hass.async_create_task(coroutine)
    elif hasattr(hass, "loop"):
        hass.loop.create_task(coroutine)
    else:
        coroutine.close()


def _refresh_presence_for_entity(
    hass: HomeAssistant,
    entry_id: str,
    entity_id: str | None,
) -> None:
    """Publish presence state from Home Assistant's event-loop thread."""

    data = hass.data.get(DOMAIN, {}).get(entry_id)
    if data is None:
        return
    if entity_id not in _presence_entity_ids(data["config"]):
        return
    _refresh_presence_status(hass, data)
    _publish_status_updated(hass, data)


def _initial_door_suppression_until(
    config: AnnouncementConfig,
    states: dict[str, str],
    *,
    now: datetime | None = None,
) -> str | None:
    """Start a fresh cooldown when HA loads while the configured door is open."""

    sensor_entity_id = config.door_guard.sensor_entity_id
    if (
        not sensor_entity_id
        or states.get(sensor_entity_id) != "on"
        or config.door_guard.cooldown_seconds <= 0
    ):
        return None
    now = now or datetime.now(timezone.utc)
    return (now + timedelta(seconds=config.door_guard.cooldown_seconds)).isoformat()


def _update_door_guard_state(
    hass: HomeAssistant,
    entry_id: str,
    data: dict[str, Any],
    *,
    old_state: str | None,
    new_state: str | None,
    now: datetime | None = None,
) -> None:
    """Restart the cooldown on each closed-to-open door transition."""

    now = now or datetime.now(timezone.utc)
    if new_state == "on" and old_state != "on":
        _start_encounter_suppression(
            hass,
            data,
            reason="recent_front_door_activity",
            now=now,
        )
    _refresh_door_guard_status(hass, data, now=now)


def _start_encounter_suppression(
    hass: HomeAssistant,
    data: dict[str, Any],
    *,
    reason: str,
    now: datetime | None = None,
) -> None:
    """Start the shared post-door/post-Doorbell Approach quiet window."""

    now = now or datetime.now(timezone.utc)
    policy = approach_pending_policy(data["config"])
    data["door_suppression_until"] = interaction_suppression_deadline(
        policy,
        now=now,
    )
    data["door_suppression_reason"] = (
        reason if data["door_suppression_until"] else None
    )
    _schedule_door_guard_expiry(
        hass,
        _entry_id_for_data(hass, data),
        data,
        now=now,
    )
    _refresh_door_guard_status(hass, data, now=now)


def _schedule_door_guard_expiry(
    hass: HomeAssistant,
    entry_id: str,
    data: dict[str, Any],
    *,
    now: datetime | None = None,
) -> None:
    """Schedule a status refresh when the active cooldown expires."""

    cancel_timer = data.get("door_guard_cancel_timer")
    if callable(cancel_timer):
        cancel_timer()
    data["door_guard_cancel_timer"] = None
    deadline = _deadline_datetime(data.get("door_suppression_until"))
    if deadline is None or async_call_later is None:
        return
    now = now or datetime.now(timezone.utc)
    delay = max(0.0, (_as_utc(deadline) - _as_utc(now)).total_seconds())
    expected_deadline = data["door_suppression_until"]

    @callback
    def expire_door_guard(_now: datetime) -> None:
        _expire_door_guard(hass, entry_id, expected_deadline)

    data["door_guard_cancel_timer"] = async_call_later(
        hass,
        delay,
        expire_door_guard,
    )


@callback
def _expire_door_guard(
    hass: HomeAssistant,
    entry_id: str,
    expected_deadline: str | None,
    *,
    now: datetime | None = None,
) -> None:
    """Clear one still-current deadline and repaint diagnostic entities."""

    data = hass.data.get(DOMAIN, {}).get(entry_id)
    if data is None or data.get("door_suppression_until") != expected_deadline:
        return
    deadline = _deadline_datetime(expected_deadline)
    now = now or datetime.now(timezone.utc)
    if deadline is not None and _as_utc(deadline) > _as_utc(now):
        _schedule_door_guard_expiry(hass, entry_id, data, now=now)
        return
    data["door_suppression_until"] = None
    data["door_suppression_reason"] = None
    data["door_guard_cancel_timer"] = None
    _refresh_door_guard_status(hass, data, now=now)
    _publish_status_updated(hass, data)


def _active_door_suppression(
    hass: HomeAssistant,
    data: dict[str, Any],
    *,
    event_id: str,
    now: datetime | None = None,
) -> tuple[str | None, str | None]:
    """Return a last-moment approach suppression decision for playback."""

    if event_id != "front_door_approach":
        return None, None
    config: AnnouncementConfig = data["config"]
    resolution_reason, suppression_until, _warning = evaluate_door_guard(
        config,
        ResolverRuntime(
            states=_state_map(hass),
            door_suppression_until=data.get("door_suppression_until"),
            door_suppression_reason=data.get("door_suppression_reason"),
        ),
        now=now,
    )
    return resolution_reason, suppression_until


def _refresh_door_guard_status(
    hass: HomeAssistant,
    data: dict[str, Any],
    *,
    now: datetime | None = None,
) -> None:
    """Synchronise live door-guard diagnostics with current HA state."""

    config: AnnouncementConfig = data["config"]
    states = _state_map(hass)
    reason, suppression_until, warning = evaluate_door_guard(
        config,
        ResolverRuntime(
            states=states,
            door_suppression_until=data.get("door_suppression_until"),
            door_suppression_reason=data.get("door_suppression_reason"),
        ),
        now=now,
    )
    sensor_entity_id = config.door_guard.sensor_entity_id
    status = data["status"]
    status["approach_suppression_active"] = reason is not None
    status["approach_suppression_until"] = suppression_until
    status["approach_suppression_reason"] = reason
    status["door_guard_sensor_entity_id"] = sensor_entity_id
    status["door_guard_sensor_state"] = (
        states.get(sensor_entity_id) if sensor_entity_id else None
    )
    status["door_guard_warning"] = warning


def _start_approach_wait(
    hass: HomeAssistant,
    entry_id: str,
    data: dict[str, Any],
    *,
    now: datetime | None = None,
) -> None:
    """Start one continuous-presence wait after a clean sensor-on transition."""

    config: AnnouncementConfig = data["config"]
    delay_config = config.approach_delay
    if not delay_config.sensor_entity_id or data.get("approach_wait_until"):
        return
    approach_event = next(
        (event for event in config.events if event.id == EVENT_FRONT_DOOR_APPROACH),
        None,
    )
    if approach_event is None or not approach_event.enabled:
        return
    states = _state_map(hass)
    cancellation_reason = approach_wait_cancellation_reason(delay_config, states)
    if cancellation_reason:
        return
    door_reason, door_until = _active_door_suppression(
        hass,
        data,
        event_id=EVENT_FRONT_DOOR_APPROACH,
        now=now,
    )
    if door_reason:
        _record_approach_delay_suppression(
            hass,
            data,
            reason=door_reason,
            suppression_until=door_until,
        )
        return

    now = now or datetime.now(timezone.utc)
    wait_until = approach_wait_deadline(delay_config, now=now)
    data["approach_wait_started_at"] = now.isoformat()
    data["approach_wait_until"] = wait_until
    data["status"]["last_approach_wait_cancellation_reason"] = None
    cancel_timer = data.get("approach_wait_cancel_timer")
    if callable(cancel_timer):
        cancel_timer()
    data["approach_wait_cancel_timer"] = None

    if async_call_later is not None:
        deadline = _deadline_datetime(wait_until)
        delay = (
            max(0.0, (_as_utc(deadline) - _as_utc(now)).total_seconds())
            if deadline is not None
            else 0.0
        )

        @callback
        def complete_approach_wait(_now: datetime) -> None:
            _schedule_approach_completion(hass, entry_id, wait_until)

        data["approach_wait_cancel_timer"] = async_call_later(
            hass,
            delay,
            complete_approach_wait,
        )
    _refresh_approach_delay_status(hass, data)
    _publish_status_updated(hass, data)


@callback
def _schedule_approach_completion(
    hass: HomeAssistant,
    entry_id: str,
    expected_deadline: str,
) -> None:
    """Schedule the async completion check from a Home Assistant timer."""

    data = hass.data.get(DOMAIN, {}).get(entry_id)
    if data is None or data.get("approach_wait_until") != expected_deadline:
        return
    coroutine = _complete_approach_wait(hass, entry_id, expected_deadline)
    if hasattr(hass, "async_create_task"):
        hass.async_create_task(coroutine)
    else:
        hass.loop.create_task(coroutine)


async def _complete_approach_wait(
    hass: HomeAssistant,
    entry_id: str,
    expected_deadline: str,
) -> None:
    """Recheck every cancellation condition before automatic playback."""

    data = hass.data.get(DOMAIN, {}).get(entry_id)
    if data is None or data.get("approach_wait_until") != expected_deadline:
        return
    cancellation_reason = approach_wait_cancellation_reason(
        data["config"].approach_delay,
        _state_map(hass),
    )
    if cancellation_reason:
        _cancel_approach_wait(
            hass,
            data,
            reason=cancellation_reason,
            record=True,
        )
        return
    door_reason, door_until = _active_door_suppression(
        hass,
        data,
        event_id=EVENT_FRONT_DOOR_APPROACH,
    )
    if door_reason:
        _cancel_approach_wait(
            hass,
            data,
            reason=door_reason,
            suppression_until=door_until,
            record=True,
        )
        return

    _clear_approach_wait(data)
    data["status"]["last_approach_wait_cancellation_reason"] = None
    _refresh_approach_delay_status(hass, data)
    _publish_status_updated(hass, data)
    await hass.services.async_call(
        DOMAIN,
        SERVICE_PLAY,
        {CONF_EVENT_ID: EVENT_FRONT_DOOR_APPROACH},
        blocking=True,
    )


def _cancel_approach_wait(
    hass: HomeAssistant,
    data: dict[str, Any],
    *,
    reason: str,
    suppression_until: str | None = None,
    record: bool,
) -> bool:
    """Cancel one active wait without queueing or consuming duplicate history."""

    if not data.get("approach_wait_until"):
        return False
    _clear_approach_wait(data)
    data["status"]["last_approach_wait_cancellation_reason"] = reason
    _refresh_approach_delay_status(hass, data)
    if record:
        _record_approach_delay_suppression(
            hass,
            data,
            reason=reason,
            suppression_until=suppression_until,
        )
    else:
        _publish_status_updated(hass, data)
    return True


def _clear_approach_wait(data: dict[str, Any]) -> None:
    """Clear runtime-only delayed-Approach state."""

    cancel_timer = data.get("approach_wait_cancel_timer")
    if callable(cancel_timer):
        cancel_timer()
    data["approach_wait_cancel_timer"] = None
    data["approach_wait_started_at"] = None
    data["approach_wait_until"] = None


def _record_approach_delay_suppression(
    hass: HomeAssistant,
    data: dict[str, Any],
    *,
    reason: str,
    suppression_until: str | None,
) -> None:
    """Publish an intentional source-side suppression for diagnostics."""

    resolution = AnnouncementResolution(
        event_id=EVENT_FRONT_DOOR_APPROACH,
        ok=True,
        suppressed=True,
        suppression_reason=reason,
        suppression_until=suppression_until,
    )
    data["last_resolution"] = resolution
    _record_and_publish_status(hass, data, resolution, outcome="suppressed")
    fire_announcement_event(
        hass,
        ANNOUNCEMENT_EVENT_SUPPRESSED,
        resolution,
        source="approach_delay",
    )


def _refresh_approach_delay_status(
    hass: HomeAssistant,
    data: dict[str, Any],
) -> None:
    """Synchronise delayed-Approach diagnostics with current runtime state."""

    config = data["config"].approach_delay
    states = _state_map(hass)
    status = data["status"]
    status["approach_waiting"] = bool(data.get("approach_wait_until"))
    status["approach_wait_started_at"] = data.get("approach_wait_started_at")
    status["approach_wait_until"] = data.get("approach_wait_until")
    status["approach_delay_seconds"] = config.delay_seconds
    status["approach_delay_sensor_entity_id"] = config.sensor_entity_id
    status["approach_delay_sensor_state"] = (
        states.get(config.sensor_entity_id) if config.sensor_entity_id else None
    )
    status["approach_delay_warning"] = approach_sensor_warning(config, states)


def _deadline_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


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
            volume_multiplier=current_zones_by_entity.get(
                record.entity_id,
                ZoneConfig(record.entity_id),
            ).volume_multiplier,
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
