"""add attendance tables

Revision ID: g1h2i3j4k5l6
Revises: f6a7b8c9d0e2
Create Date: 2026-03-24 10:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM

# revision identifiers, used by Alembic.
revision: str = "g1h2i3j4k5l6"
down_revision: Union[str, None] = "f6a7b8c9d0e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- Attendance enum ---------------------------------------------------

    op.execute(
        "DO $$ BEGIN CREATE TYPE attendancestatus AS ENUM "
        "('present','absent','late','half_day','on_leave','holiday','weekend'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )

    attendancestatus = PG_ENUM(
        "present", "absent", "late", "half_day", "on_leave", "holiday", "weekend",
        name="attendancestatus",
        create_type=False,
    )

    # -- Attendance records table ------------------------------------------

    op.create_table(
        "attendance_records",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("employee_id", sa.Uuid(), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("check_in", sa.DateTime(timezone=True), nullable=True),
        sa.Column("check_out", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", attendancestatus, nullable=False),
        sa.Column("source", sa.String(50), server_default="manual", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("overtime_hours", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("employee_id", "date", name="uq_attendance_employee_date"),
    )

    op.create_index("ix_attendance_tenant_date", "attendance_records", ["tenant_id", "date"])
    op.create_index("ix_attendance_employee_date", "attendance_records", ["employee_id", "date"])

    # -- Work schedules table ----------------------------------------------

    op.create_table(
        "work_schedules",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("name_ar", sa.String(255), nullable=True),
        sa.Column("work_days", sa.String(50), server_default="0,1,2,3,4", nullable=False),
        sa.Column("work_start", sa.Time(), nullable=False),
        sa.Column("work_end", sa.Time(), nullable=False),
        sa.Column("late_threshold_minutes", sa.Integer(), server_default="15", nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "name", name="uq_schedule_tenant_name"),
    )


def downgrade() -> None:
    op.drop_table("work_schedules")
    op.drop_index("ix_attendance_employee_date", table_name="attendance_records")
    op.drop_index("ix_attendance_tenant_date", table_name="attendance_records")
    op.drop_table("attendance_records")

    sa.Enum(name="attendancestatus").drop(op.get_bind(), checkfirst=True)
