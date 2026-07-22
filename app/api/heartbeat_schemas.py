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

    @model_validator(mode="after")
    def validate_reminder_period(self) -> "HeartbeatCreate":
        if self.reminder_days >= self.interval_days:
            raise ValueError("reminder_days must be less than interval_days")

        return self


class HeartbeatResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_name: str
    owner_email: EmailStr
    status: HeartbeatStatus
    interval_days: int
    reminder_days: int
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
