from collections.abc import Callable
from datetime import UTC, datetime


Clock = Callable[[], datetime]


def utc_now() -> datetime:
    """Return the current timezone-aware UTC instant."""
    return datetime.now(UTC)
