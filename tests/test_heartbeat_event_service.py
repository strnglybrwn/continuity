from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

from app.domain.heartbeat import HeartbeatEventType
from app.domain.notification import (
    Notification,
    NotificationChannel,
    NotificationMessage,
    NotificationRecipient,
)
from app.persistence.models import HeartbeatEvent
from app.services.heartbeat_event_service import (
    list_pending_heartbeat_events,
    mark_heartbeat_event_delivered,
    prepare_reminder_notification,
    ReminderNotificationPreparationError,
)


def test_list_pending_heartbeat_events_returns_query_results() -> None:
    event = HeartbeatEvent(
        id=uuid4(),
        heartbeat_id=uuid4(),
        event_type=HeartbeatEventType.REMINDER_DUE,
        occurred_at=datetime(2026, 7, 22, 12, 0, tzinfo=UTC),
        created_at=datetime(2026, 7, 22, 12, 0, tzinfo=UTC),
    )

    session = MagicMock()
    query = session.query.return_value
    query.options.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
        event
    ]

    result = list_pending_heartbeat_events(
        session,
        limit=25,
    )

    assert result == [event]
    query.options.return_value.filter.return_value.order_by.return_value.limit.assert_called_once_with(
        25
    )


def test_mark_heartbeat_event_delivered_sets_timestamp() -> None:
    event_id = uuid4()
    delivered_at = datetime(2026, 7, 22, 13, 0, tzinfo=UTC)

    event = HeartbeatEvent(
        id=event_id,
        heartbeat_id=uuid4(),
        event_type=HeartbeatEventType.OVERDUE,
        occurred_at=datetime(2026, 7, 22, 12, 0, tzinfo=UTC),
        created_at=datetime(2026, 7, 22, 12, 0, tzinfo=UTC),
    )

    session = MagicMock()
    session.get.return_value = event

    result = mark_heartbeat_event_delivered(
        session,
        event_id,
        clock=lambda: delivered_at,
    )

    assert result is event
    assert event.delivered_at == delivered_at
    session.commit.assert_called_once()
    session.refresh.assert_called_once_with(event)


def test_mark_heartbeat_event_delivered_is_idempotent() -> None:
    event_id = uuid4()
    original_delivery_time = datetime(
        2026,
        7,
        22,
        13,
        0,
        tzinfo=UTC,
    )

    event = HeartbeatEvent(
        id=event_id,
        heartbeat_id=uuid4(),
        event_type=HeartbeatEventType.CHECKED_IN,
        occurred_at=datetime(2026, 7, 22, 12, 0, tzinfo=UTC),
        delivered_at=original_delivery_time,
        created_at=datetime(2026, 7, 22, 12, 0, tzinfo=UTC),
    )

    session = MagicMock()
    session.get.return_value = event

    result = mark_heartbeat_event_delivered(
        session,
        event_id,
        clock=lambda: datetime(2026, 7, 22, 14, 0, tzinfo=UTC),
    )

    assert result is event
    assert event.delivered_at == original_delivery_time
    session.commit.assert_not_called()
    session.refresh.assert_not_called()


def test_mark_heartbeat_event_delivered_returns_none_when_missing() -> None:
    event_id = uuid4()
    session = MagicMock()
    session.get.return_value = None

    result = mark_heartbeat_event_delivered(
        session,
        event_id,
    )

    assert result is None
    session.commit.assert_not_called()


def test_prepare_reminder_notification_returns_send_ready_payload(
    monkeypatch,
) -> None:
    event_id = uuid4()
    heartbeat_id = uuid4()
    event = HeartbeatEvent(
        id=event_id,
        heartbeat_id=heartbeat_id,
        event_type=HeartbeatEventType.REMINDER_DUE,
        occurred_at=datetime(2026, 7, 22, 12, 0, tzinfo=UTC),
        created_at=datetime(2026, 7, 22, 12, 0, tzinfo=UTC),
    )
    event.heartbeat = MagicMock()
    event.heartbeat.owner_name = "Scott"
    event.heartbeat.owner_email = "scott@example.com"

    session = MagicMock()
    session.get.return_value = event

    monkeypatch.setattr(
        "app.services.heartbeat_event_service.issue_checkin_token",
        MagicMock(
            return_value=MagicMock(
                raw_token="example-token",
            )
        ),
    )

    notification = Notification(
        channel=NotificationChannel.EMAIL,
        recipient=NotificationRecipient(
            name="Scott",
            email="scott@example.com",
        ),
        message=NotificationMessage(
            template_name="heartbeat_reminder",
            template_version=1,
            subject="Continuity check-in reminder",
            text_body="text",
            html_body="html",
        ),
    )
    monkeypatch.setattr(
        "app.services.heartbeat_event_service.build_reminder_notification",
        MagicMock(return_value=notification),
    )

    prepared_event, prepared_notification, checkin_url = prepare_reminder_notification(
        session,
        event_id,
        public_base_url="https://continuity.whistler.com",
    )

    assert prepared_event is event
    assert prepared_notification is notification
    assert checkin_url == "https://continuity.whistler.com/checkins/example-token"


def test_prepare_reminder_notification_rejects_non_reminder_event() -> None:
    event_id = uuid4()
    event = HeartbeatEvent(
        id=event_id,
        heartbeat_id=uuid4(),
        event_type=HeartbeatEventType.OVERDUE,
        occurred_at=datetime(2026, 7, 22, 12, 0, tzinfo=UTC),
        created_at=datetime(2026, 7, 22, 12, 0, tzinfo=UTC),
    )

    session = MagicMock()
    session.get.return_value = event

    try:
        prepare_reminder_notification(
            session,
            event_id,
            public_base_url="https://continuity.whistler.com",
        )
    except ReminderNotificationPreparationError as exc:
        assert str(exc) == "Heartbeat event is not a reminder event"
    else:
        raise AssertionError("Expected ReminderNotificationPreparationError")


def test_prepare_reminder_notification_rejects_delivered_event() -> None:
    event_id = uuid4()
    event = HeartbeatEvent(
        id=event_id,
        heartbeat_id=uuid4(),
        event_type=HeartbeatEventType.REMINDER_DUE,
        occurred_at=datetime(2026, 7, 22, 12, 0, tzinfo=UTC),
        delivered_at=datetime(2026, 7, 22, 13, 0, tzinfo=UTC),
        created_at=datetime(2026, 7, 22, 12, 0, tzinfo=UTC),
    )

    session = MagicMock()
    session.get.return_value = event

    try:
        prepare_reminder_notification(
            session,
            event_id,
            public_base_url="https://continuity.whistler.com",
        )
    except ReminderNotificationPreparationError as exc:
        assert str(exc) == "Heartbeat event is already delivered"
    else:
        raise AssertionError("Expected ReminderNotificationPreparationError")
