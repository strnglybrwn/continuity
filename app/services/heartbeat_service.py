from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from app.api.heartbeat_schemas import HeartbeatCreate
from app.persistence.models import Heartbeat


def create_heartbeat(
    session: Session,
    request: HeartbeatCreate,
) -> Heartbeat:
    now = datetime.now(UTC)

    heartbeat = Heartbeat(
        owner_name=request.owner_name,
        owner_email=str(request.owner_email),
        interval_days=request.interval_days,
        reminder_days=request.reminder_days,
        next_due_at=now + timedelta(days=request.interval_days),
    )

    session.add(heartbeat)
    session.commit()
    session.refresh(heartbeat)

    return heartbeat


def get_heartbeat(
    session: Session,
    heartbeat_id: UUID,
) -> Heartbeat | None:
    return session.get(Heartbeat, heartbeat_id)

def list_heartbeats(
    session: Session,
) -> list[Heartbeat]:
    return (
        session.query(Heartbeat)
        .order_by(Heartbeat.created_at.desc())
        .all()
    )
