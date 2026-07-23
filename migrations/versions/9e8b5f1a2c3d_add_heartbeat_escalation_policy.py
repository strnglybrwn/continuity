"""add heartbeat escalation policy

Revision ID: 9e8b5f1a2c3d
Revises: 4f4a9a4c7874
Create Date: 2026-07-23 19:10:00.000000

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "9e8b5f1a2c3d"
down_revision: str | Sequence[str] | None = "4f4a9a4c7874"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add escalation policy columns to heartbeats."""
    op.add_column(
        "heartbeats",
        sa.Column(
            "escalation_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "heartbeats",
        sa.Column(
            "escalation_delay_days",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )
    op.add_column(
        "heartbeats",
        sa.Column(
            "escalation_contact_name",
            sa.String(length=200),
            nullable=True,
        ),
    )
    op.add_column(
        "heartbeats",
        sa.Column(
            "escalation_contact_email",
            sa.String(length=320),
            nullable=True,
        ),
    )

    op.create_index(
        op.f("ix_heartbeats_escalation_contact_email"),
        "heartbeats",
        ["escalation_contact_email"],
        unique=False,
    )


def downgrade() -> None:
    """Remove escalation policy columns from heartbeats."""
    op.drop_index(
        op.f("ix_heartbeats_escalation_contact_email"),
        table_name="heartbeats",
    )

    op.drop_column("heartbeats", "escalation_contact_email")
    op.drop_column("heartbeats", "escalation_contact_name")
    op.drop_column("heartbeats", "escalation_delay_days")
    op.drop_column("heartbeats", "escalation_enabled")
