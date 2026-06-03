"""tool_trace_role_to_tool

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-03

"""
from alembic import op


revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE messages SET role = 'tool' WHERE message_type = 'tool_trace'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE messages SET role = 'assistant' WHERE message_type = 'tool_trace'"
    )
