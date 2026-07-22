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


def determine_heartbeat_status(
    heartbeat: Heartbeat,
    *,
    now: datetime | None = None,
) -> HeartbeatStatus:
    """Return the status implied by the heartbeat's due date."""
    if heartbeat.status in {
        HeartbeatStatus.OVERDUE,
        HeartbeatStatus.PAUSED,
        HeartbeatStatus.CANCELLED,
    }:
        return heartbeat.status

    current_time = now or datetime.now(UTC)

    if heartbeat.next_due_at <= current_time:
        return HeartbeatStatus.OVERDUE

    return HeartbeatStatus.ACTIVE


def refresh_heartbeat_status(
    session: Session,
    heartbeat: Heartbeat,
    *,
    now: datetime | None = None,
) -> Heartbeat:
    """Update and persist one heartbeat when its calculated status changed."""
    calculated_status = determine_heartbeat_status(
        heartbeat,
        now=now,
    )

    if heartbeat.status != calculated_status:
        heartbeat.status = calculated_status
        session.commit()
        session.refresh(heartbeat)

    return heartbeat


def refresh_heartbeat_statuses(
    session: Session,
    heartbeats: list[Heartbeat],
    *,
    now: datetime | None = None,
) -> list[Heartbeat]:
    """Update a collection of heartbeats using a single transaction."""
    current_time = now or datetime.now(UTC)
    changed = False

    for heartbeat in heartbeats:
        calculated_status = determine_heartbeat_status(
            heartbeat,
            now=current_time,
        )

        if heartbeat.status != calculated_status:
            heartbeat.status = calculated_status
            changed = True

    if changed:
        session.commit()

        for heartbeat in heartbeats:
            session.refresh(heartbeat)

    return heartbeats


def get_heartbeat(
    session: Session,
    heartbeat_id: UUID,
) -> Heartbeat | None:
    heartbeat = session.get(Heartbeat, heartbeat_id)

    if heartbeat is None:
        return None

    return refresh_heartbeat_status(
        session,
        heartbeat,
    )


def list_heartbeats(
    session: Session,
) -> list[Heartbeat]:
    heartbeats = session.query(Heartbeat).order_by(Heartbeat.created_at.desc()).all()

    return refresh_heartbeat_statuses(
        session,
        heartbeats,
    )


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
