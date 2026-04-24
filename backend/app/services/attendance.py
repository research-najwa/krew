"""Attendance service — check-in/out, daily reports, and summary stats."""
import logging
import uuid
from datetime import datetime, date, time, timezone

from fastapi import HTTPException
from sqlalchemy import select, func, and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance import AttendanceRecord, AttendanceStatus, WorkSchedule
from app.models.employee import Employee, EmployeeStatus

logger = logging.getLogger(__name__)


class AttendanceService:
    """Handles attendance tracking, tenant-scoped."""

    def __init__(self, db: AsyncSession, tenant_id: uuid.UUID):
        self.db = db
        self.tenant_id = tenant_id

    # -- Helper: get default work schedule for tenant ----------------------

    async def _get_default_schedule(self) -> WorkSchedule | None:
        result = await self.db.execute(
            select(WorkSchedule).where(
                WorkSchedule.tenant_id == self.tenant_id,
                WorkSchedule.is_default.is_(True),
                WorkSchedule.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def _determine_status(
        self, check_in_time: datetime, schedule: WorkSchedule | None,
    ) -> AttendanceStatus:
        """Determine if check-in is on-time or late based on work schedule."""
        if not schedule:
            return AttendanceStatus.present

        # Compare check-in time-of-day against schedule start + threshold
        ci_time = check_in_time.time()
        threshold_minutes = schedule.late_threshold_minutes or 15
        # Build the late cutoff
        start_minutes = schedule.work_start.hour * 60 + schedule.work_start.minute + threshold_minutes
        late_hour, late_minute = divmod(start_minutes, 60)
        late_cutoff = time(late_hour, late_minute)

        if ci_time > late_cutoff:
            return AttendanceStatus.late
        return AttendanceStatus.present

    def _calculate_overtime(
        self, check_in: datetime, check_out: datetime, schedule: WorkSchedule | None,
    ) -> float:
        """Calculate overtime hours beyond scheduled work_end."""
        if not schedule:
            return 0.0

        work_end_dt = datetime.combine(check_out.date(), schedule.work_end, tzinfo=timezone.utc)
        if check_out > work_end_dt:
            overtime_seconds = (check_out - work_end_dt).total_seconds()
            return round(overtime_seconds / 3600, 2)
        return 0.0

    # -- Check-in ----------------------------------------------------------

    async def record_check_in(
        self,
        employee_id: uuid.UUID,
        source: str = "manual",
        notes: str | None = None,
    ) -> AttendanceRecord:
        """Create or update today's attendance record with check-in time."""
        now = datetime.now(timezone.utc)
        today = now.date()

        # Check for existing record today
        result = await self.db.execute(
            select(AttendanceRecord).where(
                AttendanceRecord.tenant_id == self.tenant_id,
                AttendanceRecord.employee_id == employee_id,
                AttendanceRecord.date == today,
            )
        )
        record = result.scalar_one_or_none()

        if record and record.check_in:
            raise HTTPException(
                status_code=409,
                detail="Already checked in today.",
            )

        schedule = await self._get_default_schedule()
        status = await self._determine_status(now, schedule)

        if record:
            # Update existing record (e.g. pre-created absent record)
            record.check_in = now
            record.status = status
            record.source = source
            if notes:
                record.notes = notes
            record.updated_at = datetime.now(timezone.utc)
        else:
            record = AttendanceRecord(
                tenant_id=self.tenant_id,
                employee_id=employee_id,
                date=today,
                check_in=now,
                status=status,
                source=source,
                notes=notes,
            )
            self.db.add(record)

        try:
            await self.db.flush()
        except IntegrityError:
            await self.db.rollback()
            raise HTTPException(
                status_code=409,
                detail="Already checked in today (concurrent request).",
            )
        return record

    # -- Check-out ---------------------------------------------------------

    async def record_check_out(
        self,
        employee_id: uuid.UUID,
        notes: str | None = None,
    ) -> AttendanceRecord:
        """Update today's attendance record with check-out time and calculate overtime."""
        now = datetime.now(timezone.utc)
        today = now.date()

        result = await self.db.execute(
            select(AttendanceRecord).where(
                AttendanceRecord.tenant_id == self.tenant_id,
                AttendanceRecord.employee_id == employee_id,
                AttendanceRecord.date == today,
            )
        )
        record = result.scalar_one_or_none()

        if not record or not record.check_in:
            raise HTTPException(
                status_code=400,
                detail="No check-in found for today. Please check in first.",
            )

        if record.check_out:
            raise HTTPException(
                status_code=409,
                detail="Already checked out today.",
            )

        record.check_out = now
        if notes:
            record.notes = notes

        # Calculate overtime
        schedule = await self._get_default_schedule()
        record.overtime_hours = self._calculate_overtime(record.check_in, now, schedule)
        record.updated_at = datetime.now(timezone.utc)

        await self.db.flush()
        return record

    # -- Daily attendance list ---------------------------------------------

    async def get_daily_attendance(
        self,
        target_date: date,
        department_id: uuid.UUID | None = None,
    ) -> list[dict]:
        """List attendance records for a given date, tenant-scoped."""
        query = (
            select(AttendanceRecord, Employee)
            .join(Employee, AttendanceRecord.employee_id == Employee.id)
            .where(
                AttendanceRecord.tenant_id == self.tenant_id,
                AttendanceRecord.date == target_date,
            )
            .order_by(Employee.first_name)
        )

        if department_id:
            query = query.where(Employee.department_id == department_id)

        result = await self.db.execute(query)
        rows = result.all()

        return [
            {
                "id": str(rec.id),
                "employee_id": str(rec.employee_id),
                "employee_name": emp.full_name,
                "employee_number": emp.employee_number,
                "department_id": str(emp.department_id) if emp.department_id else None,
                "date": rec.date.isoformat(),
                "check_in": rec.check_in.isoformat() if rec.check_in else None,
                "check_out": rec.check_out.isoformat() if rec.check_out else None,
                "status": rec.status.value,
                "source": rec.source,
                "notes": rec.notes,
                "overtime_hours": rec.overtime_hours,
            }
            for rec, emp in rows
        ]

    # -- Employee attendance history ---------------------------------------

    async def get_employee_attendance(
        self,
        employee_id: uuid.UUID,
        start_date: date,
        end_date: date,
    ) -> list[dict]:
        """Get attendance history for a single employee within a date range."""
        result = await self.db.execute(
            select(AttendanceRecord).where(
                AttendanceRecord.tenant_id == self.tenant_id,
                AttendanceRecord.employee_id == employee_id,
                AttendanceRecord.date >= start_date,
                AttendanceRecord.date <= end_date,
            ).order_by(AttendanceRecord.date.desc())
        )
        records = result.scalars().all()

        return [
            {
                "id": str(r.id),
                "date": r.date.isoformat(),
                "check_in": r.check_in.isoformat() if r.check_in else None,
                "check_out": r.check_out.isoformat() if r.check_out else None,
                "status": r.status.value,
                "source": r.source,
                "notes": r.notes,
                "overtime_hours": r.overtime_hours,
            }
            for r in records
        ]

    # -- Attendance summary stats ------------------------------------------

    async def get_attendance_summary(
        self,
        start_date: date,
        end_date: date,
    ) -> dict:
        """Summary stats for a date range: total_days, present, absent, late, avg_hours."""
        base_where = and_(
            AttendanceRecord.tenant_id == self.tenant_id,
            AttendanceRecord.date >= start_date,
            AttendanceRecord.date <= end_date,
        )

        # Total records
        total_result = await self.db.execute(
            select(func.count(AttendanceRecord.id)).where(base_where)
        )
        total_days = total_result.scalar_one()

        # Count by status
        status_counts = {}
        for s in [AttendanceStatus.present, AttendanceStatus.absent, AttendanceStatus.late]:
            count_result = await self.db.execute(
                select(func.count(AttendanceRecord.id)).where(
                    base_where,
                    AttendanceRecord.status == s,
                )
            )
            status_counts[s.value] = count_result.scalar_one()

        # Average working hours (for records with both check_in and check_out)
        # Calculate as average of (check_out - check_in) in hours
        records_result = await self.db.execute(
            select(AttendanceRecord.check_in, AttendanceRecord.check_out).where(
                base_where,
                AttendanceRecord.check_in.isnot(None),
                AttendanceRecord.check_out.isnot(None),
            )
        )
        rows = records_result.all()
        if rows:
            total_hours = sum(
                (co - ci).total_seconds() / 3600 for ci, co in rows
            )
            avg_hours = round(total_hours / len(rows), 2)
        else:
            avg_hours = 0.0

        return {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "total_records": total_days,
            "present": status_counts.get("present", 0),
            "absent": status_counts.get("absent", 0),
            "late": status_counts.get("late", 0),
            "avg_hours": avg_hours,
        }

    # -- Bulk mark absent --------------------------------------------------

    async def bulk_mark_absent(self, target_date: date) -> int:
        """Mark all active employees without an attendance record as absent for the given date."""
        # Get all active employee IDs for this tenant
        emp_result = await self.db.execute(
            select(Employee.id).where(
                Employee.tenant_id == self.tenant_id,
                Employee.status == EmployeeStatus.active,
            )
        )
        all_employee_ids = set(emp_result.scalars().all())

        # Get employee IDs that already have a record for this date
        existing_result = await self.db.execute(
            select(AttendanceRecord.employee_id).where(
                AttendanceRecord.tenant_id == self.tenant_id,
                AttendanceRecord.date == target_date,
            )
        )
        existing_ids = set(existing_result.scalars().all())

        # Create absent records for missing employees
        missing_ids = all_employee_ids - existing_ids
        for eid in missing_ids:
            record = AttendanceRecord(
                tenant_id=self.tenant_id,
                employee_id=eid,
                date=target_date,
                status=AttendanceStatus.absent,
                source="system",
            )
            self.db.add(record)

        if missing_ids:
            await self.db.flush()

        logger.info(
            "Bulk marked %d employees as absent for %s (tenant=%s)",
            len(missing_ids), target_date, self.tenant_id,
        )
        return len(missing_ids)

    # -- Manual attendance entry -------------------------------------------

    async def mark_attendance(
        self,
        employee_id: uuid.UUID,
        target_date: date,
        status: AttendanceStatus,
        check_in: datetime | None = None,
        check_out: datetime | None = None,
        source: str = "manual",
        notes: str | None = None,
    ) -> AttendanceRecord:
        """Manual attendance entry by HR. Creates or updates a record."""
        # Verify employee belongs to this tenant
        emp_result = await self.db.execute(
            select(Employee).where(
                Employee.id == employee_id,
                Employee.tenant_id == self.tenant_id,
            )
        )
        emp = emp_result.scalar_one_or_none()
        if not emp:
            raise HTTPException(status_code=404, detail="Employee not found.")

        # Check for existing record
        result = await self.db.execute(
            select(AttendanceRecord).where(
                AttendanceRecord.tenant_id == self.tenant_id,
                AttendanceRecord.employee_id == employee_id,
                AttendanceRecord.date == target_date,
            )
        )
        record = result.scalar_one_or_none()

        overtime = 0.0
        if check_in and check_out:
            schedule = await self._get_default_schedule()
            overtime = self._calculate_overtime(check_in, check_out, schedule)

        if record:
            record.status = status
            record.check_in = check_in
            record.check_out = check_out
            record.source = source
            record.notes = notes
            record.overtime_hours = overtime
            record.updated_at = datetime.now(timezone.utc)
        else:
            record = AttendanceRecord(
                tenant_id=self.tenant_id,
                employee_id=employee_id,
                date=target_date,
                check_in=check_in,
                check_out=check_out,
                status=status,
                source=source,
                notes=notes,
                overtime_hours=overtime,
            )
            self.db.add(record)

        await self.db.flush()
        return record
