"""add notification delivery columns

Revision ID: f6a7b8c9d0e2
Revises: c5d6e7f8a9b0
Create Date: 2026-03-23 16:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f6a7b8c9d0e2"
down_revision: Union[str, None] = "c5d6e7f8a9b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "notifications",
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "notifications",
        sa.Column("delivery_status", sa.String(20), server_default="pending", nullable=False),
    )
    op.add_column(
        "notifications",
        sa.Column("delivery_error", sa.Text(), nullable=True),
    )
    op.add_column(
        "notifications",
        sa.Column("delivery_attempts", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("notifications", "delivery_attempts")
    op.drop_column("notifications", "delivery_error")
    op.drop_column("notifications", "delivery_status")
    op.drop_column("notifications", "delivered_at")
