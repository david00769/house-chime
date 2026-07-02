# House Chime

House Chime is a Home Assistant custom integration for household audio
announcements.

It discovers Home Assistant people and playback zones, then
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

Use `resolve` for dry runs. Use `play` for manual announcements. Use
`play` from automations whose triggers come from the real source integration,
for example a doorbell, camera, presence, or package-delivery integration.
House Chime does not create or reset helper entities.

House Chime also exposes purpose-specific automation conditions for readiness,
event enablement, event resolution, and quiet mode, plus an Activity event
entity and `house_chime_event` bus event for follow-up automations after a
resolve/play/failure.

## Automation Model

House Chime is not a source-event bridge. Automations should start from the
real source integration and call House Chime as the announcement action:

```yaml
triggers:
  - trigger: event
    event_type: source_integration_package_detected
conditions:
  - condition: house_chime.ready
  - condition: house_chime.event_enabled
    options:
      event_id: front_door_package
actions:
  - action: house_chime.play
    data:
      event_id: front_door_package
```

Use the `house_chime.announcement_activity` trigger only for follow-up
automations after House Chime resolves, plays, or fails an announcement.

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
- `Additional settings`: fallback trackers, duplicate windows, quiet-zone
  exclusions, and per-person chime overrides.
- `Review / Dry Run`: validate the setup without playing audio.

Diagnostics remain available, but they are not part of the default setup path.

Do not add House Chime configuration links or `Configure speakers` tiles to an
operator dashboard. Dashboards should show readiness, saved speaker status,
dry-run actions, and intentional play actions. Setup belongs in Home Assistant
`Settings -> Devices & services -> House Chime -> Configure`.

`Selected target zones` reports the saved configured speaker list. It is not
the same thing as the per-event resolved playback target list after quiet rules,
duplicate suppression, unavailable speakers, or validation. Use the
last-resolution diagnostic detail when troubleshooting a specific event.

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

If playback fails, check the `Last failure reason` diagnostic first, then Home
Assistant `Settings -> Repairs`. Stock Lovelace buttons do not display service
response bodies, so House Chime reports friendly operator warnings through its
diagnostic entities and Repair issues instead of relying on a button pop-up.
URL signing/auth failures are reported before Music Assistant is called.
Selected speakers are also checked before handoff. If a Juke-native control
entity or other media player cannot accept `music_assistant.play_announcement`,
House Chime records an incompatible-target failure instead of reporting a false
success.

If the speaker selector shows several identical friendly names, use the entity
ID suffix in the option label to distinguish the actual media players.

Music Assistant and Home Assistant can rename or recreate `media_player`
entities after integration updates, device rediscovery, or restoring a backup.
If House Chime reports a selected speaker as missing or incompatible, open
`Settings -> Devices & services -> House Chime -> Configure -> Speakers` and
reselect the current Music Assistant player. A successful dry run clears stale
House Chime Repair issues for that event.

When saved speakers are missing, the Speakers form lists the stale entity IDs
and shows best-effort current matches by friendly name or entity ID. These are
operator review hints only. House Chime does not automatically remap speakers
because friendly names and areas are not unique enough to guarantee the intended
playback target.

## Events

The initial public events are:

- Approach
- Package
- Doorbell

Internal event IDs are still used by service actions and direct source
automations, but the setup UI uses the friendly names above.

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
