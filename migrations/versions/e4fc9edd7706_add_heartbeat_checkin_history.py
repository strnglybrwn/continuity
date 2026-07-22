"""Add heartbeat check-in history.

Revision ID: e4fc9edd7706
Revises: cdbea5bc59b8
Create Date: 2026-07-22 05:13:17.283957
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "e4fc9edd7706"
down_revision: str | Sequence[str] | None = "cdbea5bc59b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


checkin_status = postgresql.ENUM(
    "ok",
    "warning",
    name="checkin_status",
    create_type=False,
)


def upgrade() -> None:
    """Create the heartbeat check-in history table."""
    checkin_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "heartbeat_checkins",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("heartbeat_id", sa.UUID(), nullable=False),
        sa.Column("status", checkin_status, nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=50), nullable=False),
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
        op.f("ix_heartbeat_checkins_heartbeat_id"),
        "heartbeat_checkins",
        ["heartbeat_id"],
        unique=False,
    )


def downgrade() -> None:
    """Remove the heartbeat check-in history table."""
    op.drop_index(
        op.f("ix_heartbeat_checkins_heartbeat_id"),
        table_name="heartbeat_checkins",
    )
    op.drop_table("heartbeat_checkins")
    checkin_status.drop(op.get_bind(), checkfirst=True)
