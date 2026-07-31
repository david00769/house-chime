"""Reusable policy model for announcements that require a continuous trigger."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .const import STATE_UNAVAILABLE, STATE_UNKNOWN
from .models import AnnouncementConfig


@dataclass(frozen=True, slots=True)
class PendingAnnouncementPolicy:
    """Describe a delayed announcement independently of Home Assistant timers."""

    event_id: str
    trigger_entity_id: str | None
    hold_seconds: int
    cancel_event_ids: frozenset[str]
    interaction_suppression_seconds: int


def approach_pending_policy(config: AnnouncementConfig) -> PendingAnnouncementPolicy:
    """Adapt the backward-compatible Approach settings to the generic policy."""

    return PendingAnnouncementPolicy(
        event_id="front_door_approach",
        trigger_entity_id=config.approach_delay.sensor_entity_id,
        hold_seconds=config.approach_delay.delay_seconds,
        cancel_event_ids=frozenset({"front_door_doorbell"}),
        interaction_suppression_seconds=config.door_guard.cooldown_seconds,
    )


def pending_deadline(
    policy: PendingAnnouncementPolicy,
    *,
    now: datetime | None = None,
) -> str:
    """Return the UTC deadline for a new continuous-trigger wait."""

    now = now or datetime.now(timezone.utc)
    return (now + timedelta(seconds=policy.hold_seconds)).isoformat()


def pending_cancellation_reason(
    policy: PendingAnnouncementPolicy,
    states: dict[str, str],
) -> str | None:
    """Return why the policy's continuous trigger can no longer be verified."""

    entity_id = policy.trigger_entity_id
    if not entity_id:
        return "pending_trigger_not_configured"
    state = states.get(entity_id)
    if state is None:
        return "pending_trigger_missing"
    if state == STATE_UNAVAILABLE:
        return "pending_trigger_unavailable"
    if state == STATE_UNKNOWN:
        return "pending_trigger_unknown"
    if state != "on":
        return "trigger_cleared_before_delay"
    return None


def interaction_suppression_deadline(
    policy: PendingAnnouncementPolicy,
    *,
    now: datetime | None = None,
) -> str | None:
    """Return the end of an encounter quiet window, if one is configured."""

    if policy.interaction_suppression_seconds <= 0:
        return None
    now = now or datetime.now(timezone.utc)
    return (
        now + timedelta(seconds=policy.interaction_suppression_seconds)
    ).isoformat()
