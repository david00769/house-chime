# Changelog

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
