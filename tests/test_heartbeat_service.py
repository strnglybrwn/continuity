from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from uuid import uuid4

from app.config import settings
from app.api.heartbeat_schemas import (
    HeartbeatCheckInCreate,
    HeartbeatCreate,
)
from app.domain.heartbeat import (
    CheckInStatus,
    HeartbeatEventType,
    HeartbeatStatus,
)
from app.persistence.models import Heartbeat, HeartbeatEvent
from app.services.heartbeat_service import (
    HeartbeatEvaluationResult,
    create_heartbeat,
    create_heartbeat_checkin,
    delete_heartbeat,
    determine_heartbeat_status,
    evaluate_due_heartbeats,
    is_heartbeat_reminder_due,
    record_heartbeat_event,
    refresh_heartbeat_status,
    refresh_heartbeat_statuses,
    update_heartbeat_dashboard_settings,
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
    assert heartbeat.escalation_enabled is False
    assert heartbeat.escalation_delay_days == 1
    assert heartbeat.escalation_contact_name is None
    assert heartbeat.escalation_contact_email is None

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
    session.scalar.return_value = None

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

    added_objects = [call.args[0] for call in session.add.call_args_list]
    assert checkin in added_objects
    assert any(
        isinstance(item, HeartbeatEvent) and item.event_type == HeartbeatEventType.CHECKED_IN
        for item in added_objects
    )
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


def test_update_heartbeat_dashboard_settings_recalculates_due_at() -> None:
    now = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)
    heartbeat = Heartbeat(
        id=uuid4(),
        owner_name="Scott",
        owner_email="scott@example.com",
        status=HeartbeatStatus.ACTIVE,
        interval_days=30,
        reminder_days=7,
        last_checkin_at=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
        next_due_at=datetime(2026, 8, 1, 10, 0, tzinfo=UTC),
    )

    session = MagicMock()
    session.get.return_value = heartbeat

    result = update_heartbeat_dashboard_settings(
        session,
        heartbeat.id,
        owner_name="Zoe",
        owner_email="zoe@example.com",
        interval_days=14,
        reminder_days=3,
        arm_reminder_now=False,
        now=now,
    )

    assert result is heartbeat
    assert heartbeat.owner_name == "Zoe"
    assert heartbeat.owner_email == "zoe@example.com"
    assert heartbeat.interval_days == 14
    assert heartbeat.reminder_days == 3
    assert heartbeat.next_due_at == datetime(2026, 7, 15, 10, 0, tzinfo=UTC)
    session.commit.assert_called_once()
    session.refresh.assert_called_once_with(heartbeat)


def test_update_heartbeat_dashboard_settings_arms_reminder_now() -> None:
    now = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)
    heartbeat = Heartbeat(
        id=uuid4(),
        owner_name="Scott",
        owner_email="scott@example.com",
        status=HeartbeatStatus.OVERDUE,
        interval_days=30,
        reminder_days=7,
        last_checkin_at=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
        next_due_at=datetime(2026, 7, 10, 10, 0, tzinfo=UTC),
    )

    session = MagicMock()
    session.get.return_value = heartbeat

    result = update_heartbeat_dashboard_settings(
        session,
        heartbeat.id,
        owner_name="Scott",
        owner_email="scott@example.com",
        interval_days=30,
        reminder_days=7,
        arm_reminder_now=True,
        now=now,
    )

    assert result is heartbeat
    assert heartbeat.status == HeartbeatStatus.ACTIVE
    assert heartbeat.next_due_at == datetime(2026, 7, 22, 13, 0, tzinfo=UTC)


def test_update_heartbeat_dashboard_settings_rejects_invalid_reminder_window() -> None:
    heartbeat = Heartbeat(
        id=uuid4(),
        owner_name="Scott",
        owner_email="scott@example.com",
        status=HeartbeatStatus.ACTIVE,
        interval_days=30,
        reminder_days=7,
        next_due_at=datetime(2026, 8, 1, 10, 0, tzinfo=UTC),
    )

    session = MagicMock()
    session.get.return_value = heartbeat

    with pytest.raises(ValueError, match="reminder_days must be less than interval_days"):
        update_heartbeat_dashboard_settings(
            session,
            heartbeat.id,
            owner_name="Scott",
            owner_email="scott@example.com",
            interval_days=5,
            reminder_days=7,
            arm_reminder_now=False,
        )


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


def test_heartbeat_complete_accelerated_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_at = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)
    heartbeat_id = uuid4()
    session = MagicMock()

    monkeypatch.setattr(settings, "lifecycle_day_seconds", 60)

    heartbeat = create_heartbeat(
        session,
        HeartbeatCreate(
            owner_name="Scott",
            owner_email="scott@example.com",
            interval_days=30,
            reminder_days=7,
        ),
        clock=lambda: created_at,
    )
    heartbeat.id = heartbeat_id

    assert heartbeat.status == HeartbeatStatus.ACTIVE
    assert heartbeat.next_due_at == created_at + timedelta(minutes=30)

    session.query.return_value.filter.return_value.all.return_value = [
        heartbeat,
    ]

    evaluation = evaluate_due_heartbeats(
        session,
        now=heartbeat.next_due_at,
    )

    assert evaluation == HeartbeatEvaluationResult(
        evaluated=1,
        changed=1,
    )
    assert heartbeat.status == HeartbeatStatus.OVERDUE

    checked_in_at = created_at + timedelta(minutes=35)
    session.get.return_value = heartbeat

    checkin = create_heartbeat_checkin(
        session,
        heartbeat_id,
        HeartbeatCheckInCreate(),
        clock=lambda: checked_in_at,
    )

    assert checkin is not None
    assert checkin.created_at == checked_in_at
    assert heartbeat.status == HeartbeatStatus.ACTIVE
    assert heartbeat.last_checkin_at == checked_in_at
    assert heartbeat.next_due_at == checked_in_at + timedelta(minutes=30)


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (datetime(2026, 7, 22, 11, 52, tzinfo=UTC), False),
        (datetime(2026, 7, 22, 11, 53, tzinfo=UTC), True),
        (datetime(2026, 7, 22, 11, 59, tzinfo=UTC), True),
        (datetime(2026, 7, 22, 12, 0, tzinfo=UTC), False),
    ],
)
def test_heartbeat_reminder_due_window(
    monkeypatch: pytest.MonkeyPatch,
    now: datetime,
    expected: bool,
) -> None:
    monkeypatch.setattr(settings, "lifecycle_day_seconds", 60)

    heartbeat = Heartbeat(
        id=uuid4(),
        owner_name="Scott",
        owner_email="scott@example.com",
        status=HeartbeatStatus.ACTIVE,
        interval_days=30,
        reminder_days=7,
        next_due_at=datetime(2026, 7, 22, 12, 0, tzinfo=UTC),
    )

    assert (
        is_heartbeat_reminder_due(
            heartbeat,
            now=now,
        )
        is expected
    )


@pytest.mark.parametrize(
    "status",
    [
        HeartbeatStatus.OVERDUE,
        HeartbeatStatus.PAUSED,
        HeartbeatStatus.CANCELLED,
    ],
)
def test_heartbeat_reminder_not_due_for_inactive_status(
    monkeypatch: pytest.MonkeyPatch,
    status: HeartbeatStatus,
) -> None:
    monkeypatch.setattr(settings, "lifecycle_day_seconds", 60)

    heartbeat = Heartbeat(
        id=uuid4(),
        owner_name="Scott",
        owner_email="scott@example.com",
        status=status,
        interval_days=30,
        reminder_days=7,
        next_due_at=datetime(2026, 7, 22, 12, 0, tzinfo=UTC),
    )

    assert (
        is_heartbeat_reminder_due(
            heartbeat,
            now=datetime(2026, 7, 22, 11, 55, tzinfo=UTC),
        )
        is False
    )


def test_heartbeat_with_zero_reminder_days_has_no_advance_reminder() -> None:
    heartbeat = Heartbeat(
        id=uuid4(),
        owner_name="Scott",
        owner_email="scott@example.com",
        status=HeartbeatStatus.ACTIVE,
        interval_days=30,
        reminder_days=0,
        next_due_at=datetime(2026, 7, 22, 12, 0, tzinfo=UTC),
    )

    assert (
        is_heartbeat_reminder_due(
            heartbeat,
            now=datetime(2026, 7, 22, 11, 59, tzinfo=UTC),
        )
        is False
    )


def test_record_heartbeat_event_creates_new_event() -> None:
    heartbeat = Heartbeat(
        id=uuid4(),
        owner_name="Scott",
        owner_email="scott@example.com",
        status=HeartbeatStatus.ACTIVE,
        interval_days=30,
        reminder_days=7,
        next_due_at=datetime(2026, 8, 21, tzinfo=UTC),
    )
    occurred_at = datetime(2026, 8, 14, tzinfo=UTC)

    session = MagicMock()
    session.scalar.return_value = None

    event = record_heartbeat_event(
        session,
        heartbeat,
        HeartbeatEventType.REMINDER_DUE,
        occurred_at=occurred_at,
    )

    assert event is not None
    assert event.heartbeat_id == heartbeat.id
    assert event.event_type == HeartbeatEventType.REMINDER_DUE
    assert event.occurred_at == occurred_at
    assert event.created_at == occurred_at
    session.add.assert_called_once_with(event)


def test_record_heartbeat_event_skips_existing_event() -> None:
    heartbeat = Heartbeat(
        id=uuid4(),
        owner_name="Scott",
        owner_email="scott@example.com",
        status=HeartbeatStatus.ACTIVE,
        interval_days=30,
        reminder_days=7,
        next_due_at=datetime(2026, 8, 21, tzinfo=UTC),
    )

    session = MagicMock()
    session.scalar.return_value = uuid4()

    event = record_heartbeat_event(
        session,
        heartbeat,
        HeartbeatEventType.REMINDER_DUE,
        occurred_at=datetime(2026, 8, 14, tzinfo=UTC),
    )

    assert event is None
    session.add.assert_not_called()


def test_evaluate_due_heartbeats_records_reminder_event() -> None:
    heartbeat = Heartbeat(
        id=uuid4(),
        owner_name="Scott",
        owner_email="scott@example.com",
        status=HeartbeatStatus.ACTIVE,
        interval_days=30,
        reminder_days=7,
        next_due_at=datetime(2026, 8, 21, 12, 0, tzinfo=UTC),
    )

    session = MagicMock()
    session.scalar.return_value = None
    session.query.return_value.filter.return_value.all.return_value = [
        heartbeat,
    ]

    result = evaluate_due_heartbeats(
        session,
        now=datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
    )

    assert result == HeartbeatEvaluationResult(
        evaluated=1,
        changed=0,
    )

    added_event = session.add.call_args.args[0]
    assert isinstance(added_event, HeartbeatEvent)
    assert added_event.event_type == HeartbeatEventType.REMINDER_DUE
    assert added_event.occurred_at == datetime(
        2026,
        8,
        14,
        12,
        0,
        tzinfo=UTC,
    )
    session.commit.assert_called_once()


def test_evaluate_due_heartbeats_records_overdue_event() -> None:
    due_at = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)
    heartbeat = Heartbeat(
        id=uuid4(),
        owner_name="Scott",
        owner_email="scott@example.com",
        status=HeartbeatStatus.ACTIVE,
        interval_days=30,
        reminder_days=7,
        next_due_at=due_at,
    )

    session = MagicMock()
    session.scalar.return_value = None
    session.query.return_value.filter.return_value.all.return_value = [
        heartbeat,
    ]

    result = evaluate_due_heartbeats(
        session,
        now=due_at,
    )

    assert result == HeartbeatEvaluationResult(
        evaluated=1,
        changed=1,
    )
    assert heartbeat.status == HeartbeatStatus.OVERDUE

    added_event = session.add.call_args.args[0]
    assert isinstance(added_event, HeartbeatEvent)
    assert added_event.event_type == HeartbeatEventType.OVERDUE
    assert added_event.occurred_at == due_at


def test_evaluate_due_heartbeats_emits_escalation_event_when_due(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "lifecycle_day_seconds", 60)

    now = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)
    heartbeat = Heartbeat(
        id=uuid4(),
        owner_name="Scott",
        owner_email="scott@example.com",
        status=HeartbeatStatus.OVERDUE,
        interval_days=30,
        reminder_days=7,
        escalation_enabled=True,
        escalation_delay_days=1,
        escalation_contact_name="Zoe",
        escalation_contact_email="zoe@example.com",
        next_due_at=now - timedelta(minutes=2),
    )

    session = MagicMock()
    session.query.return_value.filter.return_value.all.return_value = [heartbeat]
    session.scalar.return_value = None

    result = evaluate_due_heartbeats(
        session,
        now=now,
    )

    assert result == HeartbeatEvaluationResult(
        evaluated=1,
        changed=0,
    )

    added_events = [
        item
        for item in (call.args[0] for call in session.add.call_args_list)
        if isinstance(item, HeartbeatEvent)
    ]
    assert len(added_events) == 1
    assert added_events[0].event_type == HeartbeatEventType.ESCALATION_DUE
    assert added_events[0].occurred_at == heartbeat.next_due_at + timedelta(minutes=1)
    session.commit.assert_called_once()


def test_evaluate_due_heartbeats_deduplicates_escalation_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "lifecycle_day_seconds", 60)

    now = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)
    heartbeat = Heartbeat(
        id=uuid4(),
        owner_name="Scott",
        owner_email="scott@example.com",
        status=HeartbeatStatus.OVERDUE,
        interval_days=30,
        reminder_days=7,
        escalation_enabled=True,
        escalation_delay_days=1,
        escalation_contact_name="Zoe",
        escalation_contact_email="zoe@example.com",
        next_due_at=now - timedelta(minutes=2),
    )

    session = MagicMock()
    session.query.return_value.filter.return_value.all.return_value = [heartbeat]
    session.scalar.return_value = uuid4()

    result = evaluate_due_heartbeats(
        session,
        now=now,
    )

    assert result == HeartbeatEvaluationResult(
        evaluated=1,
        changed=0,
    )
    session.add.assert_not_called()
    session.commit.assert_not_called()


def test_evaluate_due_heartbeats_skips_escalation_without_contact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "lifecycle_day_seconds", 60)

    now = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)
    heartbeat = Heartbeat(
        id=uuid4(),
        owner_name="Scott",
        owner_email="scott@example.com",
        status=HeartbeatStatus.OVERDUE,
        interval_days=30,
        reminder_days=7,
        escalation_enabled=True,
        escalation_delay_days=1,
        escalation_contact_name=None,
        escalation_contact_email=None,
        next_due_at=now - timedelta(minutes=2),
    )

    session = MagicMock()
    session.query.return_value.filter.return_value.all.return_value = [heartbeat]

    result = evaluate_due_heartbeats(
        session,
        now=now,
    )

    assert result == HeartbeatEvaluationResult(
        evaluated=1,
        changed=0,
    )
    session.scalar.assert_not_called()
    session.add.assert_not_called()
    session.commit.assert_not_called()


def test_create_heartbeat_checkin_records_checked_in_event() -> None:
    heartbeat_id = uuid4()
    checked_in_at = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)

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
    session.scalar.return_value = None

    checkin = create_heartbeat_checkin(
        session,
        heartbeat_id,
        HeartbeatCheckInCreate(),
        clock=lambda: checked_in_at,
    )

    assert checkin is not None

    added_objects = [call.args[0] for call in session.add.call_args_list]
    events = [item for item in added_objects if isinstance(item, HeartbeatEvent)]

    assert len(events) == 1
    assert events[0].event_type == HeartbeatEventType.CHECKED_IN
    assert events[0].occurred_at == checked_in_at


def test_delete_heartbeat_removes_existing_heartbeat() -> None:
    heartbeat_id = uuid4()
    heartbeat = Heartbeat(
        id=heartbeat_id,
        owner_name="Scott",
        owner_email="scott@example.com",
        status=HeartbeatStatus.ACTIVE,
        interval_days=30,
        reminder_days=7,
        next_due_at=datetime(2026, 8, 1, tzinfo=UTC),
    )

    session = MagicMock()
    session.get.return_value = heartbeat

    result = delete_heartbeat(session, heartbeat_id)

    assert result is True
    session.delete.assert_called_once_with(heartbeat)
    session.commit.assert_called_once()


def test_delete_heartbeat_returns_false_when_not_found() -> None:
    heartbeat_id = uuid4()
    session = MagicMock()
    session.get.return_value = None

    result = delete_heartbeat(session, heartbeat_id)

    assert result is False
    session.delete.assert_not_called()
    session.commit.assert_not_called()
