"""Drop FK constraints on direct_conversations participants to allow deployed agent UUIDs.

Revision ID: dm03_drop_participant_fk
Revises: dm02_add_dm_features
Create Date: 2026-05-17
"""
from alembic import op

revision = "dm03_drop_participant_fk"
down_revision = "dm02_add_dm_features"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("direct_conversations_participant_a_id_fkey", "direct_conversations", type_="foreignkey")
    op.drop_constraint("direct_conversations_participant_b_id_fkey", "direct_conversations", type_="foreignkey")


def downgrade() -> None:
    op.create_foreign_key("direct_conversations_participant_a_id_fkey", "direct_conversations", "employees", ["participant_a_id"], ["id"])
    op.create_foreign_key("direct_conversations_participant_b_id_fkey", "direct_conversations", "employees", ["participant_b_id"], ["id"])
