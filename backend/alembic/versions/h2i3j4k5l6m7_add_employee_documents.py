"""add employee_documents table

Revision ID: h2i3j4k5l6m7
Revises: g1h2i3j4k5l6
Create Date: 2026-03-24 12:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM

# revision identifiers, used by Alembic.
revision: str = "h2i3j4k5l6m7"
down_revision: Union[str, None] = "g1h2i3j4k5l6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Define enum types
documenttype = PG_ENUM(
    'national_id', 'iqama', 'contract', 'gosi_cert', 'medical_insurance',
    'education_cert', 'passport', 'bank_letter', 'driving_license', 'other',
    name='documenttype', create_type=False,
)
verificationstatus = PG_ENUM(
    'pending', 'verified', 'rejected',
    name='verificationstatus', create_type=False,
)


def upgrade() -> None:
    # Create enum types (idempotent)
    op.execute(
        "DO $$ BEGIN CREATE TYPE documenttype AS ENUM "
        "('national_id','iqama','contract','gosi_cert','medical_insurance',"
        "'education_cert','passport','bank_letter','driving_license','other'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )
    op.execute(
        "DO $$ BEGIN CREATE TYPE verificationstatus AS ENUM "
        "('pending','verified','rejected'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )

    op.create_table(
        'employee_documents',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=False),
        sa.Column('employee_id', sa.Uuid(), nullable=False),
        sa.Column('document_type', documenttype, nullable=False),
        sa.Column('label', sa.String(length=255), nullable=True),
        sa.Column('label_ar', sa.String(length=255), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('document_id', sa.Uuid(), nullable=False),
        sa.Column('original_filename', sa.String(length=500), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=False),
        sa.Column('mime_type', sa.String(length=100), nullable=False),
        sa.Column('expires_at', sa.Date(), nullable=True),
        sa.Column('verification_status', verificationstatus, server_default='pending', nullable=False),
        sa.Column('verified_by', sa.Uuid(), nullable=True),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rejection_reason', sa.Text(), nullable=True),
        sa.Column('uploaded_by', sa.Uuid(), nullable=False),
        sa.Column('uploaded_via', sa.String(length=20), server_default='web', nullable=False),
        sa.Column('is_deleted', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id']),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id']),
        sa.ForeignKeyConstraint(['verified_by'], ['admin_users.id']),
        sa.ForeignKeyConstraint(['uploaded_by'], ['employees.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_index('ix_empdocs_tenant_employee', 'employee_documents', ['tenant_id', 'employee_id'])
    op.create_index('ix_empdocs_tenant_expires', 'employee_documents', ['tenant_id', 'expires_at'])
    op.create_index('ix_empdocs_tenant_doctype', 'employee_documents', ['tenant_id', 'document_type'])


def downgrade() -> None:
    op.drop_index('ix_empdocs_tenant_doctype', table_name='employee_documents')
    op.drop_index('ix_empdocs_tenant_expires', table_name='employee_documents')
    op.drop_index('ix_empdocs_tenant_employee', table_name='employee_documents')
    op.drop_table('employee_documents')
    op.execute("DROP TYPE IF EXISTS verificationstatus")
    op.execute("DROP TYPE IF EXISTS documenttype")
