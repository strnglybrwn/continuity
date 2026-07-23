from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session, joinedload

from app.core.clock import Clock, utc_now
from app.domain.heartbeat import HeartbeatEventType
from app.domain.notification import Notification
from app.persistence.models import HeartbeatEvent
from app.services.checkin_token_service import issue_checkin_token
from app.services.notification_service import build_reminder_notification


class ReminderNotificationPreparationError(ValueError):
    """Raised when a heartbeat event cannot be prepared for reminder delivery."""


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
