"""add heartbeat schedule overrides

Revision ID: f18c2a41a9bd
Revises: b2c1f1a7d944
Create Date: 2026-07-27 14:00:00.000000

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "f18c2a41a9bd"
down_revision: str | Sequence[str] | None = "b2c1f1a7d944"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add optional schedule override timestamps for heartbeat lifecycle events."""
    op.add_column(
        "heartbeats",
        sa.Column(
            "reminder_at_override",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "heartbeats",
        sa.Column(
            "escalation_at_override",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Remove optional schedule override timestamps from heartbeats."""
    op.drop_column("heartbeats", "escalation_at_override")
    op.drop_column("heartbeats", "reminder_at_override")
