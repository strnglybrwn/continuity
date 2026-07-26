"""add heartbeat attachments

Revision ID: b2c1f1a7d944
Revises: 9e8b5f1a2c3d
Create Date: 2026-07-26 12:15:00.000000

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b2c1f1a7d944"
down_revision: str | Sequence[str] | None = "9e8b5f1a2c3d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create heartbeat_attachments table."""
    op.create_table(
        "heartbeat_attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("heartbeat_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("content_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["heartbeat_id"],
            ["heartbeats.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        op.f("ix_heartbeat_attachments_heartbeat_id"),
        "heartbeat_attachments",
        ["heartbeat_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop heartbeat_attachments table."""
    op.drop_index(
        op.f("ix_heartbeat_attachments_heartbeat_id"),
        table_name="heartbeat_attachments",
    )

    op.drop_table("heartbeat_attachments")
