# Install

## HACS Custom Repository

1. Open HACS in Home Assistant.
2. Open custom repositories.
3. Add the House Chime repository URL.
4. Select category `Integration`.
5. Install House Chime.
6. Restart Home Assistant.
7. Add the integration from `Settings -> Devices & services`.

For maintainers updating an existing HACS installation, follow the
[release and deployment runbook](releasing.md). It covers the reviewed commit,
upstream publication, HACS update, and safe post-update checks.

## Configure

After adding the integration, open `Configure`. House Chime exposes four
sections:

- `Household`: people and presence, priority and fallback context, and
  per-person playback preferences.
- `Announcements`: event controls, personalisation, and event-first voice media
  configuration. Each Approach, Package, and Doorbell form contains its enabled
  state, default voice, pre-sound, and duplicate window.
- `Playback`: Music Assistant speakers, shared daytime volume, per-speaker
  overrides, bedtime and quiet-hours behavior, and effective-volume summaries.
- `Rules & diagnostics`: door-aware Approach suppression and Review / Dry Run,
  including live door state, active reason, expiry, and readiness by event.

Keep configuration entry points out of operator dashboards. A House Chime
dashboard may show readiness, configured speaker status, presence/listener
status, generated per-person playback switches, dry-run buttons, and
intentional audible test buttons, but `Configure speakers` tiles or direct
configuration links belong in Devices & Services.

Shared speakers cannot make a broadcast inaudible to one physical person. A
person's playback switch means "do not use this person as a reason to play"
while they are home. If another present person has playback enabled, House
Chime plays once using that enabled person's personalisation. If everyone home
is muted, it records an intentional `all_present_people_muted` suppression.
The generated switches appear on the House Chime device page and can be added
to any dashboard without hard-coding names into this public package.

`People home`, `Enabled listeners home`, and `Muted listeners home` refresh
whenever a configured person or that person's fallback device tracker changes
state. To make these align with an existing household-presence policy, select
the same Home Assistant people in `Household people` and add the same trusted
trackers under each person's `Playback preferences`. House Chime does not use
dashboard cards or their templates as an input.

## Upload Media

House Chime does not upload or generate audio files. Use Home Assistant's
existing media flow:

1. Open Home Assistant Media.
2. Upload MP3 audio to Local Media, for example `announcements/front-door.mp3`.
3. Open `Settings -> Devices & services -> House Chime -> Configure ->
   Announcements -> Voice media`.
4. Select the uploaded files with the media picker.

If the media picker is unavailable in a Home Assistant version, enter a raw
path in the same event-first voice media form, such as:

```text
media-source://media_source/local/announcements/front-door.mp3
```

House Chime signs the selected Local Media URL at playback time before sending
it to Music Assistant. Keep using the normal HA Media upload flow; you do not
need to expose files manually under `/local`.

Before handoff, House Chime probes the playback URL. If Home Assistant would
reject the URL or the file cannot be fetched, the play service records a clear
failure and creates a Repair issue instead of reporting the announcement as
played.

Stock Lovelace buttons do not show service response bodies. When a manual play
button appears to do nothing, check the House Chime diagnostic entities first:

- `Last failure reason`
- `Last failed event`
- `Last resolution valid`

The House Chime Activity event entity is the most direct signal that a backend
service call actually ran. Status sensors refresh from a House Chime bus event
after `resolve`, `play`, and speaker updates; if the Activity event updates but
status sensors do not, reload the integration and update House Chime.

Then check `Settings -> Repairs` for House Chime issues. URL signing failures,
unreachable Local Media URLs, missing media, missing zones, and a missing Music
Assistant service are intended to show there. Incompatible speaker selections
also show there. For Music Assistant playback, select media players that support
Music Assistant announcements rather than Juke-native zone/control entities.
For Juke Audio AirPlay2 zones, select the Music Assistant-presented
`media_player` entities. House Chime hides unavailable players and raw
input/control entities that cannot be passed to `music_assistant.play_announcement`.

If a Repair says a selected speaker is missing or incompatible after a Home
Assistant, Music Assistant, restore, or device rediscovery event, re-open
`Configure -> Playback -> Speakers` and reselect the current Music Assistant
player. Saved `media_player` entity IDs can change over time. After the event
resolves cleanly, House Chime clears stale Repair issues for that event.

The Speakers form shows missing saved speakers and suggested current matches
when it can infer them from friendly names or entity IDs. Treat those
suggestions as review hints, not automatic migration. House Chime will not
replace a missing speaker unless you select the current entity before saving.
For scripted support workflows, `house_chime.set_speakers` can replace the
saved speaker list through HA Services while still rejecting unavailable or
incompatible targets.

`Selected target zones` is the saved configured speaker list. If an individual
event is suppressed or resolves to no playable targets, inspect the
last-resolution diagnostic detail instead of treating the configured speaker
summary as the per-event target list.

After a Home Assistant restart, House Chime should load automatically. If it
shows `not_loaded`, use `Settings -> Devices & services -> House Chime ->
Reload`, then check Home Assistant logs and Repairs. A manual reload should be a
temporary recovery step, not the normal operating model.

## No-Audio Smoke Test

Use these services before live playback:

- `house_chime.discover`
- `house_chime.resolve`

Use `house_chime.set_speakers` when the selected speaker list needs to be
repaired through HA Services. It accepts multiple `media_player` entities and
persists only currently compatible Music Assistant announcement targets.

Use `house_chime.set_playback_routes` when compatible targets still need
physical output zones switched to the matching input before audio is audible.
This is common with whole-home amplifiers where Music Assistant plays to an
input and separate media-player entities control which source each output zone
hears. Route rules are validated before they are saved, and stale routes fail
before playback so a play button does not report success while the amplifier is
listening to the wrong source.

Example route service data:

```yaml
playback_routes:
  - target_player_entity_id: media_player.whole_house
    source: Whole House
    zone_entity_ids:
      - media_player.great_room_zone
      - media_player.living_room_zone
```

The `Review / Dry Run` configuration step performs the same kind of non-audible
validation for all three built-in events.

Do not call `house_chime.play` during quiet hours unless an audible test is
intended.

Manual dashboard play-test buttons may pass
`skip_duplicate_suppression: true` so a deliberate repeat test is not blocked
by the event duplicate window. It never bypasses door-aware Approach
suppression. Leave that option off for real source automations.

## Door-aware Approach suppression

In `Configure -> Rules & diagnostics -> Door-aware approach suppression`,
select a front-door `binary_sensor` and set `After-door quiet time` from 0 to
3600 seconds. Leaving the sensor unselected disables this rule.

Approach announcements are dropped while this sensor is open and for the
configured time after it opens. Doorbell and package announcements continue.
House Chime does not queue, defer, or replay suppressed attempts, and those
attempts do not update duplicate-suppression history.

Every closed-to-open transition restarts the cooldown. Zero seconds means
open-door suppression only. A restart discards the prior deadline: if the door
is currently open, House Chime establishes a fresh cooldown; if closed, no
cooldown starts. A missing, unknown, or unavailable sensor fails open and is
reported as a configuration warning. An already-running cooldown remains
active.

Review / Dry Run reports the live door state, active reason, UTC expiry, and
event readiness. The integration device also exposes Approach suppression
active and Approach suppression until entities.

## Automation Pattern

Use the real source integration as the automation trigger, add House Chime
conditions when useful, then call `house_chime.play`.

Example shape:

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

Do not create `input_boolean` handoff helpers for package, approach, or doorbell
events. House Chime does not own source-event capture; it owns event resolution,
diagnostics, and playback.
