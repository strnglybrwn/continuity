from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient

from app.domain.heartbeat import HeartbeatStatus
from app.main import app
from app.persistence.database import get_db_session
from app.persistence.models import Heartbeat, HeartbeatCheckInToken
from app.services.checkin_token_service import hash_checkin_token


RAW_TOKEN = "valid-public-checkin-token"
REDEEMED_AT = datetime(2026, 7, 22, 15, 0, tzinfo=UTC)


def make_heartbeat() -> Heartbeat:
    return Heartbeat(
        id=uuid4(),
        owner_name="Scott",
        owner_email="scott@example.com",
        status=HeartbeatStatus.OVERDUE,
        interval_days=30,
        reminder_days=7,
        next_due_at=datetime(2026, 7, 1, tzinfo=UTC),
    )


def make_token(
    heartbeat: Heartbeat,
    *,
    expires_at: datetime | None = None,
    used_at: datetime | None = None,
) -> HeartbeatCheckInToken:
    return HeartbeatCheckInToken(
        id=uuid4(),
        heartbeat_id=heartbeat.id,
        token_hash=hash_checkin_token(RAW_TOKEN),
        expires_at=expires_at or datetime(2100, 1, 1, tzinfo=UTC),
        used_at=used_at,
        created_at=REDEEMED_AT - timedelta(hours=1),
    )


def override_session(session: MagicMock):
    def dependency_override():
        yield session

    return dependency_override


def test_get_checkin_page_displays_post_confirmation_form() -> None:
    session = MagicMock()
    app.dependency_overrides[get_db_session] = override_session(session)

    try:
        client = TestClient(app)
        response = client.get(f"/checkins/{RAW_TOKEN}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Confirm your check-in" in response.text
    assert 'method="post"' in response.text.lower()
    assert f'action="/checkins/{RAW_TOKEN}"' in response.text

    session.execute.assert_not_called()
    session.get.assert_not_called()
    session.commit.assert_not_called()


def test_get_checkin_page_does_not_validate_unknown_token() -> None:
    session = MagicMock()
    app.dependency_overrides[get_db_session] = override_session(session)

    try:
        client = TestClient(app)
        response = client.get("/checkins/unknown-token")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Confirm your check-in" in response.text

    session.execute.assert_not_called()
    session.get.assert_not_called()
    session.commit.assert_not_called()


def test_post_checkin_redeems_valid_token() -> None:
    heartbeat = make_heartbeat()
    token = make_token(heartbeat)

    session = MagicMock()
    session.execute.return_value.scalar_one_or_none.return_value = token
    session.get.return_value = heartbeat

    app.dependency_overrides[get_db_session] = override_session(session)

    try:
        client = TestClient(app)
        response = client.post(f"/checkins/{RAW_TOKEN}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Check-in confirmed" in response.text
    assert RAW_TOKEN not in response.text

    assert token.used_at is not None
    assert heartbeat.status == HeartbeatStatus.ACTIVE
    assert heartbeat.last_checkin_at is not None
    assert heartbeat.next_due_at == heartbeat.last_checkin_at + timedelta(days=30)

    session.add.assert_called_once()
    session.commit.assert_called_once()


def test_post_checkin_returns_unavailable_for_unknown_token() -> None:
    session = MagicMock()
    session.execute.return_value.scalar_one_or_none.return_value = None

    app.dependency_overrides[get_db_session] = override_session(session)

    try:
        client = TestClient(app)
        response = client.post("/checkins/unknown-token")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Check-in unavailable" in response.text
    assert "unknown" not in response.text.lower()

    session.get.assert_not_called()
    session.add.assert_not_called()
    session.commit.assert_not_called()


def test_post_checkin_returns_unavailable_for_expired_token() -> None:
    heartbeat = make_heartbeat()
    token = make_token(
        heartbeat,
        expires_at=datetime(2020, 1, 1, tzinfo=UTC),
    )

    session = MagicMock()
    session.execute.return_value.scalar_one_or_none.return_value = token

    app.dependency_overrides[get_db_session] = override_session(session)

    try:
        client = TestClient(app)
        response = client.post(f"/checkins/{RAW_TOKEN}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Check-in unavailable" in response.text
    assert "expired" not in response.text.lower()

    session.get.assert_not_called()
    session.add.assert_not_called()
    session.commit.assert_not_called()


def test_post_checkin_returns_unavailable_for_used_token() -> None:
    heartbeat = make_heartbeat()
    token = make_token(
        heartbeat,
        used_at=REDEEMED_AT - timedelta(minutes=5),
    )

    session = MagicMock()
    session.execute.return_value.scalar_one_or_none.return_value = token

    app.dependency_overrides[get_db_session] = override_session(session)

    try:
        client = TestClient(app)
        response = client.post(f"/checkins/{RAW_TOKEN}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Check-in unavailable" in response.text
    assert "used" not in response.text.lower()

    session.get.assert_not_called()
    session.add.assert_not_called()
    session.commit.assert_not_called()
