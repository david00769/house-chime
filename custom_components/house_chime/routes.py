"""Playback source routing helpers."""

from __future__ import annotations

import logging
from typing import Any, Iterable

from .discovery import (
    DiscoveredEntity,
    UNAVAILABLE_STATES,
    discover_media_players,
    is_selectable_announcement_player,
)
from .models import AnnouncementConfig, AnnouncementResolution, PlaybackRouteConfig

_LOGGER = logging.getLogger(__name__)

MEDIA_PLAYER_SELECT_SOURCE_FEATURE = 2048


def normalise_playback_routes(
    route_data: Iterable[dict[str, Any]],
) -> tuple[list[PlaybackRouteConfig], list[str]]:
    """Convert service route data into config models."""

    routes: list[PlaybackRouteConfig] = []
    errors: list[str] = []
    seen_targets: set[str] = set()
    for item in route_data:
        target_player_entity_id = str(item.get("target_player_entity_id") or "").strip()
        source = str(item.get("source") or "").strip()
        zone_entity_ids = list(
            dict.fromkeys(
                str(entity_id).strip()
                for entity_id in item.get("zone_entity_ids", [])
                if str(entity_id).strip()
            )
        )
        if not target_player_entity_id:
            errors.append("invalid_playback_route:missing_target")
            continue
        if target_player_entity_id in seen_targets:
            errors.append(f"duplicate_playback_route_target:{target_player_entity_id}")
            continue
        seen_targets.add(target_player_entity_id)
        if not source:
            errors.append(f"invalid_playback_route_source:{target_player_entity_id}:empty")
            continue
        if not zone_entity_ids:
            errors.append(f"invalid_playback_route_zones:{target_player_entity_id}:empty")
            continue
        routes.append(
            PlaybackRouteConfig(
                target_player_entity_id=target_player_entity_id,
                source=source,
                zone_entity_ids=zone_entity_ids,
            )
        )
    return routes, errors


def validate_playback_routes(hass: Any, routes: Iterable[PlaybackRouteConfig]) -> list[str]:
    """Validate route config against the current Home Assistant state."""

    states = {state.entity_id: state for state in hass.states.async_all()}
    selectable_target_ids = {
        record.entity_id
        for record in discover_media_players(states.values())
        if is_selectable_announcement_player(record)
    }
    errors: list[str] = []
    for route in routes:
        if route.target_player_entity_id not in selectable_target_ids:
            errors.append(f"incompatible_route_target:{route.target_player_entity_id}")
        errors.extend(_validate_route_zones(states, route))
    return errors


async def apply_playback_routes(
    hass: Any,
    config: AnnouncementConfig,
    resolution: AnnouncementResolution,
) -> list[str]:
    """Apply source routes for the targets selected by this resolution."""

    routes_by_target = {
        route.target_player_entity_id: route
        for route in config.playback_routes
    }
    selected_routes = [
        routes_by_target[entity_id]
        for entity_id in resolution.target_player_entity_ids
        if entity_id in routes_by_target
    ]
    if not selected_routes:
        return []

    states = {state.entity_id: state for state in hass.states.async_all()}
    errors: list[str] = []
    for route in selected_routes:
        route_errors = _validate_route_zones(states, route)
        if route_errors:
            errors.extend(route_errors)
            continue
        for zone_entity_id in route.zone_entity_ids:
            state = states[zone_entity_id]
            current_source = (state.attributes or {}).get("source")
            if current_source == route.source:
                continue
            try:
                await hass.services.async_call(
                    "media_player",
                    "select_source",
                    {"entity_id": zone_entity_id, "source": route.source},
                    blocking=True,
                )
            except Exception as err:
                _LOGGER.exception(
                    "Failed to route %s to source %s for announcement target %s",
                    zone_entity_id,
                    route.source,
                    route.target_player_entity_id,
                )
                errors.append(
                    "playback_route_failed:"
                    f"{route.target_player_entity_id}:{zone_entity_id}:{type(err).__name__}"
                )
    return errors


def _validate_route_zones(
    states: dict[str, Any],
    route: PlaybackRouteConfig,
) -> list[str]:
    errors: list[str] = []
    for zone_entity_id in route.zone_entity_ids:
        state = states.get(zone_entity_id)
        if state is None:
            errors.append(
                f"invalid_route_zone:{route.target_player_entity_id}:{zone_entity_id}:missing"
            )
            continue
        if state.state in UNAVAILABLE_STATES:
            errors.append(
                "invalid_route_zone:"
                f"{route.target_player_entity_id}:{zone_entity_id}:{state.state}"
            )
            continue
        attributes = dict(state.attributes or {})
        record = DiscoveredEntity(
            entity_id=zone_entity_id,
            name=str(attributes.get("friendly_name") or zone_entity_id),
            state=state.state,
            attributes=attributes,
        )
        if not _supports_source_selection(record):
            errors.append(
                "invalid_route_zone:"
                f"{route.target_player_entity_id}:{zone_entity_id}:missing_select_source"
            )
            continue
        source_list = attributes.get("source_list")
        if source_list and route.source not in source_list:
            errors.append(
                "invalid_route_source:"
                f"{route.target_player_entity_id}:{zone_entity_id}:{route.source}"
            )
    return errors


def _supports_source_selection(record: DiscoveredEntity) -> bool:
    try:
        supported_features = int(record.attributes.get("supported_features") or 0)
    except (TypeError, ValueError):
        supported_features = 0
    return bool(
        supported_features & MEDIA_PLAYER_SELECT_SOURCE_FEATURE
        or record.attributes.get("source_list")
    )
