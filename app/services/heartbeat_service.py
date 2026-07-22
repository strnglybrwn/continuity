from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.api.heartbeat_schemas import (
    HeartbeatCheckInCreate,
    HeartbeatCreate,
)
from app.core.clock import Clock, utc_now
from app.core.lifecycle import lifecycle_duration
from app.domain.heartbeat import HeartbeatStatus
from app.persistence.models import Heartbeat, HeartbeatCheckIn


@dataclass(frozen=True, slots=True)
class HeartbeatEvaluationResult:
    evaluated: int
    changed: int


def create_heartbeat(
    session: Session,
    request: HeartbeatCreate,
    *,
    clock: Clock = utc_now,
) -> Heartbeat:
    now = clock()

    heartbeat = Heartbeat(
        owner_name=request.owner_name,
        owner_email=str(request.owner_email),
        status=HeartbeatStatus.ACTIVE,
        interval_days=request.interval_days,
        reminder_days=request.reminder_days,
        next_due_at=now + lifecycle_duration(request.interval_days),
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

    current_time = now if now is not None else utc_now()

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
    current_time = now if now is not None else utc_now()
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


def evaluate_due_heartbeats(
    session: Session,
    *,
    now: datetime | None = None,
) -> HeartbeatEvaluationResult:
    """Evaluate every active heartbeat and persist overdue transitions."""
    current_time = now if now is not None else utc_now()

    heartbeats = session.query(Heartbeat).filter(Heartbeat.status == HeartbeatStatus.ACTIVE).all()

    changed = sum(
        determine_heartbeat_status(
            heartbeat,
            now=current_time,
        )
        != heartbeat.status
        for heartbeat in heartbeats
    )

    refresh_heartbeat_statuses(
        session,
        heartbeats,
        now=current_time,
    )

    return HeartbeatEvaluationResult(
        evaluated=len(heartbeats),
        changed=changed,
    )


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


def _apply_heartbeat_checkin(
    session: Session,
    heartbeat: Heartbeat,
    request: HeartbeatCheckInCreate,
    *,
    created_at: datetime,
) -> HeartbeatCheckIn:
    """Apply a check-in without committing the surrounding transaction."""
    checkin = HeartbeatCheckIn(
        heartbeat_id=heartbeat.id,
        status=request.status,
        notes=request.notes,
        source=request.source,
        created_at=created_at,
    )

    heartbeat.status = HeartbeatStatus.ACTIVE
    heartbeat.last_checkin_at = created_at
    heartbeat.next_due_at = created_at + lifecycle_duration(
        heartbeat.interval_days,
    )

    session.add(checkin)

    return checkin


def create_heartbeat_checkin(
    session: Session,
    heartbeat_id: UUID,
    request: HeartbeatCheckInCreate,
    *,
    clock: Clock = utc_now,
) -> HeartbeatCheckIn | None:
    heartbeat = session.get(Heartbeat, heartbeat_id)

    if heartbeat is None:
        return None

    checkin = _apply_heartbeat_checkin(
        session,
        heartbeat,
        request,
        created_at=clock(),
    )

    session.commit()
    session.refresh(checkin)
    session.refresh(heartbeat)

    return checkin
