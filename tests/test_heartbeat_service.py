from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

from app.api.heartbeat_schemas import HeartbeatCheckInCreate
from app.domain.heartbeat import CheckInStatus, HeartbeatStatus
from app.persistence.models import Heartbeat
from app.services.heartbeat_service import create_heartbeat_checkin


def test_create_heartbeat_checkin_updates_heartbeat() -> None:
    heartbeat_id = uuid4()
    old_due_at = datetime(2026, 7, 1, tzinfo=UTC)

    heartbeat = Heartbeat(
        id=heartbeat_id,
        owner_name="Scott",
        owner_email="scott@example.com",
        status=HeartbeatStatus.OVERDUE,
        interval_days=30,
        reminder_days=7,
        next_due_at=old_due_at,
    )

    session = MagicMock()
    session.get.return_value = heartbeat

    request = HeartbeatCheckInCreate(
        status=CheckInStatus.WARNING,
        notes="May need assistance",
    )

    checkin = create_heartbeat_checkin(
        session,
        heartbeat_id,
        request,
    )

    assert checkin is not None
    assert checkin.heartbeat_id == heartbeat_id
    assert checkin.status == CheckInStatus.WARNING
    assert checkin.notes == "May need assistance"
    assert checkin.source == "manual"

    assert heartbeat.status == HeartbeatStatus.ACTIVE
    assert heartbeat.last_checkin_at is not None
    assert heartbeat.next_due_at > heartbeat.last_checkin_at
    assert (heartbeat.next_due_at - heartbeat.last_checkin_at).days == 30

    session.add.assert_called_once_with(checkin)
    session.commit.assert_called_once()
    assert session.refresh.call_count == 2


def test_create_heartbeat_checkin_returns_none_when_not_found() -> None:
    heartbeat_id = uuid4()
    session = MagicMock()
    session.get.return_value = None

    result = create_heartbeat_checkin(
        session,
        heartbeat_id,
        HeartbeatCheckInCreate(),
    )

    assert result is None
    session.add.assert_not_called()
    session.commit.assert_not_called()
