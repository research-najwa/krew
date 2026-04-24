"""sprint2 batch b — notifications, documents, hr policies

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-03-19 14:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM


revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Define enum types — create_type=False prevents auto-creation during create_table
notificationcategory = PG_ENUM('leave', 'policy', 'escalation', 'document', 'general',
                                name='notificationcategory', create_type=False)
notificationpriority = PG_ENUM('low', 'normal', 'high',
                                name='notificationpriority', create_type=False)
notificationchannel = PG_ENUM('in_app', 'email', 'whatsapp', 'slack',
                               name='notificationchannel', create_type=False)
documentcategory = PG_ENUM('leave_attachment', 'employee_document', 'policy_document',
                            name='documentcategory', create_type=False)
policycategory = PG_ENUM('leave', 'attendance', 'conduct', 'compensation', 'benefits', 'safety', 'general',
                          name='policycategory', create_type=False)
policystatus = PG_ENUM('draft', 'published', 'archived',
                        name='policystatus', create_type=False)


def upgrade() -> None:
    # ── Create enum types (idempotent) ──
    op.execute("DO $$ BEGIN CREATE TYPE notificationcategory AS ENUM ('leave','policy','escalation','document','general'); EXCEPTION WHEN duplicate_object THEN NULL; END $$")
    op.execute("DO $$ BEGIN CREATE TYPE notificationpriority AS ENUM ('low','normal','high'); EXCEPTION WHEN duplicate_object THEN NULL; END $$")
    op.execute("DO $$ BEGIN CREATE TYPE notificationchannel AS ENUM ('in_app','email','whatsapp','slack'); EXCEPTION WHEN duplicate_object THEN NULL; END $$")
    op.execute("DO $$ BEGIN CREATE TYPE documentcategory AS ENUM ('leave_attachment','employee_document','policy_document'); EXCEPTION WHEN duplicate_object THEN NULL; END $$")
    op.execute("DO $$ BEGIN CREATE TYPE policycategory AS ENUM ('leave','attendance','conduct','compensation','benefits','safety','general'); EXCEPTION WHEN duplicate_object THEN NULL; END $$")
    op.execute("DO $$ BEGIN CREATE TYPE policystatus AS ENUM ('draft','published','archived'); EXCEPTION WHEN duplicate_object THEN NULL; END $$")

    # ── CREATE notifications ──
    op.create_table('notifications',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=False),
        sa.Column('employee_id', sa.Uuid(), nullable=False),
        sa.Column('title', sa.String(length=500), nullable=False),
        sa.Column('title_ar', sa.String(length=500), nullable=True),
        sa.Column('body', sa.String(length=2000), nullable=False),
        sa.Column('body_ar', sa.String(length=2000), nullable=True),
        sa.Column('category', notificationcategory, nullable=False),
        sa.Column('priority', notificationpriority, nullable=False),
        sa.Column('channel', notificationchannel, nullable=False),
        sa.Column('is_read', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('read_at', sa.DateTime(), nullable=True),
        sa.Column('resource_type', sa.String(length=100), nullable=True),
        sa.Column('resource_id', sa.Uuid(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_notifications_tenant_employee_read', 'notifications',
                    ['tenant_id', 'employee_id', 'is_read'])
    op.create_index('ix_notifications_tenant_created', 'notifications',
                    ['tenant_id', 'created_at'])

    # ── CREATE notification_preferences ──
    op.create_table('notification_preferences',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=False),
        sa.Column('employee_id', sa.Uuid(), nullable=False),
        sa.Column('leave_notifications', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('policy_notifications', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('escalation_notifications', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('document_notifications', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'employee_id', name='uq_notification_prefs_tenant_employee'),
    )

    # ── CREATE documents ──
    op.create_table('documents',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=False),
        sa.Column('uploaded_by', sa.Uuid(), nullable=False),
        sa.Column('filename', sa.String(length=500), nullable=False),
        sa.Column('original_filename', sa.String(length=500), nullable=False),
        sa.Column('content_type', sa.String(length=100), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=False),
        sa.Column('storage_path', sa.String(length=1000), nullable=False),
        sa.Column('category', documentcategory, nullable=False),
        sa.Column('resource_type', sa.String(length=100), nullable=True),
        sa.Column('resource_id', sa.Uuid(), nullable=True),
        sa.Column('description', sa.String(length=1000), nullable=True),
        sa.Column('is_deleted', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['uploaded_by'], ['employees.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_documents_tenant_resource', 'documents',
                    ['tenant_id', 'resource_type', 'resource_id'])
    op.create_index('ix_documents_tenant_uploader', 'documents',
                    ['tenant_id', 'uploaded_by'])

    # ── CREATE hr_policies ──
    op.create_table('hr_policies',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=False),
        sa.Column('title', sa.String(length=500), nullable=False),
        sa.Column('title_ar', sa.String(length=500), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('content_ar', sa.Text(), nullable=True),
        sa.Column('category', policycategory, nullable=False),
        sa.Column('status', policystatus, server_default='draft', nullable=False),
        sa.Column('version', sa.Integer(), server_default='1', nullable=False),
        sa.Column('parent_id', sa.Uuid(), nullable=True),
        sa.Column('effective_date', sa.Date(), nullable=False),
        sa.Column('created_by', sa.Uuid(), nullable=True),
        sa.Column('published_at', sa.DateTime(), nullable=True),
        sa.Column('archived_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['parent_id'], ['hr_policies.id']),
        sa.ForeignKeyConstraint(['created_by'], ['employees.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_hr_policies_tenant_category_status', 'hr_policies',
                    ['tenant_id', 'category', 'status'])
    op.create_index('ix_hr_policies_tenant_parent', 'hr_policies',
                    ['tenant_id', 'parent_id'])

    # ── CREATE policy_acknowledgments ──
    op.create_table('policy_acknowledgments',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=False),
        sa.Column('policy_id', sa.Uuid(), nullable=False),
        sa.Column('employee_id', sa.Uuid(), nullable=False),
        sa.Column('acknowledged_at', sa.DateTime(), nullable=False),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['policy_id'], ['hr_policies.id']),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('policy_id', 'employee_id', name='uq_policy_ack_policy_employee'),
    )


def downgrade() -> None:
    op.drop_table('policy_acknowledgments')

    op.drop_index('ix_hr_policies_tenant_parent', table_name='hr_policies')
    op.drop_index('ix_hr_policies_tenant_category_status', table_name='hr_policies')
    op.drop_table('hr_policies')
    op.execute("DROP TYPE IF EXISTS policystatus")
    op.execute("DROP TYPE IF EXISTS policycategory")

    op.drop_index('ix_documents_tenant_uploader', table_name='documents')
    op.drop_index('ix_documents_tenant_resource', table_name='documents')
    op.drop_table('documents')
    op.execute("DROP TYPE IF EXISTS documentcategory")

    op.drop_table('notification_preferences')

    op.drop_index('ix_notifications_tenant_created', table_name='notifications')
    op.drop_index('ix_notifications_tenant_employee_read', table_name='notifications')
    op.drop_table('notifications')
    op.execute("DROP TYPE IF EXISTS notificationchannel")
    op.execute("DROP TYPE IF EXISTS notificationpriority")
    op.execute("DROP TYPE IF EXISTS notificationcategory")
