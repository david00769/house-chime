"""Media-source validation helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import unquote

from .models import AnnouncementResolution

LOCAL_MEDIA_PREFIX = "media-source://media_source/local/"


def configured_media_paths(resolution: AnnouncementResolution) -> list[str]:
    """Return configured media-source paths used by a resolution."""

    paths = []
    if resolution.media_path:
        paths.append(resolution.media_path)
    if resolution.trigger_sound_path:
        paths.append(resolution.trigger_sound_path)
    return paths


async def async_available_media_for_resolution(
    hass: Any,
    resolution: AnnouncementResolution,
) -> set[str]:
    """Return the subset of configured media paths that currently exists."""

    available: set[str] = set()
    for media_path in configured_media_paths(resolution):
        if await async_media_exists(hass, media_path):
            available.add(media_path)
    return available


async def async_media_exists(hass: Any, media_path: str) -> bool:
    """Check whether a configured HA media path exists."""

    if media_path.startswith(LOCAL_MEDIA_PREFIX):
        relative_path = unquote(media_path.removeprefix(LOCAL_MEDIA_PREFIX))
        return any(path.exists() for path in _local_media_candidates(hass, relative_path))

    try:
        from homeassistant.components import media_source

        await media_source.async_resolve_media(hass, media_path, None)
    except Exception:
        return False
    return True


def _local_media_candidates(hass: Any, relative_path: str) -> list[Path]:
    relative = Path(relative_path)
    candidates = [Path("/media") / relative]
    config = getattr(hass, "config", None)
    if config is not None and hasattr(config, "path"):
        candidates.append(Path(config.path("media")) / relative)
        candidates.append(Path(config.path()) / "media" / relative)
    return candidates
