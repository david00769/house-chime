# House Chime

House Chime is a Home Assistant custom integration for household audio
announcements.

It discovers Home Assistant people, playback zones, and helper entities, then
resolves each configured event into a media file, target zones, volume, quiet
rules, duplicate suppression, and diagnostics. Playback currently uses Music
Assistant's `music_assistant.play_announcement` service.

## Current Support

Tested playback path:

- Juke Audio through Music Assistant

Other Music Assistant-backed speakers may work, but they are not tested yet.
Native Sonos, Cast, AirPlay, DLNA, and generic `media_player.play_media` support
are not supported until adapter-specific testing exists.

## Installation

Install as a HACS custom repository:

1. Open HACS.
2. Add this repository as a custom integration repository.
3. Install House Chime.
4. Restart Home Assistant.
5. Go to `Settings -> Devices & services -> Add integration -> House Chime`.

## Services

House Chime registers:

- `house_chime.discover`
- `house_chime.resolve`
- `house_chime.play`
- `house_chime.bridge_trigger`

Use `resolve` for dry runs. Use `play` for manual announcements. Use
`bridge_trigger` for external helper-driven automations that should reset a
helper after handling an event.

## Media

House Chime consumes approved playable files that already exist in Home
Assistant local media. It does not create announcement audio.

Use `media-source://media_source/local/...` paths in the options flow. Example:

```text
media-source://media_source/local/announcements/front-door.mp3
```

## Events

The initial event IDs are:

- `front_door_approach`
- `front_door_package`
- `front_door_doorbell`

## Development

```bash
uv sync --extra dev
uv run python scripts/check_hacs_structure.py
uv run pytest tests
uv run python -m unittest discover -s tests
```

## Release Status

This is an early beta integration. Run dry-run resolution and non-audible
configuration checks first. Do not run live playback tests during quiet hours.

## Public Repo Boundary

This repository is the public HACS package boundary. Do not commit
house-specific Home Assistant entity IDs, local IP addresses, deployment logs,
screenshots, generated audio, voice profiles, or private testing notes here.

Keep private project memory in the ignored `project-memory/` folder or in the
separate private planning workspace.
