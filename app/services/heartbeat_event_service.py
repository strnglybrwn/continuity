from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.core.clock import Clock, utc_now
from app.domain.heartbeat import HeartbeatEventType
from app.domain.notification import Notification
from app.persistence.models import HeartbeatEvent
from app.services.checkin_token_service import issue_checkin_token
from app.services.notification_service import build_reminder_notification


class ReminderNotificationPreparationError(ValueError):
    """Raised when a heartbeat event cannot be prepared for reminder delivery."""


@dataclass(frozen=True, slots=True)
class HeartbeatPendingMetrics:
    pending_total: int
    pending_reminder_due_total: int
    oldest_pending_occurred_at: datetime | None
    oldest_pending_age_seconds: int | None
    stale_pending_alert: bool
    stale_reminder_due_total: int


def _build_checkin_url(*, public_base_url: str, raw_token: str) -> str:
    return f"{public_base_url.rstrip('/')}/checkins/{raw_token}"


def prepare_reminder_notification(
    session: Session,
    event_id: UUID,
    *,
    public_base_url: str,
    now: datetime | None = None,
) -> tuple[HeartbeatEvent, Notification, str]:
    """Create a send-ready reminder payload for one pending reminder event."""
    event = session.get(
        HeartbeatEvent,
        event_id,
        options=(joinedload(HeartbeatEvent.heartbeat),),
    )

    if event is None:
        raise ReminderNotificationPreparationError("Heartbeat event not found")

    if event.event_type != HeartbeatEventType.REMINDER_DUE:
        raise ReminderNotificationPreparationError("Heartbeat event is not a reminder event")

    if event.delivered_at is not None:
        raise ReminderNotificationPreparationError("Heartbeat event is already delivered")

    if not public_base_url.strip():
        raise ReminderNotificationPreparationError("public_base_url must not be empty")

    issued = issue_checkin_token(
        session,
        event.heartbeat_id,
        now=now,
    )

    if issued is None:
        raise ReminderNotificationPreparationError("Heartbeat not found for event")

    checkin_url = _build_checkin_url(
        public_base_url=public_base_url,
        raw_token=issued.raw_token,
    )
    notification = build_reminder_notification(
        event.heartbeat,
        checkin_url=checkin_url,
    )

    return event, notification, checkin_url


def list_pending_heartbeat_events(
    session: Session,
    *,
    limit: int = 100,
) -> list[HeartbeatEvent]:
    """Return undelivered heartbeat events in occurrence order."""
    return (
        session.query(HeartbeatEvent)
        .options(joinedload(HeartbeatEvent.heartbeat))
        .filter(HeartbeatEvent.delivered_at.is_(None))
        .order_by(
            HeartbeatEvent.occurred_at.asc(),
            HeartbeatEvent.created_at.asc(),
        )
        .limit(limit)
        .all()
    )


def get_pending_heartbeat_event_metrics(
    session: Session,
    *,
    stale_after_seconds: int,
    now: datetime | None = None,
) -> HeartbeatPendingMetrics:
    """Return queue metrics and stale reminder alert information."""
    if stale_after_seconds <= 0:
        raise ValueError("stale_after_seconds must be greater than zero")

    current_time = now if now is not None else utc_now()
    stale_cutoff = datetime.fromtimestamp(
        current_time.timestamp() - stale_after_seconds,
        tz=current_time.tzinfo,
    )

    pending_total = (
        session.query(func.count(HeartbeatEvent.id))
        .filter(HeartbeatEvent.delivered_at.is_(None))
        .scalar()
        or 0
    )

    pending_reminder_due_total = (
        session.query(func.count(HeartbeatEvent.id))
        .filter(HeartbeatEvent.delivered_at.is_(None))
        .filter(HeartbeatEvent.event_type == HeartbeatEventType.REMINDER_DUE)
        .scalar()
        or 0
    )

    oldest_pending_occurred_at = (
        session.query(func.min(HeartbeatEvent.occurred_at))
        .filter(HeartbeatEvent.delivered_at.is_(None))
        .scalar()
    )

    stale_reminder_due_total = (
        session.query(func.count(HeartbeatEvent.id))
        .filter(HeartbeatEvent.delivered_at.is_(None))
        .filter(HeartbeatEvent.event_type == HeartbeatEventType.REMINDER_DUE)
        .filter(HeartbeatEvent.occurred_at <= stale_cutoff)
        .scalar()
        or 0
    )

    oldest_pending_age_seconds: int | None = None
    if oldest_pending_occurred_at is not None:
        age_seconds = int((current_time - oldest_pending_occurred_at).total_seconds())
        oldest_pending_age_seconds = max(age_seconds, 0)

    return HeartbeatPendingMetrics(
        pending_total=int(pending_total),
        pending_reminder_due_total=int(pending_reminder_due_total),
        oldest_pending_occurred_at=oldest_pending_occurred_at,
        oldest_pending_age_seconds=oldest_pending_age_seconds,
        stale_pending_alert=stale_reminder_due_total > 0,
        stale_reminder_due_total=int(stale_reminder_due_total),
    )


def mark_heartbeat_event_delivered(
    session: Session,
    event_id: UUID,
    *,
    clock: Clock = utc_now,
) -> HeartbeatEvent | None:
    """Mark an event delivered, preserving the original delivery time."""
    event = session.get(HeartbeatEvent, event_id)

    if event is None:
        return None

    if event.delivered_at is None:
        event.delivered_at = clock()
        session.commit()
        session.refresh(event)

    return event
