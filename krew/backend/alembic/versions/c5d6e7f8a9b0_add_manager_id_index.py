"""add manager_id index on employees

Revision ID: c5d6e7f8a9b0
Revises: c3d4e5f6a7b8
Create Date: 2026-03-23 18:00:00.000000
"""
from typing import Sequence, Union
from alembic import op


revision: str = 'c5d6e7f8a9b0'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_employees_manager_id "
        "ON employees (manager_id) WHERE manager_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_employees_manager_id")
