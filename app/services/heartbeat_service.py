from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from app.api.heartbeat_schemas import (
    HeartbeatCheckInCreate,
    HeartbeatCreate,
)
from app.domain.heartbeat import HeartbeatStatus
from app.persistence.models import Heartbeat, HeartbeatCheckIn


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
    return session.query(Heartbeat).order_by(Heartbeat.created_at.desc()).all()


def create_heartbeat_checkin(
    session: Session,
    heartbeat_id: UUID,
    request: HeartbeatCheckInCreate,
) -> HeartbeatCheckIn | None:
    heartbeat = session.get(Heartbeat, heartbeat_id)

    if heartbeat is None:
        return None

    now = datetime.now(UTC)

    checkin = HeartbeatCheckIn(
        heartbeat_id=heartbeat.id,
        status=request.status,
        notes=request.notes,
        source=request.source,
        created_at=now,
    )

    heartbeat.status = HeartbeatStatus.ACTIVE
    heartbeat.last_checkin_at = now
    heartbeat.next_due_at = now + timedelta(days=heartbeat.interval_days)

    session.add(checkin)
    session.commit()
    session.refresh(checkin)
    session.refresh(heartbeat)

    return checkin
