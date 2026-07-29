"""Scope approval uniqueness to a tool invocation.

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-07-29 11:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a7b8c9d0e1f2"
down_revision: str | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TERMINAL_APPROVAL_PREDICATE = "event_type IN ('approved','denied','expired','stale')"


def upgrade() -> None:
    op.drop_index("uq_tool_approval_events_terminal", table_name="tool_approval_events")
    with op.batch_alter_table("tool_approval_events") as batch_op:
        batch_op.drop_constraint("uq_tool_approval_events_type", type_="unique")
        batch_op.create_unique_constraint(
            "uq_tool_approval_events_type",
            ["tool_call_metric_id", "approval_id", "event_type"],
        )
    op.create_index(
        "uq_tool_approval_events_terminal",
        "tool_approval_events",
        ["tool_call_metric_id", "approval_id"],
        unique=True,
        sqlite_where=sa.text(TERMINAL_APPROVAL_PREDICATE),
    )


def downgrade() -> None:
    op.drop_index("uq_tool_approval_events_terminal", table_name="tool_approval_events")
    with op.batch_alter_table("tool_approval_events") as batch_op:
        batch_op.drop_constraint("uq_tool_approval_events_type", type_="unique")
        batch_op.create_unique_constraint(
            "uq_tool_approval_events_type",
            ["approval_id", "event_type"],
        )
    op.create_index(
        "uq_tool_approval_events_terminal",
        "tool_approval_events",
        ["approval_id"],
        unique=True,
        sqlite_where=sa.text(TERMINAL_APPROVAL_PREDICATE),
    )
