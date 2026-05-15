"""Diagnostics support for House Chime."""

from __future__ import annotations

from typing import Any

from .const import DOMAIN


async def async_get_config_entry_diagnostics(hass: Any, entry: Any) -> dict[str, Any]:
    """Return non-secret integration diagnostics."""

    data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    config = data.get("config")
    last_resolution = data.get("last_resolution")
    return {
        "entry_id": entry.entry_id,
        "config_version": getattr(config, "version", None),
        "people_count": len(getattr(config, "people", [])) if config else 0,
        "zones_count": len(getattr(config, "zones", [])) if config else 0,
        "voices_count": len(getattr(config, "voices", [])) if config else 0,
        "events_count": len(getattr(config, "events", [])) if config else 0,
        "last_resolution": last_resolution.to_dict() if last_resolution else None,
    }
