from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.domain.heartbeat import (
    CheckInStatus,
    HeartbeatEventType,
    HeartbeatStatus,
)


class HeartbeatCreate(BaseModel):
    owner_name: str = Field(min_length=1, max_length=200)
    owner_email: EmailStr
    interval_days: int = Field(ge=1, le=365)
    reminder_days: int = Field(ge=0, le=364)
    escalation_enabled: bool = False
    escalation_delay_days: int = Field(default=1, ge=1, le=365)
    escalation_contact_name: str | None = Field(default=None, min_length=1, max_length=200)
    escalation_contact_email: EmailStr | None = None

    @model_validator(mode="after")
    def validate_reminder_period(self) -> "HeartbeatCreate":
        if self.reminder_days >= self.interval_days:
            raise ValueError("reminder_days must be less than interval_days")

        if self.escalation_delay_days > self.interval_days:
            raise ValueError("escalation_delay_days must be less than or equal to interval_days")

        if self.escalation_enabled and not self.escalation_contact_name:
            raise ValueError("escalation_contact_name is required when escalation_enabled is true")

        if self.escalation_enabled and self.escalation_contact_email is None:
            raise ValueError("escalation_contact_email is required when escalation_enabled is true")

        return self


class HeartbeatResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_name: str
    owner_email: EmailStr
    status: HeartbeatStatus
    interval_days: int
    reminder_days: int
    escalation_enabled: bool
    escalation_delay_days: int
    escalation_contact_name: str | None
    escalation_contact_email: EmailStr | None
    last_checkin_at: datetime | None
    next_due_at: datetime
    created_at: datetime
    updated_at: datetime


class HeartbeatCheckInCreate(BaseModel):
    status: CheckInStatus = CheckInStatus.OK
    notes: str | None = Field(default=None, max_length=5000)
    source: str = Field(default="manual", min_length=1, max_length=50)


class HeartbeatCheckInResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    heartbeat_id: UUID
    status: CheckInStatus
    notes: str | None
    source: str
    created_at: datetime


class HeartbeatEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    heartbeat_id: UUID
    event_type: HeartbeatEventType
    occurred_at: datetime
    delivered_at: datetime | None
    created_at: datetime

    owner_name: str
    owner_email: EmailStr


class HeartbeatEventDeliveredResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    heartbeat_id: UUID
    event_type: HeartbeatEventType
    occurred_at: datetime
    delivered_at: datetime
    created_at: datetime


class HeartbeatReminderNotificationResponse(BaseModel):
    event_id: UUID
    heartbeat_id: UUID
    owner_name: str
    owner_email: EmailStr
    subject: str
    text_body: str
    html_body: str
    checkin_url: str


class HeartbeatOverdueNotificationResponse(BaseModel):
    event_id: UUID
    heartbeat_id: UUID
    owner_name: str
    owner_email: EmailStr
    subject: str
    text_body: str
    html_body: str
    checkin_url: str


class HeartbeatEscalationNotificationResponse(BaseModel):
    event_id: UUID
    heartbeat_id: UUID
    owner_name: str
    escalation_contact_name: str
    escalation_contact_email: EmailStr
    subject: str
    text_body: str
    html_body: str


class HeartbeatEventEvaluationResponse(BaseModel):
    evaluated: int
    changed: int


class HeartbeatEventMetricsResponse(BaseModel):
    pending_total: int
    pending_reminder_due_total: int
    oldest_pending_occurred_at: datetime | None
    oldest_pending_age_seconds: int | None
    stale_pending_alert: bool
    stale_reminder_due_total: int
    stale_after_seconds: int
    pending_overdue_total: int = 0
    pending_escalation_due_total: int = 0
    stale_overdue_total: int = 0
    stale_escalation_due_total: int = 0
