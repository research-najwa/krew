"""Attendance API — check-in/out, daily reports, manual entry, and summaries."""
from datetime import date, datetime, timezone
from enum import Enum
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.admin_user import AdminUser, AdminRole
from app.models.attendance import AttendanceStatus
from app.auth.dependencies import get_current_user, require_role, require_tenant
from app.api.helpers import resolve_employee_id
from app.services.attendance import AttendanceService

router = APIRouter(prefix="/attendance", tags=["attendance"])


# -- Request / Response schemas --------------------------------------------


VALID_SOURCES = Literal["manual", "web", "mobile", "biometric", "system"]


class CheckInRequest(BaseModel):
    source: VALID_SOURCES = "manual"
    notes: str | None = None


class CheckOutRequest(BaseModel):
    notes: str | None = None


class ManualAttendanceRequest(BaseModel):
    employee_id: UUID
    target_date: date
    status: AttendanceStatus
    check_in: datetime | None = None
    check_out: datetime | None = None
    source: VALID_SOURCES = "manual"
    notes: str | None = None


class AttendanceRecordOut(BaseModel):
    id: str
    employee_id: str
    date: str
    check_in: str | None
    check_out: str | None
    status: str
    source: str
    notes: str | None
    overtime_hours: float
    created_at: str
    updated_at: str


class AttendanceSummaryOut(BaseModel):
    start_date: str
    end_date: str
    total_records: int
    present: int
    absent: int
    late: int
    avg_hours: float


# -- Helpers ---------------------------------------------------------------


def _record_to_out(rec) -> AttendanceRecordOut:
    return AttendanceRecordOut(
        id=str(rec.id),
        employee_id=str(rec.employee_id),
        date=rec.date.isoformat(),
        check_in=rec.check_in.isoformat() if rec.check_in else None,
        check_out=rec.check_out.isoformat() if rec.check_out else None,
        status=rec.status.value,
        source=rec.source,
        notes=rec.notes,
        overtime_hours=rec.overtime_hours,
        created_at=rec.created_at.isoformat(),
        updated_at=rec.updated_at.isoformat(),
    )


# -- Employee self-service endpoints ---------------------------------------


@router.post("/check-in", response_model=AttendanceRecordOut)
async def check_in(
    body: CheckInRequest,
    current_user: AdminUser = Depends(get_current_user),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Employee self check-in for today."""
    employee_id = await resolve_employee_id(current_user, tenant_id, db)
    svc = AttendanceService(db, tenant_id)
    record = await svc.record_check_in(
        employee_id=employee_id,
        source=body.source,
        notes=body.notes,
    )
    await db.commit()
    await db.refresh(record)
    return _record_to_out(record)


@router.post("/check-out", response_model=AttendanceRecordOut)
async def check_out(
    body: CheckOutRequest,
    current_user: AdminUser = Depends(get_current_user),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Employee self check-out for today."""
    employee_id = await resolve_employee_id(current_user, tenant_id, db)
    svc = AttendanceService(db, tenant_id)
    record = await svc.record_check_out(
        employee_id=employee_id,
        notes=body.notes,
    )
    await db.commit()
    await db.refresh(record)
    return _record_to_out(record)


@router.get("/my-records")
async def my_records(
    start_date: date = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: date = Query(..., description="End date (YYYY-MM-DD)"),
    current_user: AdminUser = Depends(get_current_user),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Get the current employee's own attendance records."""
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be before end_date.")

    employee_id = await resolve_employee_id(current_user, tenant_id, db)
    svc = AttendanceService(db, tenant_id)
    records = await svc.get_employee_attendance(employee_id, start_date, end_date)

    # Service returns dicts without created_at/updated_at; return raw dicts
    return records


# -- HR / Manager endpoints ------------------------------------------------


@router.get("/daily")
async def daily_attendance(
    target_date: date = Query(..., alias="date", description="Date (YYYY-MM-DD)"),
    department_id: UUID | None = Query(None),
    current_user: AdminUser = Depends(require_role(AdminRole.hr_manager)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """List daily attendance for all employees. Requires hr_manager role."""
    svc = AttendanceService(db, tenant_id)
    return await svc.get_daily_attendance(target_date, department_id)


@router.get("/summary", response_model=AttendanceSummaryOut)
async def attendance_summary(
    start_date: date = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: date = Query(..., description="End date (YYYY-MM-DD)"),
    current_user: AdminUser = Depends(require_role(AdminRole.hr_manager)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Attendance summary stats for a date range. Requires hr_manager role."""
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be before end_date.")

    svc = AttendanceService(db, tenant_id)
    return await svc.get_attendance_summary(start_date, end_date)


@router.post("/manual", response_model=AttendanceRecordOut)
async def manual_attendance(
    body: ManualAttendanceRequest,
    current_user: AdminUser = Depends(require_role(AdminRole.hr_manager)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Manual attendance entry by HR. Requires hr_manager role."""
    svc = AttendanceService(db, tenant_id)
    record = await svc.mark_attendance(
        employee_id=body.employee_id,
        target_date=body.target_date,
        status=body.status,
        check_in=body.check_in,
        check_out=body.check_out,
        source=body.source,
        notes=body.notes,
    )
    await db.commit()
    await db.refresh(record)
    return _record_to_out(record)


@router.post("/bulk-absent")
async def bulk_absent(
    target_date: date = Query(..., alias="date", description="Date to mark absent (YYYY-MM-DD)"),
    current_user: AdminUser = Depends(require_role(AdminRole.hr_manager)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Bulk mark all employees without attendance records as absent. Requires hr_manager role."""
    from datetime import date as date_type
    if target_date > date_type.today():
        raise HTTPException(status_code=400, detail="Cannot mark absent for a future date.")
    svc = AttendanceService(db, tenant_id)
    count = await svc.bulk_mark_absent(target_date)
    await db.commit()
    return {"status": "ok", "date": target_date.isoformat(), "marked_absent": count}
