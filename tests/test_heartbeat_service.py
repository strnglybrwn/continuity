from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from uuid import uuid4

from app.config import settings
from app.api.heartbeat_schemas import (
    HeartbeatCheckInCreate,
    HeartbeatCreate,
)
from app.domain.heartbeat import CheckInStatus, HeartbeatStatus
from app.persistence.models import Heartbeat
from app.services.heartbeat_service import (
    HeartbeatEvaluationResult,
    create_heartbeat,
    create_heartbeat_checkin,
    determine_heartbeat_status,
    evaluate_due_heartbeats,
    refresh_heartbeat_status,
    refresh_heartbeat_statuses,
)


def test_create_heartbeat_uses_injected_clock() -> None:
    now = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)
    session = MagicMock()

    request = HeartbeatCreate(
        owner_name="Scott",
        owner_email="scott@example.com",
        interval_days=30,
        reminder_days=7,
    )

    heartbeat = create_heartbeat(
        session,
        request,
        clock=lambda: now,
    )

    assert heartbeat.next_due_at == datetime(
        2026,
        8,
        21,
        12,
        0,
        tzinfo=UTC,
    )

    session.add.assert_called_once_with(heartbeat)
    session.commit.assert_called_once()
    session.refresh.assert_called_once_with(heartbeat)


def test_create_heartbeat_checkin_uses_injected_clock() -> None:
    now = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)
    heartbeat_id = uuid4()

    heartbeat = Heartbeat(
        id=heartbeat_id,
        owner_name="Scott",
        owner_email="scott@example.com",
        status=HeartbeatStatus.OVERDUE,
        interval_days=30,
        reminder_days=7,
        next_due_at=datetime(2026, 7, 1, tzinfo=UTC),
    )

    session = MagicMock()
    session.get.return_value = heartbeat

    checkin = create_heartbeat_checkin(
        session,
        heartbeat_id,
        HeartbeatCheckInCreate(),
        clock=lambda: now,
    )

    assert checkin is not None
    assert checkin.created_at == now
    assert heartbeat.last_checkin_at == now
    assert heartbeat.next_due_at == datetime(
        2026,
        8,
        21,
        12,
        0,
        tzinfo=UTC,
    )


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


def test_active_heartbeat_becomes_overdue_after_due_time() -> None:
    now = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)

    heartbeat = Heartbeat(
        owner_name="Scott",
        owner_email="scott@example.com",
        status=HeartbeatStatus.ACTIVE,
        interval_days=30,
        reminder_days=7,
        next_due_at=datetime(2026, 7, 22, 11, 59, tzinfo=UTC),
    )

    result = determine_heartbeat_status(
        heartbeat,
        now=now,
    )

    assert result == HeartbeatStatus.OVERDUE


def test_heartbeat_due_exactly_now_is_overdue() -> None:
    now = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)

    heartbeat = Heartbeat(
        owner_name="Scott",
        owner_email="scott@example.com",
        status=HeartbeatStatus.ACTIVE,
        interval_days=30,
        reminder_days=7,
        next_due_at=now,
    )

    result = determine_heartbeat_status(
        heartbeat,
        now=now,
    )

    assert result == HeartbeatStatus.OVERDUE


def test_active_heartbeat_before_due_time_remains_active() -> None:
    now = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)

    heartbeat = Heartbeat(
        owner_name="Scott",
        owner_email="scott@example.com",
        status=HeartbeatStatus.ACTIVE,
        interval_days=30,
        reminder_days=7,
        next_due_at=datetime(2026, 7, 23, 12, 0, tzinfo=UTC),
    )

    result = determine_heartbeat_status(
        heartbeat,
        now=now,
    )

    assert result == HeartbeatStatus.ACTIVE


def test_overdue_heartbeat_remains_overdue_until_checkin() -> None:
    now = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)

    heartbeat = Heartbeat(
        owner_name="Scott",
        owner_email="scott@example.com",
        status=HeartbeatStatus.OVERDUE,
        interval_days=30,
        reminder_days=7,
        next_due_at=datetime(2026, 8, 22, 12, 0, tzinfo=UTC),
    )

    result = determine_heartbeat_status(
        heartbeat,
        now=now,
    )

    assert result == HeartbeatStatus.OVERDUE


def test_paused_heartbeat_is_not_changed_automatically() -> None:
    now = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)

    heartbeat = Heartbeat(
        owner_name="Scott",
        owner_email="scott@example.com",
        status=HeartbeatStatus.PAUSED,
        interval_days=30,
        reminder_days=7,
        next_due_at=datetime(2026, 7, 1, tzinfo=UTC),
    )

    result = determine_heartbeat_status(
        heartbeat,
        now=now,
    )

    assert result == HeartbeatStatus.PAUSED


def test_cancelled_heartbeat_is_not_changed_automatically() -> None:
    now = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)

    heartbeat = Heartbeat(
        owner_name="Scott",
        owner_email="scott@example.com",
        status=HeartbeatStatus.CANCELLED,
        interval_days=30,
        reminder_days=7,
        next_due_at=datetime(2026, 7, 1, tzinfo=UTC),
    )

    result = determine_heartbeat_status(
        heartbeat,
        now=now,
    )

    assert result == HeartbeatStatus.CANCELLED


def test_refresh_heartbeat_status_persists_changed_status() -> None:
    now = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)

    heartbeat = Heartbeat(
        owner_name="Scott",
        owner_email="scott@example.com",
        status=HeartbeatStatus.ACTIVE,
        interval_days=30,
        reminder_days=7,
        next_due_at=datetime(2026, 7, 1, tzinfo=UTC),
    )

    session = MagicMock()

    result = refresh_heartbeat_status(
        session,
        heartbeat,
        now=now,
    )

    assert result.status == HeartbeatStatus.OVERDUE
    session.commit.assert_called_once()
    session.refresh.assert_called_once_with(heartbeat)


def test_refresh_heartbeat_status_does_not_commit_when_unchanged() -> None:
    now = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)

    heartbeat = Heartbeat(
        owner_name="Scott",
        owner_email="scott@example.com",
        status=HeartbeatStatus.ACTIVE,
        interval_days=30,
        reminder_days=7,
        next_due_at=datetime(2026, 8, 1, tzinfo=UTC),
    )

    session = MagicMock()

    result = refresh_heartbeat_status(
        session,
        heartbeat,
        now=now,
    )

    assert result.status == HeartbeatStatus.ACTIVE
    session.commit.assert_not_called()
    session.refresh.assert_not_called()


def test_refresh_heartbeat_statuses_uses_single_commit() -> None:
    now = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)

    overdue = Heartbeat(
        owner_name="Scott",
        owner_email="scott@example.com",
        status=HeartbeatStatus.ACTIVE,
        interval_days=30,
        reminder_days=7,
        next_due_at=datetime(2026, 7, 1, tzinfo=UTC),
    )

    current = Heartbeat(
        owner_name="Zoe",
        owner_email="zoe@example.com",
        status=HeartbeatStatus.ACTIVE,
        interval_days=30,
        reminder_days=7,
        next_due_at=datetime(2026, 8, 1, tzinfo=UTC),
    )

    session = MagicMock()

    result = refresh_heartbeat_statuses(
        session,
        [overdue, current],
        now=now,
    )

    assert result == [overdue, current]
    assert overdue.status == HeartbeatStatus.OVERDUE
    assert current.status == HeartbeatStatus.ACTIVE
    session.commit.assert_called_once()
    assert session.refresh.call_count == 2


def test_refresh_heartbeat_statuses_skips_commit_when_none_change() -> None:
    now = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)

    heartbeat = Heartbeat(
        owner_name="Scott",
        owner_email="scott@example.com",
        status=HeartbeatStatus.ACTIVE,
        interval_days=30,
        reminder_days=7,
        next_due_at=datetime(2026, 8, 1, tzinfo=UTC),
    )

    session = MagicMock()

    result = refresh_heartbeat_statuses(
        session,
        [heartbeat],
        now=now,
    )

    assert result == [heartbeat]
    session.commit.assert_not_called()
    session.refresh.assert_not_called()


def test_evaluate_due_heartbeats_updates_active_heartbeats() -> None:
    now = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)

    overdue = Heartbeat(
        owner_name="Scott",
        owner_email="scott@example.com",
        status=HeartbeatStatus.ACTIVE,
        interval_days=30,
        reminder_days=7,
        next_due_at=datetime(2026, 7, 1, tzinfo=UTC),
    )

    current = Heartbeat(
        owner_name="Zoe",
        owner_email="zoe@example.com",
        status=HeartbeatStatus.ACTIVE,
        interval_days=30,
        reminder_days=7,
        next_due_at=datetime(2026, 8, 1, tzinfo=UTC),
    )

    session = MagicMock()
    session.query.return_value.filter.return_value.all.return_value = [
        overdue,
        current,
    ]

    result = evaluate_due_heartbeats(
        session,
        now=now,
    )

    assert result == HeartbeatEvaluationResult(
        evaluated=2,
        changed=1,
    )
    assert overdue.status == HeartbeatStatus.OVERDUE
    assert current.status == HeartbeatStatus.ACTIVE
    session.commit.assert_called_once()
    assert session.refresh.call_count == 2


def test_evaluate_due_heartbeats_returns_zero_when_none_are_active() -> None:
    now = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)

    session = MagicMock()
    session.query.return_value.filter.return_value.all.return_value = []

    result = evaluate_due_heartbeats(
        session,
        now=now,
    )

    assert result == HeartbeatEvaluationResult(
        evaluated=0,
        changed=0,
    )
    session.commit.assert_not_called()
    session.refresh.assert_not_called()


def test_evaluate_due_heartbeats_does_not_commit_when_none_are_due() -> None:
    now = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)

    heartbeat = Heartbeat(
        owner_name="Scott",
        owner_email="scott@example.com",
        status=HeartbeatStatus.ACTIVE,
        interval_days=30,
        reminder_days=7,
        next_due_at=datetime(2026, 8, 1, tzinfo=UTC),
    )

    session = MagicMock()
    session.query.return_value.filter.return_value.all.return_value = [
        heartbeat,
    ]

    result = evaluate_due_heartbeats(
        session,
        now=now,
    )

    assert result == HeartbeatEvaluationResult(
        evaluated=1,
        changed=0,
    )
    assert heartbeat.status == HeartbeatStatus.ACTIVE
    session.commit.assert_not_called()
    session.refresh.assert_not_called()


def test_heartbeat_evaluation_result_is_immutable() -> None:
    result = HeartbeatEvaluationResult(
        evaluated=10,
        changed=2,
    )

    with pytest.raises(AttributeError):
        result.changed = 3


def test_create_heartbeat_uses_configured_lifecycle_day(
    monkeypatch,
) -> None:
    now = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)
    session = MagicMock()

    monkeypatch.setattr(settings, "lifecycle_day_seconds", 60)

    request = HeartbeatCreate(
        owner_name="Scott",
        owner_email="scott@example.com",
        interval_days=30,
        reminder_days=7,
    )

    heartbeat = create_heartbeat(
        session,
        request,
        clock=lambda: now,
    )

    assert heartbeat.next_due_at == now + timedelta(minutes=30)


def test_create_heartbeat_checkin_uses_configured_lifecycle_day(
    monkeypatch,
) -> None:
    now = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)
    heartbeat_id = uuid4()

    monkeypatch.setattr(settings, "lifecycle_day_seconds", 60)

    heartbeat = Heartbeat(
        id=heartbeat_id,
        owner_name="Scott",
        owner_email="scott@example.com",
        status=HeartbeatStatus.OVERDUE,
        interval_days=30,
        reminder_days=7,
        next_due_at=datetime(2026, 7, 1, tzinfo=UTC),
    )

    session = MagicMock()
    session.get.return_value = heartbeat

    create_heartbeat_checkin(
        session,
        heartbeat_id,
        HeartbeatCheckInCreate(),
        clock=lambda: now,
    )

    assert heartbeat.next_due_at == now + timedelta(minutes=30)
