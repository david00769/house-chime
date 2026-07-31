"""Pure timing policy for delayed front-door Approach announcements."""

from __future__ import annotations

from datetime import datetime

from .const import STATE_UNAVAILABLE, STATE_UNKNOWN
from .models import AnnouncementConfig, ApproachDelayConfig
from .pending_policy import (
    approach_pending_policy,
    pending_cancellation_reason,
    pending_deadline,
)


def _policy(config: ApproachDelayConfig):
    """Return the reusable pending policy for a legacy Approach config."""

    announcement_config = AnnouncementConfig(approach_delay=config)
    return approach_pending_policy(announcement_config)


def approach_wait_deadline(
    config: ApproachDelayConfig,
    *,
    now: datetime | None = None,
) -> str:
    """Return the UTC deadline for a newly detected person."""

    return pending_deadline(_policy(config), now=now)


def approach_wait_cancellation_reason(
    config: ApproachDelayConfig,
    states: dict[str, str],
) -> str | None:
    """Return why continuous presence can no longer be verified."""

    reason = pending_cancellation_reason(_policy(config), states)
    return {
        "pending_trigger_not_configured": "approach_delay_not_configured",
        "pending_trigger_missing": "approach_sensor_missing",
        "pending_trigger_unavailable": "approach_sensor_unavailable",
        "pending_trigger_unknown": "approach_sensor_unknown",
        "trigger_cleared_before_delay": "person_left_before_delay",
    }.get(reason, reason)


def approach_sensor_warning(
    config: ApproachDelayConfig,
    states: dict[str, str],
) -> str | None:
    """Return a setup warning without treating an inactive sensor as faulty."""

    sensor_entity_id = config.sensor_entity_id
    if not sensor_entity_id:
        return None
    sensor_state = states.get(sensor_entity_id)
    if sensor_state is None:
        return f"approach_sensor_missing:{sensor_entity_id}"
    if sensor_state in {STATE_UNAVAILABLE, STATE_UNKNOWN}:
        return f"approach_sensor_{sensor_state}:{sensor_entity_id}"
    return None
