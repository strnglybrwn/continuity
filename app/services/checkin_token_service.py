import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.heartbeat_schemas import HeartbeatCheckInCreate
from app.core.clock import utc_now
from app.persistence.models import (
    Heartbeat,
    HeartbeatCheckIn,
    HeartbeatCheckInToken,
)
from app.services.heartbeat_service import _apply_heartbeat_checkin

DEFAULT_TOKEN_LIFETIME = timedelta(hours=24)


@dataclass(frozen=True, slots=True)
class IssuedCheckInToken:
    """A newly issued token and its persisted database record."""

    raw_token: str
    token: HeartbeatCheckInToken


def hash_checkin_token(raw_token: str) -> str:
    """Return the SHA-256 hexadecimal digest for a raw check-in token."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def issue_checkin_token(
    session: Session,
    heartbeat_id: UUID,
    *,
    lifetime: timedelta = DEFAULT_TOKEN_LIFETIME,
    now: datetime | None = None,
) -> IssuedCheckInToken | None:
    """Issue and persist a single-use check-in token for a heartbeat.

    Only the token hash is persisted. The raw token is returned once to the
    caller so it can be included in a check-in link.
    """
    if lifetime <= timedelta(0):
        raise ValueError("Token lifetime must be greater than zero")

    heartbeat = session.get(Heartbeat, heartbeat_id)

    if heartbeat is None:
        return None

    issued_at = now if now is not None else utc_now()
    raw_token = secrets.token_urlsafe(32)

    token = HeartbeatCheckInToken(
        heartbeat_id=heartbeat.id,
        token_hash=hash_checkin_token(raw_token),
        expires_at=issued_at + lifetime,
        created_at=issued_at,
    )

    session.add(token)
    session.commit()
    session.refresh(token)

    return IssuedCheckInToken(
        raw_token=raw_token,
        token=token,
    )


def redeem_checkin_token(
    session: Session,
    raw_token: str,
    *,
    now: datetime | None = None,
) -> HeartbeatCheckIn | None:
    """Redeem a valid check-in token exactly once.

    Invalid, expired, already-used, and orphaned tokens all return None.
    The token row is locked until the transaction completes so concurrent
    redemption attempts cannot both succeed.
    """
    redeemed_at = now if now is not None else utc_now()
    token_hash = hash_checkin_token(raw_token)

    statement = (
        select(HeartbeatCheckInToken)
        .where(HeartbeatCheckInToken.token_hash == token_hash)
        .with_for_update()
    )

    token = session.execute(statement).scalar_one_or_none()

    if token is None:
        return None

    if token.used_at is not None:
        return None

    if token.expires_at <= redeemed_at:
        return None

    heartbeat = session.get(Heartbeat, token.heartbeat_id)

    if heartbeat is None:
        return None

    checkin = _apply_heartbeat_checkin(
        session,
        heartbeat,
        HeartbeatCheckInCreate(source="token"),
        created_at=redeemed_at,
    )

    token.used_at = redeemed_at
    session.commit()
    session.refresh(checkin)
    session.refresh(heartbeat)

    return checkin
