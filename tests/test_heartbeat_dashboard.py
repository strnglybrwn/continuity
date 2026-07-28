from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient

from app.domain.heartbeat import HeartbeatEventType, HeartbeatStatus
from app.main import app
from app.persistence.database import get_db_session
from app.persistence.models import Heartbeat, HeartbeatEvent


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
    assert "Lifecycle Flow" in response.text
    assert "Policy Editor" in response.text
    assert "Core identity" in response.text
    assert "Heartbeat Settings" in response.text
    assert "01/08/2026 11:00 BST" in response.text
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


def test_heartbeat_dashboard_prefers_pending_event_timestamps_for_timeline(monkeypatch) -> None:
    heartbeat = Heartbeat(
        id=uuid4(),
        owner_name="Scott",
        owner_email="scott@example.com",
        status=HeartbeatStatus.OVERDUE,
        interval_days=2,
        reminder_days=0,
        escalation_enabled=True,
        escalation_delay_days=1,
        escalation_contact_name="Ops",
        escalation_contact_email="ops@example.com",
        last_checkin_at=datetime(2026, 7, 24, 20, 0, tzinfo=UTC),
        next_due_at=datetime(2026, 7, 26, 20, 5, tzinfo=UTC),
        created_at=datetime(2026, 7, 20, 20, 0, tzinfo=UTC),
        updated_at=datetime(2026, 7, 26, 20, 0, tzinfo=UTC),
    )
    heartbeat.events = [
        HeartbeatEvent(
            id=uuid4(),
            heartbeat_id=heartbeat.id,
            event_type=HeartbeatEventType.REMINDER_DUE,
            occurred_at=datetime(2026, 7, 26, 20, 0, tzinfo=UTC),
            created_at=datetime(2026, 7, 26, 20, 0, tzinfo=UTC),
        ),
        HeartbeatEvent(
            id=uuid4(),
            heartbeat_id=heartbeat.id,
            event_type=HeartbeatEventType.OVERDUE,
            occurred_at=datetime(2026, 7, 26, 20, 5, tzinfo=UTC),
            created_at=datetime(2026, 7, 26, 20, 5, tzinfo=UTC),
        ),
        HeartbeatEvent(
            id=uuid4(),
            heartbeat_id=heartbeat.id,
            event_type=HeartbeatEventType.ESCALATION_DUE,
            occurred_at=datetime(2026, 7, 26, 20, 10, tzinfo=UTC),
            created_at=datetime(2026, 7, 26, 20, 10, tzinfo=UTC),
        ),
    ]

    monkeypatch.setattr(
        "app.api.heartbeat_dashboard.list_heartbeats",
        lambda _session: [heartbeat],
    )

    session = MagicMock()
    app.dependency_overrides[get_db_session] = override_session(session)

    try:
        client = TestClient(app)
        response = client.get("/ui/heartbeats")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "26/07/2026 21:00 BST" in response.text
    assert "26/07/2026 21:05 BST" in response.text
    assert "26/07/2026 21:10 BST" in response.text


def test_heartbeat_dashboard_uses_delivered_event_times_for_timeline(monkeypatch) -> None:
    heartbeat = Heartbeat(
        id=uuid4(),
        owner_name="Scott",
        owner_email="scott@example.com",
        status=HeartbeatStatus.OVERDUE,
        interval_days=2,
        reminder_days=0,
        escalation_enabled=True,
        escalation_delay_days=1,
        escalation_contact_name="Ops",
        escalation_contact_email="ops@example.com",
        last_checkin_at=datetime(2026, 7, 24, 20, 0, tzinfo=UTC),
        next_due_at=datetime(2026, 7, 26, 20, 5, tzinfo=UTC),
        created_at=datetime(2026, 7, 20, 20, 0, tzinfo=UTC),
        updated_at=datetime(2026, 7, 26, 20, 0, tzinfo=UTC),
    )
    heartbeat.events = [
        HeartbeatEvent(
            id=uuid4(),
            heartbeat_id=heartbeat.id,
            event_type=HeartbeatEventType.REMINDER_DUE,
            occurred_at=datetime(2026, 7, 26, 20, 0, tzinfo=UTC),
            delivered_at=datetime(2026, 7, 26, 20, 0, 30, tzinfo=UTC),
            created_at=datetime(2026, 7, 26, 20, 0, tzinfo=UTC),
        ),
        HeartbeatEvent(
            id=uuid4(),
            heartbeat_id=heartbeat.id,
            event_type=HeartbeatEventType.OVERDUE,
            occurred_at=datetime(2026, 7, 26, 20, 5, tzinfo=UTC),
            delivered_at=datetime(2026, 7, 26, 20, 5, 30, tzinfo=UTC),
            created_at=datetime(2026, 7, 26, 20, 5, tzinfo=UTC),
        ),
        HeartbeatEvent(
            id=uuid4(),
            heartbeat_id=heartbeat.id,
            event_type=HeartbeatEventType.ESCALATION_DUE,
            occurred_at=datetime(2026, 7, 26, 20, 10, tzinfo=UTC),
            delivered_at=datetime(2026, 7, 26, 20, 10, 30, tzinfo=UTC),
            created_at=datetime(2026, 7, 26, 20, 10, tzinfo=UTC),
        ),
        HeartbeatEvent(
            id=uuid4(),
            heartbeat_id=heartbeat.id,
            event_type=HeartbeatEventType.ESCALATION_DUE,
            occurred_at=datetime(2030, 1, 1, 0, 0, tzinfo=UTC),
            delivered_at=datetime(2026, 7, 26, 20, 11, tzinfo=UTC),
            created_at=datetime(2026, 7, 26, 20, 11, tzinfo=UTC),
        ),
    ]

    monkeypatch.setattr(
        "app.api.heartbeat_dashboard.list_heartbeats",
        lambda _session: [heartbeat],
    )

    session = MagicMock()
    app.dependency_overrides[get_db_session] = override_session(session)

    try:
        client = TestClient(app)
        response = client.get("/ui/heartbeats")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "26/07/2026 21:00 BST" in response.text
    assert "26/07/2026 21:05 BST" in response.text
    assert "26/07/2026 21:10 BST" in response.text


def test_heartbeat_dashboard_update_redirects_with_success(monkeypatch) -> None:
    heartbeat_id = uuid4()
    session = MagicMock()

    called: dict[str, object] = {}

    def fake_update(
        _session,
        _heartbeat_id,
        *,
        owner_name,
        owner_email,
        interval_days,
        reminder_days,
        escalation_enabled,
        escalation_delay_days,
        escalation_contact_name,
        escalation_contact_email,
        next_due_at_override,
        reminder_at_override,
        escalation_at_override,
        now,
    ):
        called["heartbeat_id"] = _heartbeat_id
        called["owner_name"] = owner_name
        called["owner_email"] = owner_email
        called["interval_days"] = interval_days
        called["reminder_days"] = reminder_days
        called["escalation_enabled"] = escalation_enabled
        called["escalation_delay_days"] = escalation_delay_days
        called["escalation_contact_name"] = escalation_contact_name
        called["escalation_contact_email"] = escalation_contact_email
        called["next_due_at_override"] = next_due_at_override
        called["reminder_at_override"] = reminder_at_override
        called["escalation_at_override"] = escalation_at_override
        called["now"] = now
        heartbeat = MagicMock()
        heartbeat.id = heartbeat_id
        return heartbeat

    monkeypatch.setattr(
        "app.api.heartbeat_dashboard.update_heartbeat_dashboard_settings",
        fake_update,
    )

    baseline = Heartbeat(
        id=heartbeat_id,
        owner_name="Original",
        owner_email="original@example.com",
        status=HeartbeatStatus.ACTIVE,
        interval_days=30,
        reminder_days=7,
        escalation_enabled=True,
        escalation_delay_days=1,
        escalation_contact_name="Ops",
        escalation_contact_email="ops@example.com",
        last_checkin_at=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
        next_due_at=datetime(2026, 7, 31, 10, 0, tzinfo=UTC),
        created_at=datetime(2026, 6, 1, 10, 0, tzinfo=UTC),
        updated_at=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
    )
    session.get.return_value = baseline

    app.dependency_overrides[get_db_session] = override_session(session)

    try:
        client = TestClient(app)
        response = client.post(
            f"/ui/heartbeats/{heartbeat_id}",
            data={
                "owner_name": "New Owner",
                "owner_email": "new@example.com",
                "reminder_at": "2026-07-12T11:00",
                "overdue_at": "2026-07-15T11:00",
                "escalation_at": "2026-07-18T11:00",
                "escalation_enabled": "true",
                "escalation_contact_name": "Ops Lead",
                "escalation_contact_email": "ops@example.com",
            },
            files={},
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert str(heartbeat_id) in response.headers["location"]
    assert called == {
        "heartbeat_id": heartbeat_id,
        "owner_name": "New Owner",
        "owner_email": "new@example.com",
        "interval_days": 14,
        "reminder_days": 3,
        "escalation_enabled": True,
        "escalation_delay_days": 3,
        "escalation_contact_name": "Ops Lead",
        "escalation_contact_email": "ops@example.com",
        "next_due_at_override": datetime(2026, 7, 15, 10, 0, tzinfo=UTC),
        "reminder_at_override": datetime(2026, 7, 12, 10, 0, tzinfo=UTC),
        "escalation_at_override": datetime(2026, 7, 18, 10, 0, tzinfo=UTC),
        "now": called["now"],
    }


def test_heartbeat_dashboard_update_validation_error(monkeypatch) -> None:
    heartbeat_id = uuid4()
    session = MagicMock()

    monkeypatch.setattr(
        "app.api.heartbeat_dashboard.update_heartbeat_dashboard_settings",
        lambda *_args, **_kwargs: None,
    )

    app.dependency_overrides[get_db_session] = override_session(session)
    heartbeat = Heartbeat(
        id=heartbeat_id,
        owner_name="Original",
        owner_email="original@example.com",
        status=HeartbeatStatus.ACTIVE,
        interval_days=30,
        reminder_days=7,
        escalation_enabled=False,
        escalation_delay_days=1,
        escalation_contact_name=None,
        escalation_contact_email=None,
        last_checkin_at=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
        next_due_at=datetime(2026, 7, 31, 10, 0, tzinfo=UTC),
        created_at=datetime(2026, 6, 1, 10, 0, tzinfo=UTC),
        updated_at=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
    )
    session.get.return_value = heartbeat

    try:
        client = TestClient(app)
        response = client.post(
            f"/ui/heartbeats/{heartbeat_id}",
            data={
                "owner_name": "New Owner",
                "owner_email": "not-an-email",
                "reminder_at": "2026-07-12T11:00",
                "overdue_at": "2026-07-15T11:00",
                "escalation_at": "2026-07-16T11:00",
            },
            files={},
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "error=" in response.headers["location"]


def test_heartbeat_dashboard_create_redirects_with_success(monkeypatch) -> None:
    session = MagicMock()
    created_heartbeat_id = uuid4()

    called: dict[str, object] = {}

    def fake_create_heartbeat(_session, request):
        called["request"] = request
        heartbeat = MagicMock()
        heartbeat.id = created_heartbeat_id
        return heartbeat

    monkeypatch.setattr(
        "app.api.heartbeat_dashboard.create_heartbeat",
        fake_create_heartbeat,
    )

    app.dependency_overrides[get_db_session] = override_session(session)

    try:
        client = TestClient(app)
        response = client.post(
            "/ui/heartbeats",
            data={
                "owner_name": "New Owner",
                "owner_email": "new@example.com",
                "escalation_enabled": "true",
                "escalation_contact_name": "Ops Lead",
                "escalation_contact_email": "ops@example.com",
            },
            files={},
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert str(created_heartbeat_id) in response.headers["location"]
    assert "created=" in response.headers["location"]

    request = called["request"]
    assert request.owner_name == "New Owner"
    assert str(request.owner_email) == "new@example.com"
    assert request.interval_days == 30
    assert request.reminder_days == 7
    assert request.escalation_enabled is True
    assert request.escalation_delay_days == 1
    assert request.escalation_contact_name == "Ops Lead"
    assert str(request.escalation_contact_email) == "ops@example.com"


def test_heartbeat_dashboard_create_validation_error(monkeypatch) -> None:
    session = MagicMock()

    create_called = MagicMock()
    monkeypatch.setattr(
        "app.api.heartbeat_dashboard.create_heartbeat",
        create_called,
    )

    app.dependency_overrides[get_db_session] = override_session(session)

    try:
        client = TestClient(app)
        response = client.post(
            "/ui/heartbeats",
            data={
                "owner_name": "New Owner",
                "owner_email": "not-an-email",
            },
            files={},
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "error=" in response.headers["location"]
    create_called.assert_not_called()


def test_heartbeat_dashboard_delete_redirects_with_success(monkeypatch) -> None:
    heartbeat_id = uuid4()
    session = MagicMock()

    monkeypatch.setattr(
        "app.api.heartbeat_dashboard.delete_heartbeat",
        lambda _session, _heartbeat_id: True,
    )

    app.dependency_overrides[get_db_session] = override_session(session)

    try:
        client = TestClient(app)
        response = client.post(
            f"/ui/heartbeats/{heartbeat_id}/delete",
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert str(heartbeat_id) in response.headers["location"]
    assert "deleted=" in response.headers["location"]


def test_heartbeat_dashboard_delete_returns_error_when_not_found(monkeypatch) -> None:
    heartbeat_id = uuid4()
    session = MagicMock()

    monkeypatch.setattr(
        "app.api.heartbeat_dashboard.delete_heartbeat",
        lambda _session, _heartbeat_id: False,
    )

    app.dependency_overrides[get_db_session] = override_session(session)

    try:
        client = TestClient(app)
        response = client.post(
            f"/ui/heartbeats/{heartbeat_id}/delete",
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "error=" in response.headers["location"]


def test_heartbeat_dashboard_page_includes_create_form_and_delete_button(monkeypatch) -> None:
    heartbeat = Heartbeat(
        id=uuid4(),
        owner_name="Scott",
        owner_email="scott@example.com",
        status=HeartbeatStatus.ACTIVE,
        interval_days=30,
        reminder_days=7,
        escalation_enabled=True,
        escalation_delay_days=2,
        escalation_contact_name="Ops Lead",
        escalation_contact_email="ops@example.com",
        last_checkin_at=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
        next_due_at=datetime(2026, 8, 1, 10, 0, tzinfo=UTC),
        created_at=datetime(2026, 6, 1, 10, 0, tzinfo=UTC),
        updated_at=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
    )

    monkeypatch.setattr(
        "app.api.heartbeat_dashboard.list_heartbeats",
        lambda _session: [heartbeat],
    )

    session = MagicMock()
    app.dependency_overrides[get_db_session] = override_session(session)

    try:
        client = TestClient(app)
        response = client.get("/ui/heartbeats")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Add New Heartbeat" in response.text
    assert 'action="/ui/heartbeats"' in response.text
    assert f'action="/ui/heartbeats/{heartbeat.id}/delete"' in response.text
    assert "Delete Heartbeat" in response.text
    assert "Overdue warning to owner" in response.text
    assert "Escalation notice to contact" in response.text
    assert "Escalation attachments" in response.text


def test_heartbeat_dashboard_delete_attachment_redirects_with_success(monkeypatch) -> None:
    heartbeat_id = uuid4()
    attachment_id = uuid4()
    session = MagicMock()

    monkeypatch.setattr(
        "app.api.heartbeat_dashboard.delete_heartbeat_attachment",
        lambda _session, _heartbeat_id, _attachment_id: True,
    )

    app.dependency_overrides[get_db_session] = override_session(session)

    try:
        client = TestClient(app)
        response = client.post(
            f"/ui/heartbeats/{heartbeat_id}/attachments/{attachment_id}/delete",
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert str(heartbeat_id) in response.headers["location"]
    assert "updated=" in response.headers["location"]


def test_heartbeat_dashboard_delete_attachment_returns_error_when_not_found(monkeypatch) -> None:
    heartbeat_id = uuid4()
    attachment_id = uuid4()
    session = MagicMock()

    monkeypatch.setattr(
        "app.api.heartbeat_dashboard.delete_heartbeat_attachment",
        lambda _session, _heartbeat_id, _attachment_id: False,
    )

    app.dependency_overrides[get_db_session] = override_session(session)

    try:
        client = TestClient(app)
        response = client.post(
            f"/ui/heartbeats/{heartbeat_id}/attachments/{attachment_id}/delete",
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "error=" in response.headers["location"]
