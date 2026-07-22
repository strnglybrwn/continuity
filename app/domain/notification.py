from dataclasses import dataclass
from enum import StrEnum


class NotificationChannel(StrEnum):
    EMAIL = "email"


@dataclass(frozen=True, slots=True)
class NotificationRecipient:
    name: str
    email: str


@dataclass(frozen=True, slots=True)
class NotificationMessage:
    template_name: str
    template_version: int
    subject: str
    text_body: str
    html_body: str


@dataclass(frozen=True, slots=True)
class Notification:
    channel: NotificationChannel
    recipient: NotificationRecipient
    message: NotificationMessage
