from datetime import timedelta


def lifecycle_duration(days: int) -> timedelta:
    if days < 0:
        raise ValueError("Lifecycle days cannot be negative")

    return timedelta(days=days)
