from datetime import datetime
from pathlib import Path
from typing import Protocol

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from app.domain.notification import (
    Notification,
    NotificationChannel,
    NotificationMessage,
    NotificationRecipient,
)


REMINDER_TEMPLATE_NAME = "heartbeat_reminder"
REMINDER_TEMPLATE_VERSION = 1
REMINDER_SUBJECT = "Continuity check-in reminder"

OVERDUE_WARNING_TEMPLATE_NAME = "heartbeat_overdue_warning"
OVERDUE_WARNING_TEMPLATE_VERSION = 1
OVERDUE_WARNING_SUBJECT = "Continuity check-in overdue"

ESCALATION_TEMPLATE_NAME = "escalation_notification"
ESCALATION_TEMPLATE_VERSION = 1
ESCALATION_SUBJECT = "Continuity escalation notice"

_TEMPLATE_DIRECTORY = Path(__file__).resolve().parent.parent / "templates"

_template_environment = Environment(
    loader=FileSystemLoader(_TEMPLATE_DIRECTORY),
    autoescape=select_autoescape(
        enabled_extensions=("html", "xml"),
        default_for_string=False,
    ),
    undefined=StrictUndefined,
)


class ReminderHeartbeat(Protocol):
    owner_name: str
    owner_email: str
    next_due_at: object


class EscalationHeartbeat(Protocol):
    owner_name: str
    next_due_at: object
    escalation_contact_name: str
    escalation_contact_email: str


def build_reminder_notification(
    heartbeat: ReminderHeartbeat,
    *,
    checkin_url: str,
) -> Notification:
    """Build a complete reminder notification without delivering it."""
    if not checkin_url.strip():
        raise ValueError("checkin_url must not be empty")

    next_due_date = heartbeat.next_due_at.strftime("%-d %B %Y")

    context = {
        "owner_name": heartbeat.owner_name,
        "next_due_date": next_due_date,
        "checkin_url": checkin_url,
    }

    text_body = _template_environment.get_template(f"{REMINDER_TEMPLATE_NAME}.txt").render(context)

    html_body = _template_environment.get_template(f"{REMINDER_TEMPLATE_NAME}.html").render(context)

    return Notification(
        channel=NotificationChannel.EMAIL,
        recipient=NotificationRecipient(
            name=heartbeat.owner_name,
            email=str(heartbeat.owner_email),
        ),
        message=NotificationMessage(
            template_name=REMINDER_TEMPLATE_NAME,
            template_version=REMINDER_TEMPLATE_VERSION,
            subject=REMINDER_SUBJECT,
            text_body=text_body,
            html_body=html_body,
        ),
    )


def build_overdue_warning_notification(
    heartbeat: ReminderHeartbeat,
    *,
    checkin_url: str,
    escalation_enabled: bool,
    escalation_contact_name: str | None,
    escalation_at: datetime | None,
) -> Notification:
    """Build the follow-up warning notification sent once a heartbeat is overdue."""
    if not checkin_url.strip():
        raise ValueError("checkin_url must not be empty")

    context = {
        "owner_name": heartbeat.owner_name,
        "next_due_date": heartbeat.next_due_at.strftime("%-d %B %Y"),
        "checkin_url": checkin_url,
        "escalation_enabled": escalation_enabled,
        "escalation_contact_name": escalation_contact_name,
        "escalation_deadline_date": (
            escalation_at.strftime("%-d %B %Y") if escalation_at is not None else None
        ),
    }

    text_body = _template_environment.get_template(f"{OVERDUE_WARNING_TEMPLATE_NAME}.txt").render(
        context
    )

    html_body = _template_environment.get_template(f"{OVERDUE_WARNING_TEMPLATE_NAME}.html").render(
        context
    )

    return Notification(
        channel=NotificationChannel.EMAIL,
        recipient=NotificationRecipient(
            name=heartbeat.owner_name,
            email=str(heartbeat.owner_email),
        ),
        message=NotificationMessage(
            template_name=OVERDUE_WARNING_TEMPLATE_NAME,
            template_version=OVERDUE_WARNING_TEMPLATE_VERSION,
            subject=OVERDUE_WARNING_SUBJECT,
            text_body=text_body,
            html_body=html_body,
        ),
    )


def build_escalation_notification(
    heartbeat: EscalationHeartbeat,
) -> Notification:
    """Build the informational escalation notification sent to the nominated contact."""
    context = {
        "owner_name": heartbeat.owner_name,
        "escalation_contact_name": heartbeat.escalation_contact_name,
        "overdue_since_date": heartbeat.next_due_at.strftime("%-d %B %Y"),
    }

    text_body = _template_environment.get_template(f"{ESCALATION_TEMPLATE_NAME}.txt").render(
        context
    )

    html_body = _template_environment.get_template(f"{ESCALATION_TEMPLATE_NAME}.html").render(
        context
    )

    return Notification(
        channel=NotificationChannel.EMAIL,
        recipient=NotificationRecipient(
            name=heartbeat.escalation_contact_name,
            email=str(heartbeat.escalation_contact_email),
        ),
        message=NotificationMessage(
            template_name=ESCALATION_TEMPLATE_NAME,
            template_version=ESCALATION_TEMPLATE_VERSION,
            subject=ESCALATION_SUBJECT,
            text_body=text_body,
            html_body=html_body,
        ),
    )
