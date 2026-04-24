"""sprint2 leave compliance

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-03-19 12:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── ALTER employees: add gender, probation, contract fields ──
    op.execute("CREATE TYPE gender AS ENUM ('male', 'female')")
    op.add_column('employees', sa.Column('gender', sa.Enum('male', 'female', name='gender'), nullable=True))
    op.add_column('employees', sa.Column('probation_end_date', sa.Date(), nullable=True))
    op.add_column('employees', sa.Column('probation_completed', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('employees', sa.Column('contract_type', sa.String(length=50), server_default='full_time', nullable=False))

    # ── ALTER leave_requests: add approval workflow fields ──
    op.add_column('leave_requests', sa.Column('approved_by', sa.Uuid(), nullable=True))
    op.add_column('leave_requests', sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('leave_requests', sa.Column('rejected_by', sa.Uuid(), nullable=True))
    op.add_column('leave_requests', sa.Column('rejected_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('leave_requests', sa.Column('rejection_reason', sa.Text(), nullable=True))
    op.add_column('leave_requests', sa.Column('auto_approved', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('leave_requests', sa.Column('advance_notice_days', sa.Integer(), nullable=True))
    op.add_column('leave_requests', sa.Column('labor_law_article', sa.String(length=50), nullable=True))

    op.create_foreign_key('fk_leave_requests_approved_by', 'leave_requests', 'employees', ['approved_by'], ['id'])
    op.create_foreign_key('fk_leave_requests_rejected_by', 'leave_requests', 'employees', ['rejected_by'], ['id'])

    # ── CREATE leave_policies ──
    # leavetype enum already exists from the initial schema — use raw column type
    op.create_table('leave_policies',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=False),
        sa.Column('leave_type', sa.VARCHAR(20), nullable=False),
        sa.Column('default_days_per_year', sa.Integer(), nullable=False),
        sa.Column('extended_days_per_year', sa.Integer(), nullable=True),
        sa.Column('tenure_threshold_years', sa.Integer(), nullable=True),
        sa.Column('min_days_per_request', sa.Integer(), server_default='1', nullable=False),
        sa.Column('max_days_per_request', sa.Integer(), nullable=True),
        sa.Column('advance_notice_days', sa.Integer(), server_default='0', nullable=False),
        sa.Column('requires_attachment', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('attachment_after_days', sa.Integer(), nullable=True),
        sa.Column('auto_approve', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('auto_approve_max_days', sa.Integer(), nullable=True),
        sa.Column('requires_manager_approval', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('requires_hr_approval', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('blocked_during_probation', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('blackout_periods', JSONB(), nullable=True),
        sa.Column('max_carry_over_days', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'leave_type', name='uq_leave_policies_tenant_type'),
    )


def downgrade() -> None:
    # ── DROP leave_policies ──
    op.drop_table('leave_policies')

    # ── ALTER leave_requests: remove approval workflow fields ──
    op.drop_constraint('fk_leave_requests_rejected_by', 'leave_requests', type_='foreignkey')
    op.drop_constraint('fk_leave_requests_approved_by', 'leave_requests', type_='foreignkey')
    op.drop_column('leave_requests', 'labor_law_article')
    op.drop_column('leave_requests', 'advance_notice_days')
    op.drop_column('leave_requests', 'auto_approved')
    op.drop_column('leave_requests', 'rejection_reason')
    op.drop_column('leave_requests', 'rejected_at')
    op.drop_column('leave_requests', 'rejected_by')
    op.drop_column('leave_requests', 'approved_at')
    op.drop_column('leave_requests', 'approved_by')

    # ── ALTER employees: remove new columns ──
    op.drop_column('employees', 'contract_type')
    op.drop_column('employees', 'probation_completed')
    op.drop_column('employees', 'probation_end_date')
    op.drop_column('employees', 'gender')
    op.execute("DROP TYPE IF EXISTS gender")
