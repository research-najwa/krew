"""add payslips table

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-03-23 16:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'payslips',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=False),
        sa.Column('employee_id', sa.Uuid(), nullable=False),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('month', sa.Integer(), nullable=False),
        sa.Column('basic_salary', sa.Integer(), nullable=False),
        sa.Column('housing_allowance', sa.Integer(), server_default='0', nullable=False),
        sa.Column('transport_allowance', sa.Integer(), server_default='0', nullable=False),
        sa.Column('other_allowances', sa.Integer(), server_default='0', nullable=False),
        sa.Column('gosi_employee', sa.Integer(), server_default='0', nullable=False),
        sa.Column('absent_deduction', sa.Integer(), server_default='0', nullable=False),
        sa.Column('other_deductions', sa.Integer(), server_default='0', nullable=False),
        sa.Column('gross_salary', sa.Integer(), nullable=False),
        sa.Column('total_deductions', sa.Integer(), nullable=False),
        sa.Column('net_salary', sa.Integer(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('employee_id', 'year', 'month', name='uq_payslip_employee_year_month'),
    )


def downgrade() -> None:
    op.drop_table('payslips')
