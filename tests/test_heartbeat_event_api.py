from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient

from app.domain.heartbeat import HeartbeatEventType, HeartbeatStatus
from app.main import app
from app.persistence.database import get_db_session
from app.persistence.models import Heartbeat, HeartbeatEvent


def test_list_pending_heartbeat_events_endpoint() -> None:
    heartbeat_id = uuid4()
    event_id = uuid4()
    occurred_at = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)

    heartbeat = Heartbeat(
        id=heartbeat_id,
        owner_name="Scott",
        owner_email="scott@example.com",
        status=HeartbeatStatus.ACTIVE,
        interval_days=30,
        reminder_days=7,
        next_due_at=datetime(2026, 8, 21, tzinfo=UTC),
    )

    event = HeartbeatEvent(
        id=event_id,
        heartbeat_id=heartbeat_id,
        event_type=HeartbeatEventType.REMINDER_DUE,
        occurred_at=occurred_at,
        created_at=occurred_at,
    )
    event.heartbeat = heartbeat

    session = MagicMock()
    query = session.query.return_value
    query.options.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
        event
    ]

    def override_database_session():
        yield session

    app.dependency_overrides[get_db_session] = override_database_session

    try:
        response = TestClient(app).get("/heartbeat-events/pending?limit=25")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": str(event_id),
            "heartbeat_id": str(heartbeat_id),
            "event_type": "reminder_due",
            "occurred_at": occurred_at.isoformat().replace(
                "+00:00",
                "Z",
            ),
            "delivered_at": None,
            "created_at": occurred_at.isoformat().replace(
                "+00:00",
                "Z",
            ),
            "owner_name": "Scott",
            "owner_email": "scott@example.com",
        }
    ]


def test_mark_heartbeat_event_delivered_endpoint() -> None:
    heartbeat_id = uuid4()
    event_id = uuid4()
    occurred_at = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)
    delivered_at = datetime(2026, 7, 22, 13, 0, tzinfo=UTC)

    event = HeartbeatEvent(
        id=event_id,
        heartbeat_id=heartbeat_id,
        event_type=HeartbeatEventType.OVERDUE,
        occurred_at=occurred_at,
        created_at=occurred_at,
    )

    session = MagicMock()
    session.get.return_value = event

    def refresh(instance: object) -> None:
        if isinstance(instance, HeartbeatEvent):
            instance.delivered_at = delivered_at

    session.refresh.side_effect = refresh

    def override_database_session():
        yield session

    app.dependency_overrides[get_db_session] = override_database_session

    try:
        response = TestClient(app).post(f"/heartbeat-events/{event_id}/delivered")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "id": str(event_id),
        "heartbeat_id": str(heartbeat_id),
        "event_type": "overdue",
        "occurred_at": occurred_at.isoformat().replace(
            "+00:00",
            "Z",
        ),
        "delivered_at": delivered_at.isoformat().replace(
            "+00:00",
            "Z",
        ),
        "created_at": occurred_at.isoformat().replace(
            "+00:00",
            "Z",
        ),
    }

    session.commit.assert_called_once()


def test_mark_heartbeat_event_delivered_endpoint_returns_404() -> None:
    event_id = uuid4()
    session = MagicMock()
    session.get.return_value = None

    def override_database_session():
        yield session

    app.dependency_overrides[get_db_session] = override_database_session

    try:
        response = TestClient(app).post(f"/heartbeat-events/{event_id}/delivered")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "Heartbeat event not found"}
    session.commit.assert_not_called()


def test_pending_heartbeat_event_limit_is_validated() -> None:
    response = TestClient(app).get("/heartbeat-events/pending?limit=0")

    assert response.status_code == 422
