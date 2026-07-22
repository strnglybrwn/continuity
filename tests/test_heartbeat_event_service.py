from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

from app.domain.heartbeat import HeartbeatEventType
from app.persistence.models import HeartbeatEvent
from app.services.heartbeat_event_service import (
    list_pending_heartbeat_events,
    mark_heartbeat_event_delivered,
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
