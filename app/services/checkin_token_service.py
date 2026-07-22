import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from app.persistence.models import Heartbeat, HeartbeatCheckInToken


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

    issued_at = now or datetime.now(UTC)
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
