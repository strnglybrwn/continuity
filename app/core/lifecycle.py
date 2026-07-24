from datetime import timedelta

from app.config import settings


def lifecycle_duration(
    days: int,
    *,
    seconds_per_day: int | None = None,
) -> timedelta:
    if days < 0:
        raise ValueError("Lifecycle days cannot be negative")

    effective_seconds_per_day = (
        settings.effective_lifecycle_day_seconds if seconds_per_day is None else seconds_per_day
    )

    if effective_seconds_per_day <= 0:
        raise ValueError("Lifecycle seconds per day must be positive")

    return timedelta(
        seconds=days * effective_seconds_per_day,
    )
