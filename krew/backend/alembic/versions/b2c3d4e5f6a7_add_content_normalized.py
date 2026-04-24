"""add content_normalized to policy_chunks

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-23 14:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('policy_chunks', sa.Column('content_normalized', sa.Text(), nullable=True))

    op.execute(
        "UPDATE policy_chunks SET content_normalized = regexp_replace(content, "
        "'[\u064B-\u065F\u0610-\u061A\u0670]', '', 'g')"
    )

    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.execute(
        "CREATE INDEX ix_policy_chunks_content_normalized_trgm "
        "ON policy_chunks USING gin (content_normalized gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_policy_chunks_content_normalized_trgm")
    op.drop_column('policy_chunks', 'content_normalized')
