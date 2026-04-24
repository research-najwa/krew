"""Mudad (Wage Protection System) service — stub integration.

Returns mock data when mudad_api_url is empty (stub mode).
When a real Mudad API becomes available, the stub branches will be replaced
with HTTP calls while keeping the same interface.
"""
import logging
import uuid
from datetime import datetime, timezone, date, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.employee import Employee, EmployeeStatus

logger = logging.getLogger(__name__)


class MudadService:
    """Stub for Mudad (Wage Protection System) integration."""

    def __init__(self, db: AsyncSession, tenant_id: uuid.UUID):
        self.db = db
        self.tenant_id = tenant_id
        self.settings = get_settings()

    @property
    def _is_stub(self) -> bool:
        return not self.settings.mudad_api_url

    async def _get_employee(self, employee_id: uuid.UUID) -> Employee:
        """Fetch employee with tenant isolation."""
        result = await self.db.execute(
            select(Employee).where(
                Employee.id == employee_id,
                Employee.tenant_id == self.tenant_id,
            )
        )
        emp = result.scalar_one_or_none()
        if not emp:
            raise HTTPException(status_code=404, detail="Employee not found.")
        return emp

    async def _get_active_employees(self) -> list[Employee]:
        """Fetch all active employees for this tenant."""
        result = await self.db.execute(
            select(Employee).where(
                Employee.tenant_id == self.tenant_id,
                Employee.status == EmployeeStatus.active,
            )
        )
        return list(result.scalars().all())

    def _generate_stub_iban(self, employee_id: uuid.UUID) -> str:
        """Generate a realistic-looking Saudi IBAN for stub data.

        Uses a hash to avoid leaking the employee UUID.
        """
        import hashlib
        hashed = hashlib.sha256(str(employee_id).encode()).hexdigest()[:18]
        return f"SA0010{hashed}"

    async def generate_wps_file(self, year: int, month: int) -> dict:
        """Generate WPS (Wage Protection System) file for Mudad submission."""
        logger.info("Mudad generate_wps_file: year=%d month=%d tenant=%s stub=%s",
                     year, month, self.tenant_id, self._is_stub)

        if month < 1 or month > 12:
            raise HTTPException(status_code=400, detail="Month must be between 1 and 12.")
        if year < 2000 or year > 2100:
            raise HTTPException(status_code=400, detail="Year must be between 2000 and 2100.")

        employees = await self._get_active_employees()

        # Payment date is last day of the month
        if month == 12:
            payment_date = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            payment_date = date(year, month + 1, 1) - timedelta(days=1)

        records = []
        total_amount = 0

        for emp in employees:
            salary = emp.salary_sar or 0
            total_amount += salary

            # Mask national_id to last 4 digits for PII protection
            masked_nid = ("*" * (len(emp.national_id) - 4) + emp.national_id[-4:]) if emp.national_id and len(emp.national_id) >= 4 else "****"

            records.append({
                "employee_id": str(emp.id),
                "employee_name": emp.full_name,
                "employee_number": emp.employee_number,
                "national_id": masked_nid,
                "is_saudi": emp.is_saudi,
                "bank_name": "stub_bank",
                "iban": self._generate_stub_iban(emp.id),
                "salary_sar": salary,
                "basic_salary": salary,
                "housing_allowance": 0,
                "other_allowances": 0,
                "deductions": 0,
                "net_salary": salary,
                "payment_date": payment_date.isoformat(),
            })

        return {
            "year": year,
            "month": month,
            "tenant_id": str(self.tenant_id),
            "total_employees": len(employees),
            "total_amount": total_amount,
            "currency": "SAR",
            "records": records,
            "file_status": "draft",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    async def check_compliance_status(self) -> dict:
        """Check Mudad compliance status."""
        logger.info("Mudad check_compliance_status: tenant=%s stub=%s",
                     self.tenant_id, self._is_stub)

        employees = await self._get_active_employees()
        now = datetime.now(timezone.utc)

        # Calculate next due date (last day of current month)
        if now.month == 12:
            next_due = date(now.year + 1, 1, 1) - timedelta(days=1)
        else:
            next_due = date(now.year, now.month + 1, 1) - timedelta(days=1)

        # Last submission: last day of previous month
        first_of_month = date(now.year, now.month, 1)
        last_submission = first_of_month - timedelta(days=1)

        return {
            "tenant_id": str(self.tenant_id),
            "compliant": True,
            "total_employees": len(employees),
            "last_submission": last_submission.isoformat(),
            "next_due": next_due.isoformat(),
            "months_compliant": 12,
            "protection_percentage": 100.0,
            "status_message": "Stub: All salary payments reported on time.",
        }

    async def submit_payment_report(self, year: int, month: int) -> dict:
        """Stub: Submit salary payment report to Mudad."""
        logger.info("Mudad submit_payment_report: year=%d month=%d tenant=%s stub=%s",
                     year, month, self.tenant_id, self._is_stub)

        if month < 1 or month > 12:
            raise HTTPException(status_code=400, detail="Month must be between 1 and 12.")
        if year < 2000 or year > 2100:
            raise HTTPException(status_code=400, detail="Year must be between 2000 and 2100.")

        employees = await self._get_active_employees()
        total_amount = sum(emp.salary_sar or 0 for emp in employees)

        ref_uuid = str(uuid.uuid4())[:8]
        now = datetime.now(timezone.utc)

        return {
            "status": "submitted",
            "reference_number": f"MDD-{year}{month:02d}-{ref_uuid}",
            "year": year,
            "month": month,
            "total_employees": len(employees),
            "total_amount": total_amount,
            "currency": "SAR",
            "submitted_at": now.isoformat(),
            "message": "Stub: Payment report submitted successfully.",
        }

    async def get_employee_payment_history(
        self, employee_id: uuid.UUID, months: int = 6,
    ) -> dict:
        """Get payment history for an employee from Mudad."""
        logger.info("Mudad get_employee_payment_history: employee=%s months=%d tenant=%s stub=%s",
                     employee_id, months, self.tenant_id, self._is_stub)

        emp = await self._get_employee(employee_id)
        salary = emp.salary_sar or 0

        # Generate mock payment records for the last N months
        now = datetime.now(timezone.utc)
        payments = []

        for i in range(months):
            # Walk backwards month by month
            m = now.month - i
            y = now.year
            while m < 1:
                m += 12
                y -= 1

            # Payment date is the 28th of each month (common Saudi payroll date)
            payment_date = date(y, m, 28)
            ref_uuid = str(uuid.uuid4())[:8]

            payments.append({
                "year": y,
                "month": m,
                "salary_sar": salary,
                "net_salary": salary,
                "payment_date": payment_date.isoformat(),
                "iban": self._generate_stub_iban(emp.id),
                "bank_name": "stub_bank",
                "reference_number": f"MDD-{y}{m:02d}-{ref_uuid}",
                "status": "paid",
            })

        # Mask national_id to last 4 digits for PII protection
        masked_nid = ("*" * (len(emp.national_id) - 4) + emp.national_id[-4:]) if emp.national_id and len(emp.national_id) >= 4 else "****"

        return {
            "employee_id": str(emp.id),
            "employee_name": emp.full_name,
            "employee_number": emp.employee_number,
            "national_id": masked_nid,
            "months_requested": months,
            "payments": payments,
            "currency": "SAR",
        }
