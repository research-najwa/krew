"""Add DM feature columns: message_type, agent_name, reply_to_id, reactions,
attachments, is_deleted, edited_at, pinned_message_ids.

Supports: @mention agent inline, reply/quote, emoji reactions, file/voice
attachments, pin messages, edit/delete.

Revision ID: dm02_dm_features
Revises: dm01_direct_msg
Create Date: 2026-04-17 12:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = 'dm02_dm_features'
down_revision: Union[str, None] = 'dm01_direct_msg'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # direct_messages: new columns
    op.add_column('direct_messages',
        sa.Column('message_type', sa.String(10), server_default='human', nullable=False))
    op.add_column('direct_messages',
        sa.Column('agent_name', sa.String(100), nullable=True))
    op.add_column('direct_messages',
        sa.Column('reply_to_id', sa.UUID(),
                  sa.ForeignKey('direct_messages.id', ondelete='SET NULL'), nullable=True))
    op.add_column('direct_messages',
        sa.Column('reactions', JSONB, nullable=True))
    op.add_column('direct_messages',
        sa.Column('attachments', JSONB, nullable=True))
    op.add_column('direct_messages',
        sa.Column('is_deleted', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('direct_messages',
        sa.Column('edited_at', sa.DateTime(timezone=True), nullable=True))

    # direct_conversations: pinned messages
    op.add_column('direct_conversations',
        sa.Column('pinned_message_ids', JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column('direct_conversations', 'pinned_message_ids')
    op.drop_column('direct_messages', 'edited_at')
    op.drop_column('direct_messages', 'is_deleted')
    op.drop_column('direct_messages', 'attachments')
    op.drop_column('direct_messages', 'reactions')
    op.drop_column('direct_messages', 'reply_to_id')
    op.drop_column('direct_messages', 'agent_name')
    op.drop_column('direct_messages', 'message_type')
