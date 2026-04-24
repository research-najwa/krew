"""add activity events

Revision ID: s9_01_activity
Revises: t6_fix_datetime_tz
Create Date: 2026-04-06 10:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = 's9_01_activity'
down_revision: Union[str, None] = 't6_fix_datetime_tz'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'activity_events',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=False),
        sa.Column('actor_type', sa.String(length=20), nullable=False),
        sa.Column('actor_id', sa.String(length=64), nullable=False),
        sa.Column('subject_employee_id', sa.Uuid(), nullable=True),
        sa.Column('subject_department_id', sa.Uuid(), nullable=True),
        sa.Column('action', sa.String(length=64), nullable=False),
        sa.Column('resource_type', sa.String(length=32), nullable=False),
        sa.Column('resource_id', sa.String(length=64), nullable=True),
        sa.Column('label_en', sa.String(length=280), nullable=False),
        sa.Column('label_ar', sa.String(length=280), nullable=False),
        sa.Column('details', JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('sensitivity', sa.String(length=16), nullable=False, server_default=sa.text("'normal'")),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['subject_employee_id'], ['employees.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['subject_department_id'], ['departments.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_activity_events_tenant_id', 'activity_events', ['tenant_id'])
    op.create_index('ix_activity_events_subject_employee_id', 'activity_events', ['subject_employee_id'])
    op.create_index('ix_activity_events_subject_department_id', 'activity_events', ['subject_department_id'])
    op.create_index('ix_activity_events_created_at', 'activity_events', ['created_at'])
    op.create_index('ix_activity_tenant_created', 'activity_events', ['tenant_id', 'created_at'])
    op.create_index('ix_activity_tenant_subject', 'activity_events', ['tenant_id', 'subject_employee_id'])
    op.create_index('ix_activity_tenant_dept', 'activity_events', ['tenant_id', 'subject_department_id'])


def downgrade() -> None:
    op.drop_index('ix_activity_tenant_dept', table_name='activity_events')
    op.drop_index('ix_activity_tenant_subject', table_name='activity_events')
    op.drop_index('ix_activity_tenant_created', table_name='activity_events')
    op.drop_index('ix_activity_events_created_at', table_name='activity_events')
    op.drop_index('ix_activity_events_subject_department_id', table_name='activity_events')
    op.drop_index('ix_activity_events_subject_employee_id', table_name='activity_events')
    op.drop_index('ix_activity_events_tenant_id', table_name='activity_events')
    op.drop_table('activity_events')
