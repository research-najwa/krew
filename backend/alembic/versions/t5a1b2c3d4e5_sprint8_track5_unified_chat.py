"""Sprint 8 Track 5: Unified chat with @mention routing

- Create agent_access_rules table
- Add agent_name column to messages table
- Add last_mentioned_agent column to conversations table
- Seed default access rules for existing tenants

Revision ID: t5a1b2c3d4e5
Revises: s1a2r3a4h5
Create Date: 2026-03-30 10:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "t5a1b2c3d4e5"
down_revision: Union[str, None] = "km01_knowledge"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create accesstype enum (idempotent)
    op.execute(
        "DO $$ BEGIN CREATE TYPE accesstype AS ENUM "
        "('all','role_based','department','specific_users'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )

    # 1. Create agent_access_rules table
    op.create_table(
        'agent_access_rules',
        sa.Column('id', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', sa.UUID(), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('agent_name', sa.String(100), nullable=False),
        sa.Column('access_type', sa.String(20), nullable=False, server_default='all'),
        sa.Column('allowed_roles', postgresql.JSONB(), nullable=True),
        sa.Column('allowed_departments', postgresql.JSONB(), nullable=True),
        sa.Column('allowed_users', postgresql.JSONB(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_agent_access_tenant_agent', 'agent_access_rules',
                     ['tenant_id', 'agent_name'], unique=True)
    op.create_index('ix_agent_access_rules_tenant_id', 'agent_access_rules', ['tenant_id'])

    # 2. Add agent_name to messages table
    op.add_column('messages',
        sa.Column('agent_name', sa.String(100), nullable=True)
    )
    op.create_index('ix_messages_conversation_agent',
                     'messages', ['conversation_id', 'agent_name'])

    # 3. Add last_mentioned_agent to conversations table
    op.add_column('conversations',
        sa.Column('last_mentioned_agent', sa.String(100), nullable=True)
    )

    # 4. Seed default access rules for all existing tenants
    op.execute("""
        INSERT INTO agent_access_rules (id, tenant_id, agent_name, access_type, allowed_roles)
        SELECT gen_random_uuid(), t.id, 'deema', 'all', NULL
        FROM tenants t
        WHERE NOT EXISTS (
            SELECT 1 FROM agent_access_rules r
            WHERE r.tenant_id = t.id AND r.agent_name = 'deema'
        );

        INSERT INTO agent_access_rules (id, tenant_id, agent_name, access_type, allowed_roles)
        SELECT gen_random_uuid(), t.id, 'waleed', 'all', NULL
        FROM tenants t
        WHERE NOT EXISTS (
            SELECT 1 FROM agent_access_rules r
            WHERE r.tenant_id = t.id AND r.agent_name = 'waleed'
        );

        INSERT INTO agent_access_rules (id, tenant_id, agent_name, access_type, allowed_roles)
        SELECT gen_random_uuid(), t.id, 'mohammad', 'role_based',
            '["hr_admin", "hr_manager", "hr_specialist", "hiring_manager", "department_head", "c_suite"]'::jsonb
        FROM tenants t
        WHERE NOT EXISTS (
            SELECT 1 FROM agent_access_rules r
            WHERE r.tenant_id = t.id AND r.agent_name = 'mohammad'
        );

        INSERT INTO agent_access_rules (id, tenant_id, agent_name, access_type, allowed_roles)
        SELECT gen_random_uuid(), t.id, 'ahmad', 'role_based',
            '["hr_admin", "hr_manager", "department_head", "c_suite"]'::jsonb
        FROM tenants t
        WHERE NOT EXISTS (
            SELECT 1 FROM agent_access_rules r
            WHERE r.tenant_id = t.id AND r.agent_name = 'ahmad'
        );

        INSERT INTO agent_access_rules (id, tenant_id, agent_name, access_type, allowed_roles)
        SELECT gen_random_uuid(), t.id, 'yara', 'role_based',
            '["hr_admin", "it_admin", "c_suite"]'::jsonb
        FROM tenants t
        WHERE NOT EXISTS (
            SELECT 1 FROM agent_access_rules r
            WHERE r.tenant_id = t.id AND r.agent_name = 'yara'
        );
    """)


def downgrade() -> None:
    op.drop_column('conversations', 'last_mentioned_agent')
    op.drop_index('ix_messages_conversation_agent', 'messages')
    op.drop_column('messages', 'agent_name')
    op.drop_index('ix_agent_access_tenant_agent', 'agent_access_rules')
    op.drop_index('ix_agent_access_rules_tenant_id', 'agent_access_rules')
    op.drop_table('agent_access_rules')
    op.execute("DROP TYPE IF EXISTS accesstype")
