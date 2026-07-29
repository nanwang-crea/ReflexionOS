"""Add permission mode to sessions.

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-07-07 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d5e6f7a8b9c0"
down_revision: str | None = "c4d5e6f7a8b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("sessions")}
    if "permission_mode" not in columns:
        op.add_column(
            "sessions",
            sa.Column(
                "permission_mode",
                sa.String(),
                nullable=False,
                server_default="auto",
            ),
        )


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("sessions")}
    if "permission_mode" in columns:
        op.drop_column("sessions", "permission_mode")
