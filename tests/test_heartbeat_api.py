from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.persistence.database import get_db_session
from app.persistence.models import Heartbeat, HeartbeatCheckIn


def test_create_heartbeat_checkin_endpoint() -> None:
    heartbeat_id = uuid4()
    checkin_id = uuid4()
    created_at = datetime(2026, 7, 22, 8, 30, tzinfo=UTC)

    heartbeat = Heartbeat(
        id=heartbeat_id,
        owner_name="Scott",
        owner_email="scott@example.com",
        interval_days=30,
        reminder_days=7,
        next_due_at=created_at,
    )

    session = MagicMock()
    session.get.return_value = heartbeat

    def refresh(instance: object) -> None:
        if isinstance(instance, HeartbeatCheckIn):
            instance.id = checkin_id
            instance.created_at = created_at

    session.refresh.side_effect = refresh

    def override_database_session():
        yield session

    app.dependency_overrides[get_db_session] = override_database_session

    try:
        client = TestClient(app)
        response = client.post(
            f"/heartbeats/{heartbeat_id}/checkins",
            json={
                "status": "warning",
                "notes": "May need some assistance",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json() == {
        "id": str(checkin_id),
        "heartbeat_id": str(heartbeat_id),
        "status": "warning",
        "notes": "May need some assistance",
        "source": "manual",
        "created_at": created_at.isoformat().replace("+00:00", "Z"),
    }

    session.commit.assert_called_once()


def test_create_heartbeat_checkin_endpoint_returns_404() -> None:
    heartbeat_id = uuid4()
    session = MagicMock()
    session.get.return_value = None

    def override_database_session():
        yield session

    app.dependency_overrides[get_db_session] = override_database_session

    try:
        client = TestClient(app)
        response = client.post(
            f"/heartbeats/{heartbeat_id}/checkins",
            json={},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "Heartbeat not found"}
    session.commit.assert_not_called()
