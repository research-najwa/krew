"""Attendance and work schedule models — time tracking for Saudi HR."""
import uuid
import enum
from datetime import datetime, date, time, timezone

from sqlalchemy import (
    String, DateTime, Date, Time, Float, Integer, Text, Boolean,
    ForeignKey, Index, UniqueConstraint, Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class AttendanceStatus(str, enum.Enum):
    present = "present"
    absent = "absent"
    late = "late"
    half_day = "half_day"
    on_leave = "on_leave"
    holiday = "holiday"
    weekend = "weekend"


class AttendanceRecord(Base):
    """Daily attendance record for an employee."""
    __tablename__ = "attendance_records"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id"))

    date: Mapped[date] = mapped_column(Date)
    check_in: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    check_out: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    status: Mapped[AttendanceStatus] = mapped_column(
        SAEnum(AttendanceStatus), default=AttendanceStatus.present
    )
    source: Mapped[str] = mapped_column(String(50), default="manual")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    overtime_hours: Mapped[float] = mapped_column(Float, default=0.0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    employee: Mapped["Employee"] = relationship()
    tenant: Mapped["Tenant"] = relationship()

    __table_args__ = (
        UniqueConstraint("employee_id", "date", name="uq_attendance_employee_date"),
        Index("ix_attendance_tenant_date", "tenant_id", "date"),
        Index("ix_attendance_employee_date", "employee_id", "date"),
    )


class WorkSchedule(Base):
    """Work schedule template (e.g. Standard, Ramadan)."""
    __tablename__ = "work_schedules"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))

    name: Mapped[str] = mapped_column(String(255))
    name_ar: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Days of week as comma-separated ints: 0=Sun, 1=Mon, ..., 6=Sat
    # Saudi standard: Sun-Thu = "0,1,2,3,4"
    work_days: Mapped[str] = mapped_column(String(50), default="0,1,2,3,4")
    work_start: Mapped[time] = mapped_column(Time, default=time(8, 0))
    work_end: Mapped[time] = mapped_column(Time, default=time(17, 0))

    late_threshold_minutes: Mapped[int] = mapped_column(Integer, default=15)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_schedule_tenant_name"),
    )
