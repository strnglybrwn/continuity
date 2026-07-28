"""add heartbeat event dedupe constraint

Revision ID: a1d3f8c9b4e2
Revises: f18c2a41a9bd
Create Date: 2026-07-28 12:00:00.000000

"""

from collections.abc import Sequence

from alembic import op


revision: str = "a1d3f8c9b4e2"
down_revision: str | Sequence[str] | None = "f18c2a41a9bd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add DB-level dedupe for lifecycle events."""
    op.create_unique_constraint(
        "uq_heartbeat_events_heartbeat_event_occurred",
        "heartbeat_events",
        ["heartbeat_id", "event_type", "occurred_at"],
    )


def downgrade() -> None:
    """Remove DB-level dedupe for lifecycle events."""
    op.drop_constraint(
        "uq_heartbeat_events_heartbeat_event_occurred",
        "heartbeat_events",
        type_="unique",
    )
