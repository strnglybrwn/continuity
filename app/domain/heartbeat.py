from enum import StrEnum


class HeartbeatStatus(StrEnum):
    ACTIVE = "active"
    OVERDUE = "overdue"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class CheckInStatus(StrEnum):
    OK = "ok"
    WARNING = "warning"


class HeartbeatEventType(StrEnum):
    REMINDER_DUE = "reminder_due"
    OVERDUE = "overdue"
    CHECKED_IN = "checked_in"
    ESCALATION_DUE = "escalation_due"
