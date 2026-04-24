"""Fix conversations/messages datetime columns to use timezone-aware timestamps.

Revision ID: t6_fix_datetime_tz
Revises: t5a1b2c3d4e5
Create Date: 2026-04-04 23:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "t6_fix_datetime_tz"
down_revision: Union[str, None] = "t5a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Convert conversations timestamps to timezone-aware
    op.alter_column('conversations', 'started_at',
                    type_=sa.DateTime(timezone=True),
                    postgresql_using='started_at AT TIME ZONE \'UTC\'')
    op.alter_column('conversations', 'resolved_at',
                    type_=sa.DateTime(timezone=True),
                    postgresql_using='resolved_at AT TIME ZONE \'UTC\'')

    # Convert messages timestamp to timezone-aware
    op.alter_column('messages', 'created_at',
                    type_=sa.DateTime(timezone=True),
                    postgresql_using='created_at AT TIME ZONE \'UTC\'')


def downgrade() -> None:
    op.alter_column('messages', 'created_at',
                    type_=sa.DateTime(timezone=False))
    op.alter_column('conversations', 'resolved_at',
                    type_=sa.DateTime(timezone=False))
    op.alter_column('conversations', 'started_at',
                    type_=sa.DateTime(timezone=False))
