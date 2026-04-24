"""sprint2 batch c — reporting indexes, nitaqat, onboarding, notification category

Revision ID: a1b2c3d4e5f6
Revises: f6a7b8c9d0e1
Create Date: 2026-03-23 10:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Define enum types — create_type=False prevents auto-creation during create_table
companysizecategory = PG_ENUM('micro', 'small', 'medium', 'large', 'giant',
                               name='companysizecategory', create_type=False)
onboardingsteptype = PG_ENUM('manual', 'automatic', 'agent_assisted',
                              name='onboardingsteptype', create_type=False)
onboardingassignmentstatus = PG_ENUM('in_progress', 'completed', 'cancelled',
                                     name='onboardingassignmentstatus', create_type=False)
onboardingstepstatus = PG_ENUM('pending', 'in_progress', 'completed', 'skipped',
                                name='onboardingstepstatus', create_type=False)


def upgrade() -> None:
    # ── Create enum types (idempotent) ──
    op.execute("DO $$ BEGIN CREATE TYPE companysizecategory AS ENUM ('micro','small','medium','large','giant'); EXCEPTION WHEN duplicate_object THEN NULL; END $$")
    op.execute("DO $$ BEGIN CREATE TYPE onboardingsteptype AS ENUM ('manual','automatic','agent_assisted'); EXCEPTION WHEN duplicate_object THEN NULL; END $$")
    op.execute("DO $$ BEGIN CREATE TYPE onboardingassignmentstatus AS ENUM ('in_progress','completed','cancelled'); EXCEPTION WHEN duplicate_object THEN NULL; END $$")
    op.execute("DO $$ BEGIN CREATE TYPE onboardingstepstatus AS ENUM ('pending','in_progress','completed','skipped'); EXCEPTION WHEN duplicate_object THEN NULL; END $$")

    # ── Add 'onboarding' to notificationcategory enum ──
    op.execute("ALTER TYPE notificationcategory ADD VALUE IF NOT EXISTS 'onboarding'")

    # ── CREATE nitaqat_configs ──
    op.create_table('nitaqat_configs',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=False),
        sa.Column('industry', sa.String(length=255), server_default='general', nullable=False),
        sa.Column('industry_ar', sa.String(length=255), nullable=True),
        sa.Column('size_category', companysizecategory, server_default='small', nullable=False),
        sa.Column('platinum_threshold', sa.Float(), server_default='40.0', nullable=False),
        sa.Column('green_high_threshold', sa.Float(), server_default='26.0', nullable=False),
        sa.Column('green_low_threshold', sa.Float(), server_default='17.0', nullable=False),
        sa.Column('yellow_threshold', sa.Float(), server_default='6.0', nullable=False),
        sa.Column('target_saudization_pct', sa.Float(), server_default='26.0', nullable=False),
        sa.Column('alert_when_below_target', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('alert_buffer_pct', sa.Float(), server_default='2.0', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', name='uq_nitaqat_config_tenant'),
    )

    # ── CREATE onboarding_templates ──
    op.create_table('onboarding_templates',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('name_ar', sa.String(length=255), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('is_default', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'name', name='uq_onboarding_template_tenant_name'),
    )

    # ── CREATE onboarding_template_steps ──
    op.create_table('onboarding_template_steps',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('template_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=500), nullable=False),
        sa.Column('name_ar', sa.String(length=500), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('description_ar', sa.Text(), nullable=True),
        sa.Column('step_type', onboardingsteptype, nullable=False),
        sa.Column('order', sa.Integer(), nullable=False),
        sa.Column('due_days_after_hire', sa.Integer(), server_default='7', nullable=False),
        sa.Column('is_required', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('auto_trigger', sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(['template_id'], ['onboarding_templates.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── CREATE onboarding_assignments ──
    op.create_table('onboarding_assignments',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=False),
        sa.Column('employee_id', sa.Uuid(), nullable=False),
        sa.Column('template_id', sa.Uuid(), nullable=False),
        sa.Column('status', onboardingassignmentstatus, server_default='in_progress', nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id']),
        sa.ForeignKeyConstraint(['template_id'], ['onboarding_templates.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('employee_id', 'template_id', name='uq_onboarding_assignment_emp_template'),
    )
    op.create_index('ix_onboarding_assignment_tenant_status', 'onboarding_assignments',
                    ['tenant_id', 'status'])

    # ── CREATE onboarding_step_assignments ──
    op.create_table('onboarding_step_assignments',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('assignment_id', sa.Uuid(), nullable=False),
        sa.Column('template_step_id', sa.Uuid(), nullable=False),
        sa.Column('status', onboardingstepstatus, nullable=False),
        sa.Column('order', sa.Integer(), nullable=False),
        sa.Column('due_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_by', sa.String(length=255), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['assignment_id'], ['onboarding_assignments.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['template_step_id'], ['onboarding_template_steps.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('assignment_id', 'template_step_id', name='uq_onboarding_step_assignment_unique'),
    )

    # ── Add onboarding_notifications column to notification_preferences ──
    op.add_column('notification_preferences',
        sa.Column('onboarding_notifications', sa.Boolean(), server_default=sa.text('true'), nullable=False)
    )

    # ── Performance indexes on existing tables (for reporting) ──
    op.execute("CREATE INDEX IF NOT EXISTS ix_leave_requests_employee_status ON leave_requests (employee_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_escalation_tickets_tenant_status ON escalation_tickets (tenant_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_conversations_tenant_agent_started ON conversations (tenant_id, agent_name, started_at)")


def downgrade() -> None:
    # Drop performance indexes
    op.drop_index('ix_conversations_tenant_agent_started', table_name='conversations')
    op.drop_index('ix_escalation_tickets_tenant_status', table_name='escalation_tickets')
    op.drop_index('ix_leave_requests_employee_status', table_name='leave_requests')

    # Drop onboarding_notifications column
    op.drop_column('notification_preferences', 'onboarding_notifications')

    # Drop tables in reverse dependency order
    op.drop_table('onboarding_step_assignments')

    op.drop_index('ix_onboarding_assignment_tenant_status', table_name='onboarding_assignments')
    op.drop_table('onboarding_assignments')

    op.drop_table('onboarding_template_steps')
    op.drop_table('onboarding_templates')
    op.drop_table('nitaqat_configs')

    # Drop enum types
    op.execute("DROP TYPE IF EXISTS onboardingstepstatus")
    op.execute("DROP TYPE IF EXISTS onboardingassignmentstatus")
    op.execute("DROP TYPE IF EXISTS onboardingsteptype")
    op.execute("DROP TYPE IF EXISTS companysizecategory")
    # Note: Cannot remove 'onboarding' from notificationcategory enum in Postgres easily
