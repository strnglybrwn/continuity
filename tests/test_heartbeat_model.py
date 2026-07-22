from datetime import UTC, datetime
from uuid import uuid4

from app.domain.heartbeat import CheckInStatus, HeartbeatStatus
from app.persistence.models import Heartbeat, HeartbeatCheckIn


def test_heartbeat_defaults() -> None:
    heartbeat = Heartbeat(
        owner_name="Scott",
        owner_email="scott@example.com",
        interval_days=30,
        reminder_days=7,
        next_due_at=datetime(2026, 8, 20, tzinfo=UTC),
    )

    assert heartbeat.owner_name == "Scott"
    assert heartbeat.owner_email == "scott@example.com"
    assert heartbeat.interval_days == 30
    assert heartbeat.reminder_days == 7


def test_heartbeat_status_values() -> None:
    assert HeartbeatStatus.ACTIVE.value == "active"
    assert HeartbeatStatus.OVERDUE.value == "overdue"
    assert HeartbeatStatus.PAUSED.value == "paused"
    assert HeartbeatStatus.CANCELLED.value == "cancelled"


def test_checkin_status_values() -> None:
    assert CheckInStatus.OK.value == "ok"
    assert CheckInStatus.WARNING.value == "warning"


def test_heartbeat_table_definition() -> None:
    table = Heartbeat.__table__

    assert Heartbeat.__tablename__ == "heartbeats"
    assert table.c.id.primary_key is True
    assert table.c.id.default is not None
    assert table.c.owner_email.index is True
    assert table.c.next_due_at.nullable is False


def test_heartbeat_checkin_defaults() -> None:
    checkin = HeartbeatCheckIn(
        heartbeat_id=uuid4(),
        status=CheckInStatus.OK,
        notes="Everything is fine",
        source="manual",
    )

    assert checkin.status == CheckInStatus.OK
    assert checkin.notes == "Everything is fine"
    assert checkin.source == "manual"


def test_heartbeat_checkin_table_definition() -> None:
    table = HeartbeatCheckIn.__table__

    assert HeartbeatCheckIn.__tablename__ == "heartbeat_checkins"
    assert table.c.id.primary_key is True
    assert table.c.id.default is not None
    assert table.c.heartbeat_id.nullable is False
    assert table.c.heartbeat_id.index is True
    assert table.c.status.nullable is False
    assert table.c.source.nullable is False
    assert table.c.created_at.nullable is False
