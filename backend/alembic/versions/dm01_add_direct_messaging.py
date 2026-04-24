"""Add direct messaging tables (direct_conversations, direct_messages).

- 1-on-1 DM threads with ordered participant pair invariant
- Per-participant read cursors for unread tracking
- Indexes for fast conversation lookup by either participant

Revision ID: dm01_direct_msg
Revises: s9_01_activity
Create Date: 2026-04-15 10:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'dm01_direct_msg'
down_revision: Union[str, None] = 's9_01_activity'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'direct_conversations',
        sa.Column('id', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', sa.UUID(), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('participant_a_id', sa.UUID(), sa.ForeignKey('employees.id'), nullable=False),
        sa.Column('participant_b_id', sa.UUID(), sa.ForeignKey('employees.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('last_message_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('read_cursor_a', sa.DateTime(timezone=True), nullable=True),
        sa.Column('read_cursor_b', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'participant_a_id', 'participant_b_id', name='uq_dm_conv_pair'),
        sa.CheckConstraint('participant_a_id < participant_b_id', name='ck_dm_conv_ordered_pair'),
    )
    op.create_index('ix_dm_conv_tenant_participant_a', 'direct_conversations', ['tenant_id', 'participant_a_id'])
    op.create_index('ix_dm_conv_tenant_participant_b', 'direct_conversations', ['tenant_id', 'participant_b_id'])

    op.create_table(
        'direct_messages',
        sa.Column('id', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('conversation_id', sa.UUID(),
                  sa.ForeignKey('direct_conversations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('sender_id', sa.UUID(), sa.ForeignKey('employees.id'), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('is_edited', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_dm_msg_conv_created', 'direct_messages', ['conversation_id', 'created_at'])


def downgrade() -> None:
    op.drop_index('ix_dm_msg_conv_created', 'direct_messages')
    op.drop_table('direct_messages')
    op.drop_index('ix_dm_conv_tenant_participant_b', 'direct_conversations')
    op.drop_index('ix_dm_conv_tenant_participant_a', 'direct_conversations')
    op.drop_table('direct_conversations')
