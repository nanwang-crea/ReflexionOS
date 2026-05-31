"""add_agent_mode_to_sessions

Revision ID: a1b2c3d4e5f6
Revises: d3185a24f1c8
Create Date: 2026-05-31 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'd3185a24f1c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('sessions', sa.Column('agent_mode', sa.String(), nullable=False, server_default='build'))


def downgrade() -> None:
    op.drop_column('sessions', 'agent_mode')
