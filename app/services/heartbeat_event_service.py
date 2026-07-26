from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.core.clock import Clock, utc_now
from app.domain.heartbeat import HeartbeatEventType
from app.domain.notification import Notification
from app.persistence.models import HeartbeatEvent
from app.services.heartbeat_attachment_service import (
    HeartbeatAttachmentSummary,
    list_heartbeat_attachment_summaries,
)
from app.services.checkin_token_service import issue_checkin_token
from app.services.heartbeat_service import heartbeat_escalation_at
from app.services.notification_service import (
    build_escalation_notification,
    build_overdue_warning_notification,
    build_reminder_notification,
)


class ReminderNotificationPreparationError(ValueError):
    """Raised when a heartbeat event cannot be prepared for reminder delivery."""


class OverdueNotificationPreparationError(ValueError):
    """Raised when a heartbeat event cannot be prepared for overdue-warning delivery."""


class EscalationNotificationPreparationError(ValueError):
    """Raised when a heartbeat event cannot be prepared for escalation delivery."""


@dataclass(frozen=True, slots=True)
class HeartbeatPendingMetrics:
    pending_total: int
    pending_reminder_due_total: int
    oldest_pending_occurred_at: datetime | None
    oldest_pending_age_seconds: int | None
    stale_pending_alert: bool
    stale_reminder_due_total: int
    pending_overdue_total: int = 0
    pending_escalation_due_total: int = 0
    stale_overdue_total: int = 0
    stale_escalation_due_total: int = 0


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


def prepare_overdue_notification(
    session: Session,
    event_id: UUID,
    *,
    public_base_url: str,
    now: datetime | None = None,
) -> tuple[HeartbeatEvent, Notification, str]:
    """Create a send-ready overdue-warning payload for one pending overdue event."""
    event = session.get(
        HeartbeatEvent,
        event_id,
        options=(joinedload(HeartbeatEvent.heartbeat),),
    )

    if event is None:
        raise OverdueNotificationPreparationError("Heartbeat event not found")

    if event.event_type != HeartbeatEventType.OVERDUE:
        raise OverdueNotificationPreparationError("Heartbeat event is not an overdue event")

    if event.delivered_at is not None:
        raise OverdueNotificationPreparationError("Heartbeat event is already delivered")

    if not public_base_url.strip():
        raise OverdueNotificationPreparationError("public_base_url must not be empty")

    issued = issue_checkin_token(
        session,
        event.heartbeat_id,
        now=now,
    )

    if issued is None:
        raise OverdueNotificationPreparationError("Heartbeat not found for event")

    checkin_url = _build_checkin_url(
        public_base_url=public_base_url,
        raw_token=issued.raw_token,
    )

    heartbeat = event.heartbeat
    escalation_at = (
        heartbeat_escalation_at(heartbeat)
        if heartbeat.escalation_enabled and heartbeat.escalation_contact_email
        else None
    )

    notification = build_overdue_warning_notification(
        heartbeat,
        checkin_url=checkin_url,
        escalation_enabled=escalation_at is not None,
        escalation_contact_name=heartbeat.escalation_contact_name,
        escalation_at=escalation_at,
    )

    return event, notification, checkin_url


def prepare_escalation_notification(
    session: Session,
    event_id: UUID,
) -> tuple[HeartbeatEvent, Notification, list[HeartbeatAttachmentSummary]]:
    """Create a send-ready escalation payload for one pending escalation event."""
    event = session.get(
        HeartbeatEvent,
        event_id,
        options=(joinedload(HeartbeatEvent.heartbeat),),
    )

    if event is None:
        raise EscalationNotificationPreparationError("Heartbeat event not found")

    if event.event_type != HeartbeatEventType.ESCALATION_DUE:
        raise EscalationNotificationPreparationError("Heartbeat event is not an escalation event")

    if event.delivered_at is not None:
        raise EscalationNotificationPreparationError("Heartbeat event is already delivered")

    heartbeat = event.heartbeat

    if not heartbeat.escalation_contact_name or not heartbeat.escalation_contact_email:
        raise EscalationNotificationPreparationError(
            "Heartbeat has no escalation contact configured"
        )

    notification = build_escalation_notification(heartbeat)
    attachments = list_heartbeat_attachment_summaries(heartbeat)

    return event, notification, attachments


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
    """Return queue metrics and stale alert information across event types."""
    if stale_after_seconds <= 0:
        raise ValueError("stale_after_seconds must be greater than zero")

    current_time = now if now is not None else utc_now()
    stale_cutoff = datetime.fromtimestamp(
        current_time.timestamp() - stale_after_seconds,
        tz=current_time.tzinfo,
    )

    def _pending_count(event_type: HeartbeatEventType | None = None) -> int:
        query = session.query(func.count(HeartbeatEvent.id)).filter(
            HeartbeatEvent.delivered_at.is_(None)
        )

        if event_type is not None:
            query = query.filter(HeartbeatEvent.event_type == event_type)

        return int(query.scalar() or 0)

    def _stale_count(event_type: HeartbeatEventType) -> int:
        return int(
            session.query(func.count(HeartbeatEvent.id))
            .filter(HeartbeatEvent.delivered_at.is_(None))
            .filter(HeartbeatEvent.event_type == event_type)
            .filter(HeartbeatEvent.occurred_at <= stale_cutoff)
            .scalar()
            or 0
        )

    pending_total = _pending_count()
    pending_reminder_due_total = _pending_count(HeartbeatEventType.REMINDER_DUE)
    pending_overdue_total = _pending_count(HeartbeatEventType.OVERDUE)
    pending_escalation_due_total = _pending_count(HeartbeatEventType.ESCALATION_DUE)

    oldest_pending_occurred_at = (
        session.query(func.min(HeartbeatEvent.occurred_at))
        .filter(HeartbeatEvent.delivered_at.is_(None))
        .scalar()
    )

    stale_reminder_due_total = _stale_count(HeartbeatEventType.REMINDER_DUE)
    stale_overdue_total = _stale_count(HeartbeatEventType.OVERDUE)
    stale_escalation_due_total = _stale_count(HeartbeatEventType.ESCALATION_DUE)

    oldest_pending_age_seconds: int | None = None
    if oldest_pending_occurred_at is not None:
        age_seconds = int((current_time - oldest_pending_occurred_at).total_seconds())
        oldest_pending_age_seconds = max(age_seconds, 0)

    return HeartbeatPendingMetrics(
        pending_total=pending_total,
        pending_reminder_due_total=pending_reminder_due_total,
        oldest_pending_occurred_at=oldest_pending_occurred_at,
        oldest_pending_age_seconds=oldest_pending_age_seconds,
        stale_pending_alert=(
            stale_reminder_due_total > 0
            or stale_overdue_total > 0
            or stale_escalation_due_total > 0
        ),
        stale_reminder_due_total=stale_reminder_due_total,
        pending_overdue_total=pending_overdue_total,
        pending_escalation_due_total=pending_escalation_due_total,
        stale_overdue_total=stale_overdue_total,
        stale_escalation_due_total=stale_escalation_due_total,
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
