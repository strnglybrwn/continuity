"""Add heartbeat check-in tokens.

Revision ID: 7a62df438921
Revises: e4fc9edd7706
Create Date: 2026-07-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "7a62df438921"
down_revision: str | Sequence[str] | None = "e4fc9edd7706"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the heartbeat check-in token table."""
    op.create_table(
        "heartbeat_checkin_tokens",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("heartbeat_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "used_at",
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
        sa.UniqueConstraint("token_hash"),
    )

    op.create_index(
        op.f("ix_heartbeat_checkin_tokens_heartbeat_id"),
        "heartbeat_checkin_tokens",
        ["heartbeat_id"],
        unique=False,
    )

    op.create_index(
        op.f("ix_heartbeat_checkin_tokens_token_hash"),
        "heartbeat_checkin_tokens",
        ["token_hash"],
        unique=True,
    )


def downgrade() -> None:
    """Remove the heartbeat check-in token table."""
    op.drop_index(
        op.f("ix_heartbeat_checkin_tokens_token_hash"),
        table_name="heartbeat_checkin_tokens",
    )
    op.drop_index(
        op.f("ix_heartbeat_checkin_tokens_heartbeat_id"),
        table_name="heartbeat_checkin_tokens",
    )
    op.drop_table("heartbeat_checkin_tokens")
