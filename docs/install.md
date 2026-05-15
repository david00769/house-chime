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

After adding the integration, open `Configure` and set:

- selected people
- selected announcement zones
- quiet hours and quiet-zone exclusions
- event enablement
- voice/media mappings
- trigger sounds
- bridge helper entities

## No-Audio Smoke Test

Use these services before live playback:

- `house_chime.discover`
- `house_chime.resolve`

Do not call `house_chime.play` or `house_chime.bridge_trigger` during quiet
hours unless an audible test is intended.

