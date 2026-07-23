from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.heartbeat_schemas import (
    HeartbeatCheckInCreate,
    HeartbeatCreate,
)
from app.core.clock import Clock, utc_now
from app.core.lifecycle import lifecycle_duration
from app.domain.heartbeat import HeartbeatEventType, HeartbeatStatus
from app.persistence.models import (
    Heartbeat,
    HeartbeatCheckIn,
    HeartbeatEvent,
)


@dataclass(frozen=True, slots=True)
class HeartbeatEvaluationResult:
    evaluated: int
    changed: int


def record_heartbeat_event(
    session: Session,
    heartbeat: Heartbeat,
    event_type: HeartbeatEventType,
    *,
    occurred_at: datetime,
) -> HeartbeatEvent | None:
    """Record an event unless the same lifecycle event already exists."""
    existing_event_id = session.scalar(
        select(HeartbeatEvent.id).where(
            HeartbeatEvent.heartbeat_id == heartbeat.id,
            HeartbeatEvent.event_type == event_type,
            HeartbeatEvent.occurred_at == occurred_at,
        )
    )

    if existing_event_id is not None:
        return None

    event = HeartbeatEvent(
        heartbeat_id=heartbeat.id,
        event_type=event_type,
        occurred_at=occurred_at,
        created_at=occurred_at,
    )
    session.add(event)

    return event


def heartbeat_reminder_at(heartbeat: Heartbeat) -> datetime:
    """Return the start of a heartbeat's reminder window."""
    return heartbeat.next_due_at - lifecycle_duration(
        heartbeat.reminder_days,
    )


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


def is_heartbeat_reminder_due(
    heartbeat: Heartbeat,
    *,
    now: datetime | None = None,
) -> bool:
    """Return whether an active heartbeat is within its reminder window."""
    if heartbeat.status != HeartbeatStatus.ACTIVE:
        return False

    if heartbeat.reminder_days <= 0:
        return False

    current_time = now if now is not None else utc_now()
    reminder_at = heartbeat_reminder_at(heartbeat)

    return reminder_at <= current_time < heartbeat.next_due_at


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
    """Evaluate active heartbeats and record due lifecycle events."""
    current_time = now if now is not None else utc_now()

    heartbeats = session.query(Heartbeat).filter(Heartbeat.status == HeartbeatStatus.ACTIVE).all()

    changed = 0
    events_created = 0

    for heartbeat in heartbeats:
        if is_heartbeat_reminder_due(
            heartbeat,
            now=current_time,
        ):
            event = record_heartbeat_event(
                session,
                heartbeat,
                HeartbeatEventType.REMINDER_DUE,
                occurred_at=heartbeat_reminder_at(heartbeat),
            )
            events_created += event is not None

        calculated_status = determine_heartbeat_status(
            heartbeat,
            now=current_time,
        )

        if calculated_status != heartbeat.status:
            heartbeat.status = calculated_status
            changed += 1

            event = record_heartbeat_event(
                session,
                heartbeat,
                HeartbeatEventType.OVERDUE,
                occurred_at=heartbeat.next_due_at,
            )
            events_created += event is not None

    if changed or events_created:
        session.commit()

        for heartbeat in heartbeats:
            session.refresh(heartbeat)

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

    created_at = clock()

    checkin = _apply_heartbeat_checkin(
        session,
        heartbeat,
        request,
        created_at=created_at,
    )

    record_heartbeat_event(
        session,
        heartbeat,
        HeartbeatEventType.CHECKED_IN,
        occurred_at=created_at,
    )

    session.commit()
    session.refresh(checkin)
    session.refresh(heartbeat)

    return checkin


def update_heartbeat_dashboard_settings(
    session: Session,
    heartbeat_id: UUID,
    *,
    owner_name: str,
    owner_email: str,
    interval_days: int,
    reminder_days: int,
    arm_reminder_now: bool,
    now: datetime | None = None,
) -> Heartbeat | None:
    """Update dashboard-editable heartbeat fields used for reminder testing."""
    heartbeat = session.get(Heartbeat, heartbeat_id)

    if heartbeat is None:
        return None

    if reminder_days < 0:
        raise ValueError("reminder_days must be 0 or greater")

    if interval_days < 1:
        raise ValueError("interval_days must be greater than zero")

    if interval_days > 365:
        raise ValueError("interval_days must be less than or equal to 365")

    if reminder_days >= interval_days:
        raise ValueError("reminder_days must be less than interval_days")

    if arm_reminder_now and reminder_days == 0:
        raise ValueError(
            "Set reminder_days to at least 1 before arming reminder due now",
        )

    current_time = now if now is not None else utc_now()

    heartbeat.owner_name = owner_name
    heartbeat.owner_email = owner_email
    heartbeat.interval_days = interval_days
    heartbeat.reminder_days = reminder_days

    if arm_reminder_now:
        heartbeat.status = HeartbeatStatus.ACTIVE
        # Put due time in the near future so reminder window is active now.
        heartbeat.next_due_at = current_time + timedelta(hours=1)
    else:
        base_time = (
            heartbeat.last_checkin_at if heartbeat.last_checkin_at is not None else current_time
        )
        heartbeat.next_due_at = base_time + lifecycle_duration(interval_days)

    session.commit()
    session.refresh(heartbeat)

    return heartbeat
