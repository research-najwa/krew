"""add_interviews_table

Revision ID: d59aa9553788
Revises: h2i3j4k5l6m7
Create Date: 2026-03-25 03:25:52.116670
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'd59aa9553788'
down_revision: Union[str, None] = 'h2i3j4k5l6m7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "DO $$ BEGIN CREATE TYPE interviewtype AS ENUM "
        "('ai_screening','human','zoom_analysis'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )
    op.execute(
        "DO $$ BEGIN CREATE TYPE interviewstatus AS ENUM "
        "('in_progress','completed','cancelled'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )

    from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM

    interviewtype = PG_ENUM('ai_screening', 'human', 'zoom_analysis', name='interviewtype', create_type=False)
    interviewstatus = PG_ENUM('in_progress', 'completed', 'cancelled', name='interviewstatus', create_type=False)

    op.create_table('interviews',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=False),
        sa.Column('candidate_id', sa.Uuid(), nullable=False),
        sa.Column('job_posting_id', sa.Uuid(), nullable=False),
        sa.Column('conversation_id', sa.Uuid(), nullable=True),
        sa.Column('interview_type', interviewtype, nullable=False),
        sa.Column('status', interviewstatus, nullable=False),
        sa.Column('questions', sa.JSON(), nullable=True),
        sa.Column('answers', sa.JSON(), nullable=True),
        sa.Column('current_question_index', sa.Integer(), nullable=False),
        sa.Column('total_questions', sa.Integer(), nullable=False),
        sa.Column('scorecard', sa.JSON(), nullable=True),
        sa.Column('overall_score', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['candidate_id'], ['candidates.id']),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id']),
        sa.ForeignKeyConstraint(['job_posting_id'], ['job_postings.id']),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_interviews_candidate_id'), 'interviews', ['candidate_id'], unique=False)
    op.create_index(op.f('ix_interviews_conversation_id'), 'interviews', ['conversation_id'], unique=False)
    op.create_index(op.f('ix_interviews_tenant_id'), 'interviews', ['tenant_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_interviews_tenant_id'), table_name='interviews')
    op.drop_index(op.f('ix_interviews_conversation_id'), table_name='interviews')
    op.drop_index(op.f('ix_interviews_candidate_id'), table_name='interviews')
    op.drop_table('interviews')
    op.execute("DROP TYPE IF EXISTS interviewstatus")
    op.execute("DROP TYPE IF EXISTS interviewtype")
