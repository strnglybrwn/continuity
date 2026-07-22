from datetime import timedelta

from app.core.lifecycle import lifecycle_duration


def test_lifecycle_duration_uses_real_days_by_default() -> None:
    assert lifecycle_duration(30) == timedelta(days=30)


def test_lifecycle_duration_rejects_negative_days() -> None:
    try:
        lifecycle_duration(-1)
    except ValueError as exc:
        assert str(exc) == "Lifecycle days cannot be negative"
    else:
        raise AssertionError("Expected lifecycle_duration() to raise ValueError")
