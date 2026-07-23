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
    assert request.escalation_enabled is False
    assert request.escalation_delay_days == 1
    assert request.escalation_contact_name is None
    assert request.escalation_contact_email is None


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


def test_escalation_delay_must_be_within_interval() -> None:
    with pytest.raises(
        ValidationError,
        match="escalation_delay_days must be less than or equal to interval_days",
    ):
        HeartbeatCreate(
            owner_name="Scott",
            owner_email="scott@example.com",
            interval_days=7,
            reminder_days=1,
            escalation_enabled=True,
            escalation_delay_days=8,
            escalation_contact_name="Zoe",
            escalation_contact_email="zoe@example.com",
        )


def test_escalation_contact_required_when_enabled() -> None:
    with pytest.raises(
        ValidationError,
        match="escalation_contact_name is required when escalation_enabled is true",
    ):
        HeartbeatCreate(
            owner_name="Scott",
            owner_email="scott@example.com",
            interval_days=30,
            reminder_days=7,
            escalation_enabled=True,
            escalation_delay_days=2,
            escalation_contact_email="zoe@example.com",
        )

    with pytest.raises(
        ValidationError,
        match="escalation_contact_email is required when escalation_enabled is true",
    ):
        HeartbeatCreate(
            owner_name="Scott",
            owner_email="scott@example.com",
            interval_days=30,
            reminder_days=7,
            escalation_enabled=True,
            escalation_delay_days=2,
            escalation_contact_name="Zoe",
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
