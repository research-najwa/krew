"""add admin users

Revision ID: c3a4b5d6e7f8
Revises: a2f3c4d5e6f7
Create Date: 2026-03-19 10:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'c3a4b5d6e7f8'
down_revision: Union[str, None] = 'a2f3c4d5e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('admin_users',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('full_name', sa.String(length=255), nullable=False),
        sa.Column('full_name_ar', sa.String(length=255), nullable=True),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('role', sa.Enum('super_admin', 'tenant_admin', 'hr_manager', 'hr_specialist', name='adminrole'), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            "(role = 'super_admin') OR (tenant_id IS NOT NULL)",
            name="ck_admin_users_tenant_required",
        ),
    )
    op.create_index('ix_admin_users_email', 'admin_users', ['email'], unique=True)
    op.create_index('ix_admin_users_tenant_id', 'admin_users', ['tenant_id'])


def downgrade() -> None:
    op.drop_index('ix_admin_users_tenant_id', table_name='admin_users')
    op.drop_index('ix_admin_users_email', table_name='admin_users')
    op.drop_table('admin_users')
    op.execute("DROP TYPE IF EXISTS adminrole")
