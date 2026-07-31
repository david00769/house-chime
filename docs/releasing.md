# Releasing and deploying House Chime

This runbook keeps the public package release separate from a household's
private deployment evidence. Use the supported Git, GitHub, HACS, and Home
Assistant interfaces only; do not copy files into Home Assistant internals or
edit its database.

## 1. Verify the package

Run these commands from the repository root before committing a release:

```bash
uv sync --extra dev
uv run ruff check custom_components tests scripts ha_tests
uv run python scripts/check_hacs_structure.py
uv run python -m compileall -q custom_components/house_chime tests ha_tests scripts/check_hacs_structure.py
uv run pytest -p no:cacheprovider tests --cov=custom_components.house_chime --cov-fail-under=75
uv run --isolated --no-project --python 3.13 --with homeassistant --with pytest-homeassistant-custom-component pytest -p pytest_homeassistant_custom_component -p no:cacheprovider --asyncio-mode=auto ha_tests -q
uv run python -m unittest discover -s tests
git diff --check
```

Review `git status --short` and `CHANGELOG.md`. The public repository must not
contain household entity IDs, local addresses, credentials, screenshots, or
private deployment notes.

## 2. Create the local commit

Stage only the reviewed release files, then make one descriptive commit:

```bash
git add README.md CHANGELOG.md docs custom_components tests pyproject.toml uv.lock
git commit -m "feat: delay automatic approach announcements"
```

Check the resulting commit before publishing:

```bash
git status --short
git log -1 --oneline
```

## 3. Publish upstream

After the local commit is approved for publication, push the release branch and
create the version tag. The commands below use `main`; substitute the reviewed
release branch when one is being used.

```bash
git push origin main
git tag -a v0.5.0 -m "House Chime 0.5.0"
git push origin v0.5.0
```

Create the corresponding GitHub release from `v0.5.0`, using the matching
section of `CHANGELOG.md` as its notes. Confirm the pushed commit, tag, and
release all point to the same package version in `manifest.json`.

## 4. Update the HACS installation

Before a production update, create a normal Home Assistant backup. Then use
Home Assistant:

1. Open `HACS -> Integrations -> House Chime`.
2. Select **Update** (or **Redownload** when that is the available action).
3. Restart Home Assistant when HACS requests it.
4. Open `Settings -> Devices & services -> House Chime` and confirm the
   integration loads without a Repair or new error log entry.

HACS updates the public package only. Keep Sugarloaf-specific settings and
acceptance evidence in the private planning workspace.

## 5. Post-update acceptance

Start with non-audible checks:

1. Open **Configure** and confirm exactly four top-level sections: Household,
   Announcements, Playback, and Rules & diagnostics.
2. In `Rules & diagnostics -> Approach timing & suppression`, select the
   intended person-presence sensor, set the wait to 30 seconds, select the
   front-door sensor, and confirm the after-door or Doorbell quiet time is editable and
   defaults to 180 seconds.
3. Confirm the behavior preview explains that continuous presence is required
   and that a person leaving, the front door opening, or a Doorbell event
   cancels the pending Approach.
4. Disable any older automation that calls `house_chime.play` immediately from
   the person-presence sensor. Update Package and Doorbell source automations to
   call `house_chime.ingest_event`.
5. Use Review / Dry Run and `house_chime.resolve` for Approach while the door
   is closed, open, and in its cooldown. Confirm the suppression reason and
   UTC expiry are reported only for Approach.
6. Confirm `house_chime_approach_waiting`,
   `house_chime_approach_wait_until`,
   `house_chime_approach_suppression_active` and
   `house_chime_approach_suppression_until` are present on the integration
   device.
7. In an approved audible test window, turn on the person sensor and confirm no
   Approach plays before the configured wait. Repeat while making the person
   leave, opening the front door, and sending a Doorbell event; each case must
   cancel the pending Approach. Confirm both door-open and Doorbell events also
   block immediate re-arming for the configured quiet time.

Cancelled and suppressed Approach attempts are intentionally dropped: they are
not queued, replayed, or added to duplicate-suppression history. Do not run an
audible test unless it is deliberately scheduled and approved for the
household.
