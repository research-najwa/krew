"""add knowledge_sources, knowledge_chunks, agent_knowledge_assignments tables

Revision ID: km01_knowledge
Revises: s1a2r3a4h5
Create Date: 2026-03-30 10:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, ENUM as PG_ENUM

revision: str = "km01_knowledge"
down_revision: Union[str, None] = "s1a2r3a4h5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_source_type = PG_ENUM(
    "policy", "document", "markdown", "custom_text", "url",
    name="sourcetype", create_type=False,
)
_embedding_status = PG_ENUM(
    "pending", "processing", "complete", "failed",
    name="embeddingstatus", create_type=False,
)


def upgrade() -> None:
    # Create enum types (idempotent)
    op.execute(
        "DO $$ BEGIN CREATE TYPE sourcetype AS ENUM "
        "('policy','document','markdown','custom_text','url'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )
    op.execute(
        "DO $$ BEGIN CREATE TYPE embeddingstatus AS ENUM "
        "('pending','processing','complete','failed'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )

    # knowledge_sources
    op.create_table(
        "knowledge_sources",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.UUID(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("title_ar", sa.String(500), nullable=True),
        sa.Column("source_type", _source_type, nullable=False),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("content_text", sa.Text(), nullable=True),
        sa.Column("file_path", sa.String(1000), nullable=True),
        sa.Column("url", sa.String(2000), nullable=True),
        sa.Column("source_policy_id", sa.UUID(), sa.ForeignKey("hr_policies.id"), nullable=True),
        sa.Column("chunk_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("embedding_status", _embedding_status, server_default="pending", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("metadata_json", JSONB, nullable=True),
        sa.Column("created_by", sa.UUID(), sa.ForeignKey("employees.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_knowledge_sources_tenant_type", "knowledge_sources", ["tenant_id", "source_type"])
    op.create_index("ix_knowledge_sources_tenant_active", "knowledge_sources", ["tenant_id", "is_active"])

    # knowledge_chunks (with pgvector embedding column)
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("source_id", sa.UUID(), sa.ForeignKey("knowledge_sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    # Add the vector column via raw SQL (pgvector extension)
    op.execute("ALTER TABLE knowledge_chunks ADD COLUMN embedding vector(1536)")
    op.create_index("ix_knowledge_chunks_source", "knowledge_chunks", ["source_id"])
    op.create_index("ix_knowledge_chunks_tenant", "knowledge_chunks", ["tenant_id"])

    # agent_knowledge_assignments
    op.create_table(
        "agent_knowledge_assignments",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("agent_id", sa.UUID(), sa.ForeignKey("deployed_agents.id"), nullable=False),
        sa.Column("source_id", sa.UUID(), sa.ForeignKey("knowledge_sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("assigned_by", sa.UUID(), sa.ForeignKey("employees.id"), nullable=True),
    )
    op.create_unique_constraint(
        "uq_agent_knowledge_agent_source", "agent_knowledge_assignments",
        ["agent_id", "source_id"],
    )
    op.create_index(
        "ix_agent_knowledge_tenant_agent", "agent_knowledge_assignments",
        ["tenant_id", "agent_id"],
    )


def downgrade() -> None:
    op.drop_table("agent_knowledge_assignments")
    op.drop_table("knowledge_chunks")
    op.drop_table("knowledge_sources")
    op.execute("DROP TYPE IF EXISTS embeddingstatus")
    op.execute("DROP TYPE IF EXISTS sourcetype")
