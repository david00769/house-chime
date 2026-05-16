# Playback Compatibility

House Chime currently uses Music Assistant's `music_assistant.play_announcement`
service for playback.

For Home Assistant Local Media, House Chime signs the `/media/local/...` URL
with Home Assistant's content-user signing helper, probes that signed URL, and
only then calls Music Assistant. If signing or probing fails, playback is
stopped and the failure is exposed through House Chime diagnostics and Home
Assistant Repairs.

## Tested

- Juke Audio through Music Assistant

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
