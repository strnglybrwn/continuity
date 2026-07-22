from uuid import UUID

from sqlalchemy.orm import Session, joinedload

from app.core.clock import Clock, utc_now
from app.persistence.models import HeartbeatEvent


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
