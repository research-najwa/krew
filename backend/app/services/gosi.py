"""GOSI (General Organization for Social Insurance) service — stub integration.

Returns mock data when gosi_api_url is empty (stub mode).
When a real GOSI API becomes available, the stub branches will be replaced
with HTTP calls while keeping the same interface.
"""
import logging
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.employee import Employee, EmployeeStatus

logger = logging.getLogger(__name__)

# GOSI contribution rates
SAUDI_EMPLOYER_RATE = 0.0975  # 9.75%
SAUDI_EMPLOYEE_RATE = 0.0975  # 9.75%
NON_SAUDI_EMPLOYER_RATE = 0.02  # 2% (occupational hazards only)
NON_SAUDI_EMPLOYEE_RATE = 0.0  # 0%


class GOSIService:
    """Stub for GOSI API integration. Returns mock data for development."""

    def __init__(self, db: AsyncSession, tenant_id: uuid.UUID):
        self.db = db
        self.tenant_id = tenant_id
        self.settings = get_settings()

    @property
    def _is_stub(self) -> bool:
        return not self.settings.gosi_api_url

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

    def _compute_contributions(self, salary_sar: int, is_saudi: bool, housing_allowance: int = 0) -> dict:
        """Calculate GOSI contributions based on nationality and salary.

        GOSI contribution base includes basic salary + housing allowance.
        """
        salary_sar = salary_sar + housing_allowance
        if is_saudi:
            employer_share = round(salary_sar * SAUDI_EMPLOYER_RATE, 2)
            employee_share = round(salary_sar * SAUDI_EMPLOYEE_RATE, 2)
        else:
            employer_share = round(salary_sar * NON_SAUDI_EMPLOYER_RATE, 2)
            employee_share = 0.0
        return {
            "employer_share": employer_share,
            "employee_share": employee_share,
            "total": round(employer_share + employee_share, 2),
        }

    async def calculate_contributions(self, employee_id: uuid.UUID) -> dict:
        """Calculate GOSI contributions for an employee."""
        logger.info("GOSI calculate_contributions: employee=%s tenant=%s stub=%s",
                     employee_id, self.tenant_id, self._is_stub)

        emp = await self._get_employee(employee_id)
        salary = emp.salary_sar or 0
        contributions = self._compute_contributions(salary, emp.is_saudi)

        return {
            "employee_id": str(emp.id),
            "employee_name": emp.full_name,
            "employee_number": emp.employee_number,
            "salary_sar": salary,
            "is_saudi": emp.is_saudi,
            "employer_rate": SAUDI_EMPLOYER_RATE if emp.is_saudi else NON_SAUDI_EMPLOYER_RATE,
            "employee_rate": SAUDI_EMPLOYEE_RATE if emp.is_saudi else NON_SAUDI_EMPLOYEE_RATE,
            **contributions,
            "currency": "SAR",
        }

    async def get_tenant_summary(self) -> dict:
        """GOSI summary for all employees in tenant."""
        logger.info("GOSI get_tenant_summary: tenant=%s stub=%s",
                     self.tenant_id, self._is_stub)

        employees = await self._get_active_employees()

        total_saudi = 0
        total_non_saudi = 0
        total_employer_contribution = 0.0
        total_employee_contribution = 0.0
        registered_count = 0

        for emp in employees:
            salary = emp.salary_sar or 0
            contributions = self._compute_contributions(salary, emp.is_saudi)

            if emp.is_saudi:
                total_saudi += 1
            else:
                total_non_saudi += 1

            total_employer_contribution += contributions["employer_share"]
            total_employee_contribution += contributions["employee_share"]

            if emp.gosi_registered:
                registered_count += 1

        total_employees = len(employees)

        return {
            "tenant_id": str(self.tenant_id),
            "total_employees": total_employees,
            "total_saudi_employees": total_saudi,
            "total_non_saudi_employees": total_non_saudi,
            "total_employer_contribution": round(total_employer_contribution, 2),
            "total_employee_contribution": round(total_employee_contribution, 2),
            "total_monthly_contribution": round(total_employer_contribution + total_employee_contribution, 2),
            "registered_count": registered_count,
            "unregistered_count": total_employees - registered_count,
            "registration_status": "compliant" if registered_count == total_employees else "non_compliant",
            "currency": "SAR",
        }

    async def check_registration_status(self, employee_id: uuid.UUID) -> dict:
        """Check if employee is registered with GOSI."""
        logger.info("GOSI check_registration_status: employee=%s tenant=%s stub=%s",
                     employee_id, self.tenant_id, self._is_stub)

        emp = await self._get_employee(employee_id)
        tenant_prefix = str(self.tenant_id)[:8]
        emp_number = emp.employee_number or str(emp.id)[:8]

        return {
            "employee_id": str(emp.id),
            "employee_name": emp.full_name,
            "registered": emp.gosi_registered,
            "registration_date": emp.hire_date.isoformat() if emp.gosi_registered else None,
            "subscription_number": f"GOSI-{tenant_prefix}-{emp_number}" if emp.gosi_registered else None,
            "is_saudi": emp.is_saudi,
        }

    async def register_employee(self, employee_id: uuid.UUID) -> dict:
        """Stub: Register employee with GOSI. Sets gosi_registered=True."""
        logger.info("GOSI register_employee: employee=%s tenant=%s stub=%s",
                     employee_id, self.tenant_id, self._is_stub)

        emp = await self._get_employee(employee_id)

        if emp.gosi_registered:
            raise HTTPException(
                status_code=409,
                detail="Employee is already registered with GOSI.",
            )

        emp.gosi_registered = True
        await self.db.flush()

        tenant_prefix = str(self.tenant_id)[:8]
        emp_number = emp.employee_number or str(emp.id)[:8]
        subscription_number = f"GOSI-{tenant_prefix}-{emp_number}"

        logger.info("GOSI employee registered: employee=%s subscription=%s",
                     employee_id, subscription_number)

        return {
            "status": "registered",
            "employee_id": str(emp.id),
            "employee_name": emp.full_name,
            "subscription_number": subscription_number,
            "registration_date": datetime.now(timezone.utc).date().isoformat(),
            "message": "Stub: Employee registered with GOSI successfully.",
        }

    async def generate_monthly_report(self, year: int, month: int) -> dict:
        """Generate monthly GOSI contribution report."""
        logger.info("GOSI generate_monthly_report: year=%d month=%d tenant=%s stub=%s",
                     year, month, self.tenant_id, self._is_stub)

        if month < 1 or month > 12:
            raise HTTPException(status_code=400, detail="Month must be between 1 and 12.")
        if year < 2000 or year > 2100:
            raise HTTPException(status_code=400, detail="Year must be between 2000 and 2100.")

        employees = await self._get_active_employees()

        employee_records = []
        total_employer = 0.0
        total_employee = 0.0

        for emp in employees:
            salary = emp.salary_sar or 0
            contributions = self._compute_contributions(salary, emp.is_saudi)
            tenant_prefix = str(self.tenant_id)[:8]
            emp_number = emp.employee_number or str(emp.id)[:8]

            # Mask national_id to last 4 digits for PII protection
            masked_nid = ("*" * (len(emp.national_id) - 4) + emp.national_id[-4:]) if emp.national_id and len(emp.national_id) >= 4 else "****"

            employee_records.append({
                "employee_id": str(emp.id),
                "employee_name": emp.full_name,
                "employee_number": emp.employee_number,
                "national_id": masked_nid,
                "is_saudi": emp.is_saudi,
                "salary_sar": salary,
                "employer_share": contributions["employer_share"],
                "employee_share": contributions["employee_share"],
                "total": contributions["total"],
                "gosi_registered": emp.gosi_registered,
                "subscription_number": f"GOSI-{tenant_prefix}-{emp_number}" if emp.gosi_registered else None,
            })

            total_employer += contributions["employer_share"]
            total_employee += contributions["employee_share"]

        return {
            "year": year,
            "month": month,
            "tenant_id": str(self.tenant_id),
            "total_employees": len(employees),
            "total_employer_contribution": round(total_employer, 2),
            "total_employee_contribution": round(total_employee, 2),
            "total_contributions": round(total_employer + total_employee, 2),
            "currency": "SAR",
            "employees": employee_records,
            "submitted": False,
            "submitted_at": None,
        }
