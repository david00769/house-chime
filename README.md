# House Chime

House Chime is a Home Assistant custom integration for household audio
announcements.

It discovers Home Assistant people and playback zones, then
resolves each configured event into a media file, target zones, volume, quiet
rules, duplicate suppression, and diagnostics. Playback currently uses Music
Assistant's `music_assistant.play_announcement` service.

## Current Support

Tested playback path:

- Juke Audio AirPlay2 zones through Music Assistant

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
- `house_chime.ingest_event`
- `house_chime.play`
- `house_chime.set_speakers`
- `house_chime.set_playback_routes`
- `house_chime.set_person_playback`

Use `resolve` for dry runs, `ingest_event` for Package and Doorbell source
automations, and `play` as the explicit **Play now** operator action. Manual
operator test buttons may pass `skip_duplicate_suppression: true` so repeated
tests are not blocked by the event duplicate window. Do not use that flag in
real source automations.

Use `ingest_event` from the real source automation for **Package** and
**Doorbell** events. Configure the person-presence sensor directly in House
Chime for an automatic **Approach** announcement. The configured sensor is
already an Approach trigger, so do not also call either `house_chime.ingest_event`
or `house_chime.play` from an automation triggered by that same sensor. Doing
so creates competing paths for one encounter and can bypass the intended
loitering policy. House Chime does not create, reset, or infer helper entities.

For the current Approach safe hold, Google Home / Nest source limitation, and
the required continuous-presence infrastructure, see [Front-door event
routing](docs/front-door-event-routing.md). Approach remains disabled until a
source can report both person-present and person-left state, rather than a
one-shot detection event.

Use `set_speakers` from HA Services when an operator or support workflow needs
to replace the saved speaker list without opening the options form. The service
accepts a list of `media_player` entity IDs and persists only currently
available Music Assistant announcement targets. Stale, unavailable, raw input,
or non-Music-Assistant entities are rejected and the existing speaker selection
is left unchanged.

Use `set_playback_routes` when the audio system needs its physical output zones
switched to the selected announcement input before Music Assistant plays. Each
saved route maps one compatible announcement target to a source name and the
output-zone entities that should select that source. For example, selecting a
`media_player.whole_house` Music Assistant target can route several amplifier
zones to source `Whole House` before playback. Route updates are validated
against current Home Assistant state and are not persisted if a target, output
zone, or requested source is unavailable or incompatible.

House Chime also exposes purpose-specific automation conditions for readiness,
event enablement, event resolution, and quiet mode, plus an Activity event
entity and `house_chime_event` bus event for follow-up automations after a
resolve/play/failure.

## Automation Model

House Chime is not a source-event bridge. Automations start from the real source
integration and use House Chime's policy-aware ingress as the announcement action:

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
  - action: house_chime.ingest_event
    data:
      event_id: front_door_package
```

Leave `skip_duplicate_suppression` unset or `false` in real source automations
so duplicate doorbell/camera/package events are still suppressed. This option
does not bypass door-aware Approach suppression.

Doorbell source automations call `house_chime.ingest_event` with
`front_door_doorbell`. Receiving that event cancels any pending delayed
Approach before Doorbell resolution, including when the Doorbell event is later
duplicate-suppressed, and starts the configured encounter quiet time.

Use the `house_chime.announcement_activity` trigger only for follow-up
automations after House Chime resolves, plays, or fails an announcement.

## Guided Setup

After installation, open `Settings -> Devices & services -> House Chime ->
Configure`.

The setup flow has four Home Assistant-native sections:

- `Household`: people and presence, priority and fallback context, and
  per-person playback preferences.
- `Announcements`: Approach, Package, and Doorbell controls; per-person
  personalisation; and event-first voice media configuration. Each event form
  contains its enabled state, default voice, pre-sound, and duplicate window.
- `Playback`: speakers, shared daytime volume, per-speaker overrides, bedtime
  and quiet-hours behavior, and effective-volume summaries.
- `Rules & diagnostics`: Approach timing & suppression and Review / Dry Run
  readiness, including the person-presence wait, live door state, cancellation
  reason, and expiry.

Diagnostics remain available, but they are not part of the default setup path.

Do not add House Chime configuration links or `Configure speakers` tiles to an
operator dashboard. Dashboards should show readiness, saved speaker status,
presence/listener status, generated per-person playback switches, dry-run
actions, and intentional play actions. Setup belongs in Home Assistant
`Settings -> Devices & services -> House Chime -> Configure`.

When more than one person is home, House Chime plays once if any present person
has playback enabled. It chooses the highest-priority enabled person for the
voice and pre-sound. A muted person does not silence another enabled person. If
all present people are muted, House Chime intentionally suppresses playback and
records `all_present_people_muted` rather than a playback failure. When nobody
is home, existing behavior is retained: House Chime resolves the configured
fallback context and can still play.

House Chime creates one playback switch for every configured person. The
switches appear automatically on the integration device page. The bundled
Lovelace example does not list them so it remains portable; add the generated
switches to a household dashboard from the device page.

Presence/listener status is live: it refreshes when a configured `person.*`
entity or one of that person's configured fallback `device_tracker.*` entities
changes state. Configure the same people and trusted fallback trackers that
define the household's presence policy. House Chime deliberately does not read
or infer presence from a Lovelace card, template, or dashboard label.

`Selected target zones` reports the saved configured speaker list. It is not
the same thing as the per-event resolved playback target list after quiet rules,
duplicate suppression, unavailable speakers, or validation. Use the
last-resolution diagnostic detail when troubleshooting a specific event.

Status sensors also listen for House Chime status-update bus events so
dashboards repaint after services such as `play`, `resolve`, and
`set_speakers`.

## Delayed Approach and door-aware suppression

Open `Configure -> Rules & diagnostics -> Approach timing & suppression`.
Select a person-presence `binary_sensor` that remains `on` while someone is at
the front door, then set `Wait before announcing` from 0 to 300 seconds. The
default is 30 seconds. The Approach announcement runs only if that sensor stays
continuously `on` for the whole wait.

A pending Approach is cancelled if the person sensor turns off, becomes
unknown or unavailable, the configured front door opens, or a Doorbell event
arrives. Cancellation is final: House Chime does not queue or replay the
announcement, and the cancelled attempt does not consume the duplicate window.
Repeated `on` updates do not restart an active wait.

The configured sensor is the automatic delayed-Approach trigger. Remove or
disable any automation that calls **either** `house_chime.ingest_event` or
`house_chime.play` in response to that same sensor. Manual, deliberate
`house_chime.play` calls for Approach remain immediate for operator tests and
backwards compatibility.

`house_chime.ingest_event` deliberately rejects `front_door_approach`.
Automatic Approach is started only by the configured continuous person sensor;
Package and Doorbell are the supported automatic source-event inputs.

On the same screen, select the front-door `binary_sensor` and set
`After-door or Doorbell quiet time` from 0 to 3600 seconds. The existing default is 180
seconds (3 minutes). Leaving either sensor unselected disables only its
corresponding rule.

Approach announcements are dropped while the door sensor is open and for the
configured time after it opens or a Doorbell event arrives. Doorbell and package
announcements continue.
Suppressed attempts are never queued or replayed when the door closes or the
timer expires, and they do not consume the duplicate window.

Every closed-to-open transition and Doorbell event restarts the cooldown. A
zero-second cooldown suppresses only while the door remains open. After a Home Assistant restart,
an open door starts a fresh cooldown; a closed door starts with no retained
cooldown. Missing, unknown, or unavailable sensors fail open and create a
configuration warning, while a cooldown already in progress remains effective.

House Chime checks the guard again before each grouped Music Assistant
dispatch. If no group has played, cancellation is reported as intentional
suppression. If an earlier group was already accepted, remaining groups are
cancelled and diagnostics record a partial-dispatch warning.

The integration device exposes
`binary_sensor.house_chime_approach_waiting`,
`sensor.house_chime_approach_wait_until`,
`binary_sensor.house_chime_approach_suppression_active` and
`sensor.house_chime_approach_suppression_until` for dashboards and
troubleshooting. Pending waits are runtime-only and are discarded on
integration reload or Home Assistant restart; an already-on person sensor does
not generate a stale announcement after startup.

## Media

House Chime consumes approved playable files that already exist in Home
Assistant local media. It does not create announcement audio.

V1 uses Home Assistant's built-in media upload/browser path:

1. Open Home Assistant Media.
2. Upload audio into Local Media, for example under `announcements/`.
3. Return to House Chime `Configure -> Announcements -> Voice media`.
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

For Juke Audio, select the AirPlay2 zone entities as Music Assistant presents
them. Do not select raw Juke input/control entities or stale direct AirPlay
entities; the House Chime selector hides unavailable players and entities that
do not match Music Assistant's announcement target requirements.

If Juke output zones must be switched to the selected AirPlay2 input before
audio is audible, configure playback routes with `house_chime.set_playback_routes`.
Routes are generic data, not house-specific code: one route can map the selected
Music Assistant target to a single output zone, and another can map a whole-house
target to multiple output zones. House Chime applies only the routes for the
targets selected in the current announcement.

Music Assistant and Home Assistant can rename or recreate `media_player`
entities after integration updates, device rediscovery, or restoring a backup.
If House Chime reports a selected speaker as missing or incompatible, open
`Settings -> Devices & services -> House Chime -> Configure -> Playback ->
Speakers` and reselect the current Music Assistant player. A successful dry
run clears stale House Chime Repair issues for that event.

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

For the reviewed local commit, eventual upstream push/tag, HACS update, and
post-update validation sequence, use [the release and deployment
runbook](docs/releasing.md).

## Public Repo Boundary

This repository is the public HACS package boundary. Do not commit
house-specific Home Assistant entity IDs, local IP addresses, deployment logs,
screenshots, generated audio, voice profiles, or private testing notes here.

Keep private project memory in the ignored `project-memory/` folder or in the
separate private planning workspace.
