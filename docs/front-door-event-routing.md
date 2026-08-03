# Front-door event routing

This guide defines a reusable, vendor-neutral routing model for House Chime.
It separates *what a source detected* from *what should be announced*, so a
camera's general motion never becomes a spoken visitor announcement by
accident.

> **Approach safe hold — status 2026-08-03.** Automatic Approach is disabled
> in the reference deployment. It remains disabled until the selected Google /
> Nest source, or another supported source, exposes a reliable continuous
> person-presence state. Package and Doorbell continue to be supported.

## The supported event model

| Household outcome | Required source signal | House Chime route | Timing |
| --- | --- | --- | --- |
| Package arrival | A package-delivered event | Source automation calls `house_chime.ingest_event` with `front_door_package` | Immediate; subject to its duplicate window |
| Doorbell press | A doorbell-pressed event | Source automation calls `house_chime.ingest_event` with `front_door_doorbell` | Immediate; cancels and quiets Approach |
| Visitor loitering | A dedicated binary sensor that is `on` for the whole time a person remains at the door | Select that sensor in `Rules & diagnostics -> Approach timing & suppression` | After the configured continuous-presence wait |
| General motion | Motion, activity, sound, or zone movement | **No House Chime route** | Never announced |

`motion`, `activity`, and `person` are different source semantics. Do not use a
motion binary sensor as the Approach sensor, and do not map a generic motion
event to `front_door_approach`.

## One automatic Approach path

When a person-presence sensor is configured in House Chime, House Chime listens
to its off-to-on transition itself. That is the one automatic Approach path.

Do **not** also create an automation that reacts to that same sensor and calls
either `house_chime.ingest_event` or `house_chime.play`. Two paths for the same
encounter can create duplicate work and make the delay/cancellation policy hard
to reason about.

`house_chime.play` is an intentional immediate operator action. Use it for an
approved manual audio test, not an event-source automation. Keep
`skip_duplicate_suppression` off unless deliberately testing duplicate policy.

`house_chime.ingest_event` accepts Package and Doorbell only. It rejects
`front_door_approach` with `approach_direct_sensor_only`; this is intentional,
not a retryable source error.

## Configure loitering, not a person pulse

Set `Wait before announcing` to a non-zero value only when the chosen sensor
truthfully remains `on` while a person is at the door. House Chime cancels the
pending Approach when the sensor turns off, becomes `unknown` or `unavailable`,
the front door opens, or a Doorbell event arrives.

A one-shot person-detection event is useful evidence that a person was seen,
but it is not continuous presence. In particular, a helper that turns on for a
fixed few seconds after an event does **not** establish that the person is
still there when the wait expires. Do not use a fixed hold timer to simulate
loitering.

Choose one of these source capabilities before enabling delayed Approach:

1. **Continuous person presence available.** Configure that dedicated binary
   sensor directly in House Chime. This is the recommended loitering design.
2. **Person event only.** Leave automatic Approach disabled. Obtain a source
   that also publishes a reliable cleared/absent state before enabling it.

The source must clear the presence sensor when the person leaves. A camera
platform that cannot provide an `off`/absence signal cannot prove continuous
presence to House Chime.

## Safe hold when continuous presence is unavailable

If a front-door platform provides only person events, leave automatic Approach
disabled and leave the Approach sensor unselected. Continue to route Package
and Doorbell events through `house_chime.ingest_event`; this preserves useful
announcements without turning person or general-motion events into a false
loitering claim. Keep any event bridge disabled rather than changing it into a
fixed-duration presence helper.

## Privacy review

This public integration documents signal types, not a particular household.
Keep camera names, entity IDs, internal URLs, addresses, voice profiles,
recordings, logs, screenshots, and deployment evidence in a private workspace.
Use neutral placeholders in examples and remove identifying metadata before
sharing a configuration or diagnostic export.

## Google Home / Nest person events

Some Google Home / Nest configurations expose a `PersonDetection` starter in
the Google Home script editor but do not expose a persistent Home Assistant
binary sensor. Treat that starter as an **event**, not as proof of loitering.
Keep any bridge from that event disabled for House Chime automatic Approach.

Do not turn the event into a fixed-duration helper or template binary sensor to
simulate a person remaining at the door. Google Home availability and device
capabilities can change; review them before enabling Approach with a different,
continuous source.

### Infrastructure required before enabling Approach

Approach may be enabled only after the source path can provide all of the
following semantics to Home Assistant:

| Required capability | Why House Chime needs it |
| --- | --- |
| A dedicated front-door person-presence binary sensor | Keeps person presence distinct from general motion, packages, sound, or activity. |
| An `on` transition when a person begins remaining at the door | Starts the configured loitering wait. |
| A dependable `off` transition when that person leaves | Cancels the wait instead of announcing after the visitor has gone. |
| `unknown` / `unavailable` reporting | Lets House Chime stop treating an uncertain source as confirmed presence. |
| Stable entity identity across reloads and restarts | Prevents a source change from silently changing the operating policy. |

As of the status date above, the Google / Nest path provides a person-detected
event but not the required person-present and person-left state pair. That is
the missing infrastructure. A Google-side event bridge, a timed reset helper,
or a template that guesses departure does not satisfy this contract. Reassess
only when Google exposes this continuous state directly, or when another
supported integration publishes the five capabilities above.

## Deployment sequence

1. Inventory every front-door automation. Classify each trigger as package,
   doorbell, person presence, person event, or general motion.
2. Remove any general-motion route to House Chime.
3. Keep Package and Doorbell source automations and route them through
   `house_chime.ingest_event` with their matching event IDs.
4. For Approach, select exactly one dedicated, continuously true person sensor
   in `Rules & diagnostics -> Approach timing & suppression`; remove any
   automation that invokes a House Chime service from that sensor. If no such
   sensor exists, use the safe hold: disable Approach and leave its sensor
   unselected.
5. Select the front-door open sensor and an encounter quiet time. A Doorbell
   event and door opening both cancel a pending Approach and start the quiet
   period.
6. Use `Review / Dry Run` and `house_chime.resolve` to confirm readiness and
   suppression reasons without playing audio.
7. During an approved audible-test window, verify all acceptance cases below.

## Acceptance checklist

- General motion produces no House Chime activity or spoken announcement.
- A package event produces one Package announcement according to its duplicate
  policy.
- A doorbell event produces one Doorbell announcement, cancels a pending
  Approach, and starts the configured quiet period.
- A person who leaves before the wait expires produces no Approach
  announcement.
- A person who remains continuously present for the whole wait produces one
  Approach announcement.
- No manual audio test is run during quiet hours or without household approval.

If any item fails, leave the audio path disabled or use non-audible dry runs
while correcting the source routing. Do not work around an uncertain presence
signal by reducing the wait or using a general-motion sensor.
