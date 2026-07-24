from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from app.domain.notification import NotificationChannel
from app.services.notification_service import (
    ESCALATION_SUBJECT,
    ESCALATION_TEMPLATE_NAME,
    ESCALATION_TEMPLATE_VERSION,
    OVERDUE_WARNING_SUBJECT,
    OVERDUE_WARNING_TEMPLATE_NAME,
    OVERDUE_WARNING_TEMPLATE_VERSION,
    REMINDER_SUBJECT,
    REMINDER_TEMPLATE_NAME,
    REMINDER_TEMPLATE_VERSION,
    build_escalation_notification,
    build_overdue_warning_notification,
    build_reminder_notification,
)


@dataclass
class ExampleHeartbeat:
    owner_name: str
    owner_email: str
    next_due_at: datetime


@dataclass
class ExampleEscalationHeartbeat:
    owner_name: str
    next_due_at: datetime
    escalation_contact_name: str
    escalation_contact_email: str


def test_build_reminder_notification() -> None:
    heartbeat = ExampleHeartbeat(
        owner_name="Scott",
        owner_email="scott@example.com",
        next_due_at=datetime(2026, 8, 21, 9, 0, tzinfo=UTC),
    )
    checkin_url = "https://continuity.example/checkins/example-token"

    notification = build_reminder_notification(
        heartbeat,
        checkin_url=checkin_url,
    )

    assert notification.channel == NotificationChannel.EMAIL

    assert notification.recipient.name == "Scott"
    assert notification.recipient.email == "scott@example.com"

    assert notification.message.template_name == REMINDER_TEMPLATE_NAME
    assert notification.message.template_version == REMINDER_TEMPLATE_VERSION
    assert notification.message.subject == REMINDER_SUBJECT

    assert notification.message.text_body
    assert notification.message.html_body

    assert "Scott" in notification.message.text_body
    assert "Scott" in notification.message.html_body

    assert "21 August 2026" in notification.message.text_body
    assert "21 August 2026" in notification.message.html_body

    assert checkin_url in notification.message.text_body
    assert checkin_url in notification.message.html_body


def test_build_reminder_notification_rejects_empty_checkin_url() -> None:
    heartbeat = ExampleHeartbeat(
        owner_name="Scott",
        owner_email="scott@example.com",
        next_due_at=datetime(2026, 8, 21, 9, 0, tzinfo=UTC),
    )

    with pytest.raises(ValueError, match="checkin_url must not be empty"):
        build_reminder_notification(
            heartbeat,
            checkin_url=" ",
        )


def test_html_notification_escapes_user_controlled_content() -> None:
    heartbeat = ExampleHeartbeat(
        owner_name="<script>alert('test')</script>",
        owner_email="scott@example.com",
        next_due_at=datetime(2026, 8, 21, 9, 0, tzinfo=UTC),
    )

    notification = build_reminder_notification(
        heartbeat,
        checkin_url="https://continuity.example/checkins/example-token",
    )

    assert "<script>" not in notification.message.html_body
    assert "&lt;script&gt;" in notification.message.html_body


def test_build_overdue_warning_notification_with_escalation_enabled() -> None:
    heartbeat = ExampleHeartbeat(
        owner_name="Scott",
        owner_email="scott@example.com",
        next_due_at=datetime(2026, 8, 21, 9, 0, tzinfo=UTC),
    )
    checkin_url = "https://continuity.example/checkins/example-token"

    notification = build_overdue_warning_notification(
        heartbeat,
        checkin_url=checkin_url,
        escalation_enabled=True,
        escalation_contact_name="Jamie",
        escalation_at=datetime(2026, 8, 22, 9, 0, tzinfo=UTC),
    )

    assert notification.channel == NotificationChannel.EMAIL
    assert notification.recipient.name == "Scott"
    assert notification.recipient.email == "scott@example.com"

    assert notification.message.template_name == OVERDUE_WARNING_TEMPLATE_NAME
    assert notification.message.template_version == OVERDUE_WARNING_TEMPLATE_VERSION
    assert notification.message.subject == OVERDUE_WARNING_SUBJECT

    assert checkin_url in notification.message.text_body
    assert checkin_url in notification.message.html_body

    assert "Jamie" in notification.message.text_body
    assert "22 August 2026" in notification.message.text_body
    assert "Jamie" in notification.message.html_body
    assert "22 August 2026" in notification.message.html_body


def test_build_overdue_warning_notification_without_escalation() -> None:
    heartbeat = ExampleHeartbeat(
        owner_name="Scott",
        owner_email="scott@example.com",
        next_due_at=datetime(2026, 8, 21, 9, 0, tzinfo=UTC),
    )

    notification = build_overdue_warning_notification(
        heartbeat,
        checkin_url="https://continuity.example/checkins/example-token",
        escalation_enabled=False,
        escalation_contact_name=None,
        escalation_at=None,
    )

    assert "nominated escalation contact" not in notification.message.text_body
    assert "nominated escalation contact" not in notification.message.html_body


def test_build_overdue_warning_notification_rejects_empty_checkin_url() -> None:
    heartbeat = ExampleHeartbeat(
        owner_name="Scott",
        owner_email="scott@example.com",
        next_due_at=datetime(2026, 8, 21, 9, 0, tzinfo=UTC),
    )

    with pytest.raises(ValueError, match="checkin_url must not be empty"):
        build_overdue_warning_notification(
            heartbeat,
            checkin_url=" ",
            escalation_enabled=False,
            escalation_contact_name=None,
            escalation_at=None,
        )


def test_build_escalation_notification() -> None:
    heartbeat = ExampleEscalationHeartbeat(
        owner_name="Scott",
        next_due_at=datetime(2026, 8, 21, 9, 0, tzinfo=UTC),
        escalation_contact_name="Jamie",
        escalation_contact_email="jamie@example.com",
    )

    notification = build_escalation_notification(heartbeat)

    assert notification.channel == NotificationChannel.EMAIL
    assert notification.recipient.name == "Jamie"
    assert notification.recipient.email == "jamie@example.com"

    assert notification.message.template_name == ESCALATION_TEMPLATE_NAME
    assert notification.message.template_version == ESCALATION_TEMPLATE_VERSION
    assert notification.message.subject == ESCALATION_SUBJECT

    assert "Scott" in notification.message.text_body
    assert "Jamie" in notification.message.text_body
    assert "21 August 2026" in notification.message.text_body

    assert "Scott" in notification.message.html_body
    assert "Jamie" in notification.message.html_body
    assert "21 August 2026" in notification.message.html_body


def test_escalation_notification_escapes_user_controlled_content() -> None:
    heartbeat = ExampleEscalationHeartbeat(
        owner_name="<script>alert('test')</script>",
        next_due_at=datetime(2026, 8, 21, 9, 0, tzinfo=UTC),
        escalation_contact_name="Jamie",
        escalation_contact_email="jamie@example.com",
    )

    notification = build_escalation_notification(heartbeat)

    assert "<script>" not in notification.message.html_body
    assert "&lt;script&gt;" in notification.message.html_body
