"""add audit logs

Revision ID: d4e5f6a7b8c9
Revises: c3a4b5d6e7f8
Create Date: 2026-03-19 12:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3a4b5d6e7f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('audit_logs',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=True),
        sa.Column('actor_id', sa.Uuid(), nullable=True),
        sa.Column('actor_email', sa.String(length=255), nullable=True),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('resource_type', sa.String(length=100), nullable=True),
        sa.Column('resource_id', sa.String(length=255), nullable=True),
        sa.Column('detail', JSONB(), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.String(length=512), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['actor_id'], ['admin_users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_audit_logs_action', 'audit_logs', ['action'])
    op.create_index('ix_audit_logs_created_at', 'audit_logs', ['created_at'])
    op.create_index('ix_audit_logs_tenant_created', 'audit_logs', ['tenant_id', 'created_at'])
    op.create_index('ix_audit_logs_actor_created', 'audit_logs', ['actor_id', 'created_at'])
    op.create_index('ix_audit_logs_action_created', 'audit_logs', ['action', 'created_at'])


def downgrade() -> None:
    op.drop_index('ix_audit_logs_action_created', table_name='audit_logs')
    op.drop_index('ix_audit_logs_actor_created', table_name='audit_logs')
    op.drop_index('ix_audit_logs_tenant_created', table_name='audit_logs')
    op.drop_index('ix_audit_logs_created_at', table_name='audit_logs')
    op.drop_index('ix_audit_logs_action', table_name='audit_logs')
    op.drop_table('audit_logs')
