# House Chime v0.5.0 release-readiness plan

## Outcome

Approach announcements should describe a genuinely lingering visitor, not the
same encounter already represented by a door opening or a Doorbell event. The
release is ready only when the integration owns that policy end to end, presents
it clearly in Home Assistant's native configuration UI, and proves it through
repeatable tests and upstream validation.

## Operator-visible behaviour

1. A configured person-presence binary sensor turns on.
2. House Chime waits for the configured continuous-presence duration (30 seconds
   by default).
3. The pending Approach is cancelled if the person leaves, the front door opens,
   or a Doorbell event is received.
4. Opening the door or receiving a Doorbell event starts the same configurable
   encounter quiet time (180 seconds by default). New Approach detections during
   that window are suppressed.
5. Package and Doorbell announcements are never delayed.
6. Source automations call `house_chime.ingest_event`. `house_chime.play` remains
   an explicit operator-only **Play now** bypass for testing and dashboards.

## Architecture and reuse

The sensor-specific configuration remains backward compatible, while pure
runtime decisions are expressed as a reusable pending-announcement policy:
event ID, trigger entity, hold duration, cancellation events, trigger state,
and encounter suppression duration. The Approach options are an adapter for
that policy rather than one-off timing logic. The Home Assistant listener,
status entity, and service adapter deliberately remain Approach-specific until
a second delayed event proves the right generic runtime-controller shape; this
avoids a premature framework while keeping policy decisions reusable and tested.

Only configured people, person-presence, and front-door entities are listened to.
Entry runtime state is attached to `ConfigEntry.runtime_data` and mirrored in
`hass.data` only for platform/service compatibility.

## Delivery gates

- [x] Encounter policy: Doorbell and door-open events cancel an active wait and
  suppress re-arming for the configured quiet time.
- [x] Deadline safety: every cancellation condition is rechecked immediately
  before automatic dispatch; stale timer callbacks cannot play.
- [x] Service contract: automations use policy-aware `ingest_event`; `play` is
  clearly documented as an immediate manual bypass.
- [x] Native UX: the setup page explains both timers, defaults, cancellation
  rules, and the upgrade action in plain language.
- [x] Repairs: missing delayed-Approach setup and invalid/unavailable sensors
  surface as actionable Home Assistant Repair issues.
- [x] Diagnostics: entity values use friendly labels, timestamp/status metadata,
  a House Chime device, and no stale cancellation reason.
- [x] Tests: pure policy, encounter races, timer lifecycle, reload/unload,
  migration, config-flow, and service-ingress paths are covered.
- [ ] Upstream gates: local tests, lint, JSON/YAML validation, compilation, and
  diff checks pass; HACS validation and hassfest are configured and must pass in
  the upstream pull request.
- [x] Documentation: README, install/upgrade, automation examples, dashboard,
  release checklist, changelog, and private design records agree.

## Landing sequence

1. Complete and validate this scoped v0.5.0 change set locally.
2. Review the complete diff and any automated review findings.
3. Commit to `codex/approach-loiter-delay` and open a pull request when explicitly
   authorized.
4. Require green CI/HACS/hassfest checks and review approval before merge.
5. Tag and publish v0.5.0, then upgrade through HACS.
6. Configure both sensors/timers, replace legacy immediate Approach automations
   with `house_chime.ingest_event`, and run the documented live acceptance test.

Commit, push, release, HACS installation, and live-home changes are deliberately
outside local implementation and require separate authorization.
