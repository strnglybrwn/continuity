from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.clock import utc_now

from app.domain.heartbeat import (
    CheckInStatus,
    HeartbeatEventType,
    HeartbeatStatus,
)
from app.persistence.base import Base


class Heartbeat(Base):
    __tablename__ = "heartbeats"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    owner_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    owner_email: Mapped[str] = mapped_column(
        String(320),
        nullable=False,
        index=True,
    )

    status: Mapped[HeartbeatStatus] = mapped_column(
        Enum(
            HeartbeatStatus,
            name="heartbeat_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=HeartbeatStatus.ACTIVE,
    )

    interval_days: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    reminder_days: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    escalation_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    escalation_delay_days: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )

    escalation_contact_name: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    escalation_contact_email: Mapped[str | None] = mapped_column(
        String(320),
        nullable=True,
        index=True,
    )

    last_checkin_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    next_due_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    checkins: Mapped[list["HeartbeatCheckIn"]] = relationship(
        back_populates="heartbeat",
        cascade="all, delete-orphan",
        order_by=lambda: HeartbeatCheckIn.created_at.desc(),
    )

    checkin_tokens: Mapped[list["HeartbeatCheckInToken"]] = relationship(
        back_populates="heartbeat",
        cascade="all, delete-orphan",
        order_by=lambda: HeartbeatCheckInToken.created_at.desc(),
    )

    events: Mapped[list["HeartbeatEvent"]] = relationship(
        back_populates="heartbeat",
        cascade="all, delete-orphan",
        order_by=lambda: HeartbeatEvent.occurred_at.desc(),
    )


class HeartbeatCheckIn(Base):
    __tablename__ = "heartbeat_checkins"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    heartbeat_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("heartbeats.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    status: Mapped[CheckInStatus] = mapped_column(
        Enum(
            CheckInStatus,
            name="checkin_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=CheckInStatus.OK,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="manual",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    heartbeat: Mapped[Heartbeat] = relationship(
        back_populates="checkins",
    )


class HeartbeatCheckInToken(Base):
    __tablename__ = "heartbeat_checkin_tokens"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    heartbeat_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("heartbeats.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    token_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    heartbeat: Mapped[Heartbeat] = relationship(
        back_populates="checkin_tokens",
    )


class HeartbeatEvent(Base):
    __tablename__ = "heartbeat_events"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    heartbeat_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("heartbeats.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    event_type: Mapped[HeartbeatEventType] = mapped_column(
        Enum(
            HeartbeatEventType,
            name="heartbeat_event_type",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        index=True,
    )

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    heartbeat: Mapped[Heartbeat] = relationship(
        back_populates="events",
    )
