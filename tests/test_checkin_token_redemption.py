from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from uuid import uuid4

from app.domain.heartbeat import CheckInStatus, HeartbeatStatus
from app.persistence.models import (
    Heartbeat,
    HeartbeatCheckIn,
    HeartbeatCheckInToken,
)
from app.services.checkin_token_service import (
    hash_checkin_token,
    redeem_checkin_token,
)


RAW_TOKEN = "valid-raw-checkin-token"
REDEEMED_AT = datetime(2026, 7, 22, 14, 0, tzinfo=UTC)


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
        expires_at=expires_at or REDEEMED_AT + timedelta(hours=1),
        used_at=used_at,
        created_at=REDEEMED_AT - timedelta(hours=1),
    )


def configure_token_result(
    session: MagicMock,
    token: HeartbeatCheckInToken | None,
) -> None:
    session.execute.return_value.scalar_one_or_none.return_value = token


def test_redeem_checkin_token_updates_everything_in_one_transaction() -> None:
    heartbeat = make_heartbeat()
    token = make_token(heartbeat)

    session = MagicMock()
    configure_token_result(session, token)
    session.get.return_value = heartbeat

    result = redeem_checkin_token(
        session,
        RAW_TOKEN,
        now=REDEEMED_AT,
    )

    assert isinstance(result, HeartbeatCheckIn)
    assert result.heartbeat_id == heartbeat.id
    assert result.status == CheckInStatus.OK
    assert result.notes is None
    assert result.source == "token"
    assert result.created_at == REDEEMED_AT

    assert heartbeat.status == HeartbeatStatus.ACTIVE
    assert heartbeat.last_checkin_at == REDEEMED_AT
    assert heartbeat.next_due_at == REDEEMED_AT + timedelta(days=30)
    assert token.used_at == REDEEMED_AT

    session.add.assert_called_once_with(result)
    session.commit.assert_called_once()
    assert session.refresh.call_count == 2
    session.refresh.assert_any_call(result)
    session.refresh.assert_any_call(heartbeat)


def test_redeem_checkin_token_rejects_unknown_token() -> None:
    session = MagicMock()
    configure_token_result(session, None)

    result = redeem_checkin_token(
        session,
        "unknown-token",
        now=REDEEMED_AT,
    )

    assert result is None
    session.get.assert_not_called()
    session.add.assert_not_called()
    session.commit.assert_not_called()


def test_redeem_checkin_token_rejects_expired_token() -> None:
    heartbeat = make_heartbeat()
    token = make_token(
        heartbeat,
        expires_at=REDEEMED_AT - timedelta(seconds=1),
    )

    session = MagicMock()
    configure_token_result(session, token)

    result = redeem_checkin_token(
        session,
        RAW_TOKEN,
        now=REDEEMED_AT,
    )

    assert result is None
    session.get.assert_not_called()
    session.add.assert_not_called()
    session.commit.assert_not_called()


def test_redeem_checkin_token_expires_exactly_at_expiry_time() -> None:
    heartbeat = make_heartbeat()
    token = make_token(
        heartbeat,
        expires_at=REDEEMED_AT,
    )

    session = MagicMock()
    configure_token_result(session, token)

    result = redeem_checkin_token(
        session,
        RAW_TOKEN,
        now=REDEEMED_AT,
    )

    assert result is None
    session.get.assert_not_called()
    session.add.assert_not_called()
    session.commit.assert_not_called()


def test_redeem_checkin_token_rejects_used_token() -> None:
    heartbeat = make_heartbeat()
    original_used_at = REDEEMED_AT - timedelta(minutes=10)
    token = make_token(
        heartbeat,
        used_at=original_used_at,
    )

    session = MagicMock()
    configure_token_result(session, token)

    result = redeem_checkin_token(
        session,
        RAW_TOKEN,
        now=REDEEMED_AT,
    )

    assert result is None
    assert token.used_at == original_used_at
    session.get.assert_not_called()
    session.add.assert_not_called()
    session.commit.assert_not_called()


def test_redeem_checkin_token_rejects_orphaned_token() -> None:
    heartbeat = make_heartbeat()
    token = make_token(heartbeat)

    session = MagicMock()
    configure_token_result(session, token)
    session.get.return_value = None

    result = redeem_checkin_token(
        session,
        RAW_TOKEN,
        now=REDEEMED_AT,
    )

    assert result is None
    assert token.used_at is None
    session.add.assert_not_called()
    session.commit.assert_not_called()
