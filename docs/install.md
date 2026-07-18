# Install

## HACS Custom Repository

1. Open HACS in Home Assistant.
2. Open custom repositories.
3. Add the House Chime repository URL.
4. Select category `Integration`.
5. Install House Chime.
6. Restart Home Assistant.
7. Add the integration from `Settings -> Devices & services`.

## Configure

After adding the integration, open `Configure`. House Chime walks through:

- `People`: select Home Assistant people.
- `Priority`: rank the selected people.
- `Speakers`: select available Music Assistant announcement targets.
- `Sounds`: choose uploaded announcement and chime audio.
- `Events`: enable Approach, Package, and Doorbell and choose voices.
- `Quiet rules`: configure quiet hours and quiet volume.
- `Additional settings`: configure fallback trackers, duplicate windows,
  quiet-zone exclusions, and per-person chime overrides.
- `Review / Dry Run`: check the setup without playing audio.

Keep configuration entry points out of operator dashboards. A House Chime
dashboard may show readiness, configured speaker status, dry-run buttons, and
intentional audible test buttons, but `Configure speakers` tiles or direct
configuration links belong in Devices & Services.

## Upload Media

House Chime does not upload or generate audio files. Use Home Assistant's
existing media flow:

1. Open Home Assistant Media.
2. Upload MP3 audio to Local Media, for example `announcements/front-door.mp3`.
3. Open `Settings -> Devices & services -> House Chime -> Configure -> Sounds`.
4. Select the uploaded files with the media picker.

If the media picker is unavailable in a Home Assistant version, use Additional
settings raw paths such as:

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
`Configure -> Speakers` and reselect the current Music Assistant player. Saved
`media_player` entity IDs can change over time. After the event resolves
cleanly, House Chime clears stale Repair issues for that event.

The Speakers form shows missing saved speakers and suggested current matches
when it can infer them from friendly names or entity IDs. Treat those
suggestions as review hints, not automatic migration. House Chime will not
replace a missing speaker unless you select the current entity before saving.

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

The `Review / Dry Run` configuration step performs the same kind of non-audible
validation for all three built-in events.

Do not call `house_chime.play` during quiet hours unless an audible test is
intended.

Manual dashboard play-test buttons may pass
`skip_duplicate_suppression: true` so a deliberate repeat test is not blocked
by the event duplicate window. Leave that option off for real source
automations.

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
