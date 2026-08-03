# House Chime v0.6.0 release readiness

## Behavioural contract

- `house_chime.ingest_event` accepts automatic Package and Doorbell events.
- `house_chime.ingest_event` rejects automatic Approach with
  `approach_direct_sensor_only`.
- A configured continuous person-presence binary sensor is the sole automatic
  Approach path. Its `off`, `unknown`, or `unavailable` state cancels the wait.
- General motion, activity, sound, and one-shot person events have no automatic
  Approach route.
- If continuous person presence is unavailable, the supported deployment is the
  safe hold: automatic Approach disabled, Package and Doorbell retained.

## Release gates

1. Unit coverage proves the automatic Approach rejection and Package/Doorbell
   ingress success, as well as direct-sensor cancellation.
2. Ruff, HACS structure, compilation, unit coverage, Home Assistant lifecycle,
   and diff checks pass.
3. Public-content review confirms no household entities, URLs, credentials,
   recordings, logs, or deployment evidence are included.
4. Release notes identify the automatic-Approach service restriction as a
   deliberate compatibility change.
5. The HACS deployment is verified through Home Assistant with non-audible
   diagnostics before any approved playback test.
