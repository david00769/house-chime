# Playback Compatibility

House Chime currently uses Music Assistant's `music_assistant.play_announcement`
service for playback.

For Home Assistant Local Media, House Chime signs the `/media/local/...` URL
with Home Assistant's content-user signing helper, probes that signed URL, and
only then calls Music Assistant. If signing or probing fails, playback is
stopped and the failure is exposed through House Chime diagnostics and Home
Assistant Repairs.

House Chime also checks the selected speaker targets before the Music Assistant
handoff. The targets must be available Music Assistant `media_player` entities
that match the `music_assistant.play_announcement` target requirements. Juke
AirPlay2 zones are supported through their Music Assistant-presented players.
Juke-native input/control entities can still be useful for the broader audio
system, but they are not valid House Chime targets unless Music Assistant
exposes them with the announcement features.

Saved speaker selections are Home Assistant entity IDs. Music Assistant,
Home Assistant, restore, or device rediscovery changes can retire an old
`media_player` ID and create a replacement with the same friendly name. When
that happens, House Chime fails before playback and creates a Repair instead of
silently playing to only part of the configured target set. Reselect the current
Music Assistant speaker in House Chime options, then run `house_chime.resolve`
or `Review / Dry Run`; successful resolution clears stale event-level Repairs.
The Speakers form may suggest current entities with similar names, but it does
not auto-remap them. The operator must confirm the intended target by selecting
it.

## Tested

- Juke Audio AirPlay2 zones through Music Assistant

## Untested

These may become supported after adapter-specific testing:

- Sonos through Music Assistant
- AirPlay/HomePods through Music Assistant
- Google Cast through Music Assistant
- Snapcast through Music Assistant
- DLNA through Music Assistant
- native Home Assistant `media_player.play_media`
- native Sonos services
- native Cast services

Do not describe an audio system as supported until it has a real playback test
and documented restore behavior.
