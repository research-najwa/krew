"""add deployed_agents and workforce_plans tables for Sarah

Revision ID: s1a2r3a4h5
Revises: d59aa9553788
Create Date: 2026-03-26 12:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, ENUM as PG_ENUM

revision: str = "s1a2r3a4h5"
down_revision: Union[str, None] = "d59aa9553788"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Pre-create enum types so they can be referenced in columns
_agent_status = PG_ENUM("draft", "testing", "active", "paused", "archived", name="agentstatus", create_type=False)
_plan_status = PG_ENUM("draft", "approved", "in_progress", "implemented", name="planstatus", create_type=False)


def upgrade() -> None:
    # Create enums (idempotent)
    op.execute(
        "DO $$ BEGIN CREATE TYPE agentstatus AS ENUM "
        "('draft','testing','active','paused','archived'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )
    op.execute(
        "DO $$ BEGIN CREATE TYPE planstatus AS ENUM "
        "('draft','approved','in_progress','implemented'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )

    # deployed_agents table
    op.create_table(
        "deployed_agents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("department_id", sa.Uuid(), sa.ForeignKey("departments.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("name_ar", sa.String(100), nullable=True),
        sa.Column("role_title", sa.String(255), nullable=False),
        sa.Column("role_title_ar", sa.String(255), nullable=True),
        sa.Column("personality", sa.Text(), nullable=True),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("tools_config", JSONB, nullable=True, server_default="[]"),
        sa.Column("scope_boundaries", JSONB, nullable=True, server_default="{}"),
        sa.Column("escalation_rules", JSONB, nullable=True, server_default="{}"),
        sa.Column("channel_config", JSONB, nullable=True,
                  server_default='{"web":true,"whatsapp":true,"teams":true,"slack":true,"email":false}'),
        sa.Column("status", _agent_status, nullable=False, server_default="draft"),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("employees.id"), nullable=True),
        sa.Column("performance_metrics", JSONB, nullable=True, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_deployed_agents_tenant_status", "deployed_agents", ["tenant_id", "status"])
    op.create_index("ix_deployed_agents_tenant_dept", "deployed_agents", ["tenant_id", "department_id"])

    # workforce_plans table
    op.create_table(
        "workforce_plans",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("department_id", sa.Uuid(), sa.ForeignKey("departments.id"), nullable=False),
        sa.Column("analysis", JSONB, nullable=True),
        sa.Column("current_headcount", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recommended_humans", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recommended_ai_agents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_annual_savings_sar", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("saudization_before_pct", sa.Float(), nullable=True),
        sa.Column("saudization_after_pct", sa.Float(), nullable=True),
        sa.Column("status", _plan_status, nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_workforce_plans_tenant_dept", "workforce_plans", ["tenant_id", "department_id"])


def downgrade() -> None:
    op.drop_table("workforce_plans")
    op.drop_table("deployed_agents")
    op.execute("DROP TYPE IF EXISTS planstatus")
    op.execute("DROP TYPE IF EXISTS agentstatus")
