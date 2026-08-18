# Changelog

## Unreleased

- Document the dated Approach safe hold: automatic Approach remains disabled
  until Google / Nest or another supported source provides a dedicated,
  continuous person-present / person-left state, rather than a one-shot person
  detection event.
- Document that a Google Home Script Editor `assistant.command.OkGoogle` action
  on a speaker or display is an audible voice-command route, not a Home
  Assistant event bridge; leave an unrecognised person-event routine disabled.

## 0.6.1

- Clear the configured person-presence sensor whenever an operator disables
  Approach, making the safe hold explicit in both route state and configuration.

## 0.6.0

- Make automatic Approach direct-sensor-only: `house_chime.ingest_event` now
  rejects `front_door_approach` with `approach_direct_sensor_only`.
- Keep Package and Doorbell as the only automatic source-event ingress, so a
  one-shot person-detection event cannot be mistaken for continuous loitering.
- Clarify service, Repairs, options-flow, installation, release, and routing
  guidance for continuous person presence, safe-hold deployments, and legacy
  Approach automation migration.

## 0.5.0

- Add configurable delayed automatic Approach announcements, defaulting to 30
  seconds of continuous person-presence detection.
- Cancel a pending Approach when the person leaves, the front door opens, or a
  Doorbell event arrives, without queueing, replaying, or consuming duplicate
  history.
- Make the existing 180-second encounter quiet time explicit and editable on
  the same native Home Assistant options screen; both door-open and Doorbell
  events start it so the person sensor cannot immediately re-arm.
- Add `house_chime.ingest_event` as the policy-aware service for source
  automations and present `house_chime.play` as the explicit Play now bypass.
- Use targeted entity listeners, config-entry runtime data, native diagnostic
  device metadata, friendly reason labels, and actionable sensor/setup Repairs.
- Add Ruff, coverage, HACS, hassfest, and real Home Assistant lifecycle gates.
- Add Approach waiting, wait deadline, sensor health, and last-cancellation
  diagnostics.
- Migrate stored announcement configuration from schema v4 to v5 while
  preserving the existing door sensor and cooldown.

## 0.4.0

- Add door-aware suppression for Approach announcements while a configured
  binary sensor is open and during a configurable post-open cooldown.
- Migrate stored announcement configuration from schema v3 to v4 without
  changing existing people, event, media, speaker, quiet-hours, or volume data.
- Drop suppressed Approach attempts without queueing, replaying, or consuming
  duplicate-suppression history.
- Recheck the door guard before each Music Assistant volume group and report
  partial dispatch when a later group is cancelled.
- Add Approach suppression active and suppression-until diagnostic entities.
- Consolidate the options flow into Household, Announcements, Playback, and
  Rules & diagnostics.
- Move event enablement, voice, pre-sound, and duplicate-window controls into
  each event form.
- Include the previously unreleased shared and per-speaker volume controls.
