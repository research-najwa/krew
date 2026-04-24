"""add escalation tickets

Revision ID: a2f3c4d5e6f7
Revises: be134c8320b5
Create Date: 2026-03-18 10:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'a2f3c4d5e6f7'
down_revision: Union[str, None] = 'be134c8320b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('escalation_tickets',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=False),
        sa.Column('conversation_id', sa.Uuid(), nullable=True),
        sa.Column('employee_id', sa.Uuid(), nullable=False),
        sa.Column('agent_name', sa.String(length=50), nullable=False),
        sa.Column('category', sa.Enum('employee_request', 'agent_failure', 'sensitive_topic', 'policy_gap', name='escalationcategory'), nullable=False),
        sa.Column('urgency', sa.Enum('low', 'medium', 'high', name='escalationurgency'), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('status', sa.Enum('open', 'assigned', 'resolved', name='escalationstatus'), nullable=False),
        sa.Column('assigned_to', sa.String(length=255), nullable=True),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_escalation_tickets_tenant_status', 'escalation_tickets', ['tenant_id', 'status'])
    op.create_index('ix_escalation_tickets_employee', 'escalation_tickets', ['employee_id'])


def downgrade() -> None:
    op.drop_index('ix_escalation_tickets_employee', table_name='escalation_tickets')
    op.drop_index('ix_escalation_tickets_tenant_status', table_name='escalation_tickets')
    op.drop_table('escalation_tickets')
    op.execute("DROP TYPE IF EXISTS escalationcategory")
    op.execute("DROP TYPE IF EXISTS escalationurgency")
    op.execute("DROP TYPE IF EXISTS escalationstatus")
