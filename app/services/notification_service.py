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
