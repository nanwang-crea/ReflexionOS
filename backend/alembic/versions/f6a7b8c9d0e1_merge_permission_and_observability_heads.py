"""Merge permission-mode and observability migration heads.

Revision ID: f6a7b8c9d0e1
Revises: d5e6f7a8b9c0, e5f6a7b8c9d0
Create Date: 2026-07-28 11:30:00.000000
"""

from collections.abc import Sequence

revision: str = "f6a7b8c9d0e1"
down_revision: tuple[str, str] = ("d5e6f7a8b9c0", "e5f6a7b8c9d0")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
