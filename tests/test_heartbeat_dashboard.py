from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient

from app.domain.heartbeat import HeartbeatStatus
from app.main import app
from app.persistence.database import get_db_session
from app.persistence.models import Heartbeat


def override_session(session: MagicMock):
    def dependency_override():
        yield session

    return dependency_override


def test_heartbeat_dashboard_lists_recipient_email(monkeypatch) -> None:
    heartbeat = Heartbeat(
        id=uuid4(),
        owner_name="Scott",
        owner_email="scott@example.com",
        status=HeartbeatStatus.ACTIVE,
        interval_days=30,
        reminder_days=7,
        last_checkin_at=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
        next_due_at=datetime(2026, 8, 1, 10, 0, tzinfo=UTC),
        created_at=datetime(2026, 6, 1, 10, 0, tzinfo=UTC),
        updated_at=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
    )

    def fake_list_heartbeats(_session):
        return [heartbeat]

    monkeypatch.setattr(
        "app.api.heartbeat_dashboard.list_heartbeats",
        fake_list_heartbeats,
    )

    session = MagicMock()
    app.dependency_overrides[get_db_session] = override_session(session)

    try:
        client = TestClient(app)
        response = client.get("/ui/heartbeats")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Heartbeat Verifier" in response.text
    assert "scott@example.com" in response.text
    assert "Total heartbeats: 1" in response.text


def test_heartbeat_dashboard_empty_state(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.heartbeat_dashboard.list_heartbeats",
        lambda _session: [],
    )

    session = MagicMock()
    app.dependency_overrides[get_db_session] = override_session(session)

    try:
        client = TestClient(app)
        response = client.get("/ui/heartbeats")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "No heartbeats found yet." in response.text


def test_heartbeat_dashboard_update_redirects_with_success(monkeypatch) -> None:
    heartbeat_id = uuid4()
    session = MagicMock()

    called: dict[str, object] = {}

    def fake_update(
        _session,
        _heartbeat_id,
        *,
        owner_email,
        reminder_days,
        arm_reminder_now,
    ):
        called["heartbeat_id"] = _heartbeat_id
        called["owner_email"] = owner_email
        called["reminder_days"] = reminder_days
        called["arm_reminder_now"] = arm_reminder_now
        heartbeat = MagicMock()
        heartbeat.id = heartbeat_id
        return heartbeat

    monkeypatch.setattr(
        "app.api.heartbeat_dashboard.update_heartbeat_dashboard_settings",
        fake_update,
    )

    app.dependency_overrides[get_db_session] = override_session(session)

    try:
        client = TestClient(app)
        response = client.post(
            f"/ui/heartbeats/{heartbeat_id}",
            data={
                "owner_email": "new@example.com",
                "reminder_days": "5",
                "arm_reminder_now": "true",
            },
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert str(heartbeat_id) in response.headers["location"]
    assert called == {
        "heartbeat_id": heartbeat_id,
        "owner_email": "new@example.com",
        "reminder_days": 5,
        "arm_reminder_now": True,
    }


def test_heartbeat_dashboard_update_validation_error(monkeypatch) -> None:
    heartbeat_id = uuid4()
    session = MagicMock()

    monkeypatch.setattr(
        "app.api.heartbeat_dashboard.update_heartbeat_dashboard_settings",
        lambda *_args, **_kwargs: None,
    )

    app.dependency_overrides[get_db_session] = override_session(session)

    try:
        client = TestClient(app)
        response = client.post(
            f"/ui/heartbeats/{heartbeat_id}",
            data={
                "owner_email": "not-an-email",
                "reminder_days": "5",
            },
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "error=" in response.headers["location"]
