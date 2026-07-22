import pytest
from pydantic import ValidationError

from app.api.heartbeat_schemas import (
    HeartbeatCheckInCreate,
    HeartbeatCreate,
)
from app.domain.heartbeat import CheckInStatus


def test_valid_heartbeat_request() -> None:
    request = HeartbeatCreate(
        owner_name="Scott",
        owner_email="scott@example.com",
        interval_days=30,
        reminder_days=7,
    )

    assert request.interval_days == 30
    assert request.reminder_days == 7


def test_reminder_must_be_less_than_interval() -> None:
    with pytest.raises(
        ValidationError,
        match="reminder_days must be less than interval_days",
    ):
        HeartbeatCreate(
            owner_name="Scott",
            owner_email="scott@example.com",
            interval_days=30,
            reminder_days=30,
        )


def test_invalid_email_is_rejected() -> None:
    with pytest.raises(ValidationError):
        HeartbeatCreate(
            owner_name="Scott",
            owner_email="not-an-email-address",
            interval_days=30,
            reminder_days=7,
        )


def test_valid_heartbeat_checkin_request() -> None:
    request = HeartbeatCheckInCreate(
        status=CheckInStatus.WARNING,
        notes="I may need assistance soon",
    )

    assert request.status == CheckInStatus.WARNING
    assert request.notes == "I may need assistance soon"
    assert request.source == "manual"


def test_heartbeat_checkin_defaults() -> None:
    request = HeartbeatCheckInCreate()

    assert request.status == CheckInStatus.OK
    assert request.notes is None
    assert request.source == "manual"


def test_heartbeat_checkin_source_cannot_be_empty() -> None:
    with pytest.raises(ValidationError):
        HeartbeatCheckInCreate(source="")
