"""add heartbeat events

Revision ID: 4f4a9a4c7874
Revises: 7a62df438921
Create Date: 2026-07-22 13:03:20.807971

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "4f4a9a4c7874"
down_revision: str | Sequence[str] | None = "7a62df438921"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


heartbeat_event_type = postgresql.ENUM(
    "reminder_due",
    "overdue",
    "checked_in",
    "escalation_due",
    name="heartbeat_event_type",
    create_type=False,
)


def upgrade() -> None:
    """Create the heartbeat event log."""
    heartbeat_event_type.create(
        op.get_bind(),
        checkfirst=True,
    )

    op.create_table(
        "heartbeat_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "heartbeat_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "event_type",
            heartbeat_event_type,
            nullable=False,
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "delivered_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["heartbeat_id"],
            ["heartbeats.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        op.f("ix_heartbeat_events_heartbeat_id"),
        "heartbeat_events",
        ["heartbeat_id"],
        unique=False,
    )

    op.create_index(
        op.f("ix_heartbeat_events_event_type"),
        "heartbeat_events",
        ["event_type"],
        unique=False,
    )


def downgrade() -> None:
    """Remove the heartbeat event log."""
    op.drop_index(
        op.f("ix_heartbeat_events_event_type"),
        table_name="heartbeat_events",
    )

    op.drop_index(
        op.f("ix_heartbeat_events_heartbeat_id"),
        table_name="heartbeat_events",
    )

    op.drop_table("heartbeat_events")

    heartbeat_event_type.drop(
        op.get_bind(),
        checkfirst=True,
    )
