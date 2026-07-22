from enum import StrEnum


class HeartbeatStatus(StrEnum):
    ACTIVE = "active"
    OVERDUE = "overdue"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class CheckInStatus(StrEnum):
    OK = "ok"
    WARNING = "warning"
