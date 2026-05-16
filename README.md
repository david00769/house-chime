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

## Guided Setup

After installation, open `Settings -> Devices & services -> House Chime ->
Configure`.

The setup flow is intentionally operator-focused:

- `People`: choose Home Assistant `person.*` entities.
- `Priority`: rank who should drive the active household context.
- `Speakers`: choose recommended Music Assistant/Juke announcement targets.
- `Sounds`: select already-uploaded chime and announcement audio.
- `Events`: enable and map voices for Approach, Package, and Doorbell.
- `Quiet rules`: set quiet hours and quiet volume.
- `Advanced`: fallback trackers, bridge helpers, duplicate windows, quiet-zone
  exclusions, and per-person chime overrides.
- `Review / Dry Run`: validate the setup without playing audio.

Diagnostics remain available, but they are not part of the default setup path.

## Media

House Chime consumes approved playable files that already exist in Home
Assistant local media. It does not create announcement audio.

V1 uses Home Assistant's built-in media upload/browser path:

1. Open Home Assistant Media.
2. Upload audio into Local Media, for example under `announcements/`.
3. Return to House Chime `Configure -> Sounds`.
4. Select the uploaded media in the media picker.

Advanced users can still provide raw `media-source://media_source/local/...`
paths where Home Assistant's media selector is not available. Example:

```text
media-source://media_source/local/announcements/front-door.mp3
```

At playback time, House Chime converts selected Home Assistant Local Media paths
into short-lived signed URLs before calling Music Assistant. This lets
server-side players fetch the audio without requiring operators to make the
media folder public.

House Chime also probes the signed playback URL before calling Music Assistant.
If the URL is not reachable, playback is stopped and the dashboard diagnostics
show a failure instead of recording a false success.

## Events

The initial public events are:

- Approach
- Package
- Doorbell

Internal event IDs are still used by services and automations, but the setup UI
uses the friendly names above.

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
