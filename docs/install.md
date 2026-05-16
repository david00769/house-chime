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
- `Speakers`: select recommended Music Assistant/Juke targets.
- `Sounds`: choose uploaded announcement and chime audio.
- `Events`: enable Approach, Package, and Doorbell and choose voices.
- `Quiet rules`: configure quiet hours and quiet volume.
- `Advanced`: configure fallback trackers, bridge helpers, duplicate windows,
  quiet-zone exclusions, and per-person chime overrides.
- `Review / Dry Run`: check the setup without playing audio.

## Upload Media

House Chime does not upload or generate audio files. Use Home Assistant's
existing media flow:

1. Open Home Assistant Media.
2. Upload MP3 audio to Local Media, for example `announcements/front-door.mp3`.
3. Open `Settings -> Devices & services -> House Chime -> Configure -> Sounds`.
4. Select the uploaded files with the media picker.

If the media picker is unavailable in a Home Assistant version, use Advanced
raw paths such as:

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

## No-Audio Smoke Test

Use these services before live playback:

- `house_chime.discover`
- `house_chime.resolve`

The `Review / Dry Run` configuration step performs the same kind of non-audible
validation for all three built-in events.

Do not call `house_chime.play` or `house_chime.bridge_trigger` during quiet
hours unless an audible test is intended.
