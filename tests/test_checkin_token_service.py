import hashlib
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.persistence.models import Heartbeat, HeartbeatCheckInToken
from app.services.checkin_token_service import (
    DEFAULT_TOKEN_LIFETIME,
    IssuedCheckInToken,
    hash_checkin_token,
    issue_checkin_token,
)


def make_heartbeat() -> Heartbeat:
    return Heartbeat(
        id=uuid4(),
        owner_name="Scott",
        owner_email="scott@example.com",
        interval_days=30,
        reminder_days=7,
        next_due_at=datetime(2026, 8, 21, tzinfo=UTC),
    )


def test_hash_checkin_token_returns_sha256_digest() -> None:
    raw_token = "example-checkin-token"

    result = hash_checkin_token(raw_token)

    assert result == hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    assert len(result) == 64


def test_issue_checkin_token_persists_hash_not_raw_token() -> None:
    heartbeat = make_heartbeat()
    issued_at = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)
    raw_token = "secure-raw-token"
    expected_hash = hash_checkin_token(raw_token)

    session = MagicMock()
    session.get.return_value = heartbeat

    with patch(
        "app.services.checkin_token_service.secrets.token_urlsafe",
        return_value=raw_token,
    ) as token_urlsafe:
        result = issue_checkin_token(
            session,
            heartbeat.id,
            now=issued_at,
        )

    assert isinstance(result, IssuedCheckInToken)
    assert result.raw_token == raw_token
    assert isinstance(result.token, HeartbeatCheckInToken)
    assert result.token.heartbeat_id == heartbeat.id
    assert result.token.token_hash == expected_hash
    assert result.token.token_hash != raw_token
    assert result.token.created_at == issued_at
    assert result.token.expires_at == issued_at + DEFAULT_TOKEN_LIFETIME
    assert result.token.used_at is None

    token_urlsafe.assert_called_once_with(32)
    session.add.assert_called_once_with(result.token)
    session.commit.assert_called_once()
    session.refresh.assert_called_once_with(result.token)


def test_issue_checkin_token_supports_custom_lifetime() -> None:
    heartbeat = make_heartbeat()
    issued_at = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)
    lifetime = timedelta(hours=6)

    session = MagicMock()
    session.get.return_value = heartbeat

    with patch(
        "app.services.checkin_token_service.secrets.token_urlsafe",
        return_value="raw-token",
    ):
        result = issue_checkin_token(
            session,
            heartbeat.id,
            lifetime=lifetime,
            now=issued_at,
        )

    assert result is not None
    assert result.token.expires_at == issued_at + lifetime


def test_issue_checkin_token_returns_none_when_heartbeat_not_found() -> None:
    heartbeat_id = uuid4()
    session = MagicMock()
    session.get.return_value = None

    result = issue_checkin_token(session, heartbeat_id)

    assert result is None
    session.get.assert_called_once_with(Heartbeat, heartbeat_id)
    session.add.assert_not_called()
    session.commit.assert_not_called()
    session.refresh.assert_not_called()


@pytest.mark.parametrize(
    "lifetime",
    [
        timedelta(0),
        timedelta(seconds=-1),
    ],
)
def test_issue_checkin_token_rejects_non_positive_lifetime(
    lifetime: timedelta,
) -> None:
    session = MagicMock()

    with pytest.raises(
        ValueError,
        match="Token lifetime must be greater than zero",
    ):
        issue_checkin_token(
            session,
            uuid4(),
            lifetime=lifetime,
        )

    session.get.assert_not_called()
    session.add.assert_not_called()
    session.commit.assert_not_called()


def test_issued_checkin_token_is_immutable() -> None:
    result = IssuedCheckInToken(
        raw_token="raw-token",
        token=HeartbeatCheckInToken(
            heartbeat_id=uuid4(),
            token_hash="a" * 64,
            expires_at=datetime(2026, 7, 23, tzinfo=UTC),
        ),
    )

    with pytest.raises(AttributeError):
        result.raw_token = "replacement"
