"""Admin service — business logic for tenant, employee, and department CRUD."""
import csv
import io
import logging
from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee, EmployeeStatus, Department
from app.models.tenant import Tenant, PlanTier

logger = logging.getLogger(__name__)

# Fields required in CSV import
CSV_REQUIRED_FIELDS = {"employee_number", "first_name", "last_name", "email", "national_id", "hire_date"}

# All valid CSV columns (maps CSV header -> Employee attribute)
EMPLOYEE_UPDATABLE = {
    "first_name", "last_name", "first_name_ar", "last_name_ar", "email", "phone",
    "national_id", "job_title", "job_title_ar", "manager_id", "department_id",
    "status", "hire_date", "end_date", "is_saudi", "salary_sar", "gosi_registered",
    "gender", "probation_end_date", "probation_completed", "contract_type",
    "work_mode", "wfh_days_per_week", "work_location", "whatsapp_number",
    "slack_user_id", "teams_user_id", "preferred_language", "preferred_channel",
}

TENANT_UPDATABLE = {"name", "name_ar", "plan", "cr_number", "gosi_number", "domain"}

DEPARTMENT_UPDATABLE = {"name", "name_ar", "manager_id", "headcount_budget", "cost_budget_sar"}

CSV_VALID_COLUMNS = {
    "employee_number", "first_name", "last_name", "first_name_ar", "last_name_ar",
    "email", "phone", "national_id", "job_title", "hire_date", "is_saudi",
    "salary_sar", "department_id", "gender", "contract_type", "work_mode",
    "whatsapp_number", "preferred_language", "preferred_channel",
}


class AdminService:
    """Handles tenant, employee, and department business logic."""

    def __init__(self, db: AsyncSession, tenant_id: UUID):
        self.db = db
        self.tenant_id = tenant_id

    # ── Tenant ─────────────────────────────────────────────────────

    async def get_tenant(self) -> Tenant | None:
        result = await self.db.execute(
            select(Tenant).where(Tenant.id == self.tenant_id)
        )
        return result.scalar_one_or_none()

    async def update_tenant(self, data: dict[str, Any]) -> Tenant:
        tenant = await self.get_tenant()
        if not tenant:
            raise ValueError("Tenant not found")
        for key, value in data.items():
            if key in TENANT_UPDATABLE and hasattr(tenant, key) and value is not None:
                setattr(tenant, key, value)
        await self.db.commit()
        await self.db.refresh(tenant)
        return tenant

    # ── Employees ──────────────────────────────────────────────────

    async def list_employees(
        self,
        page: int = 1,
        per_page: int = 20,
        status: str | None = None,
        department_id: UUID | None = None,
        is_saudi: bool | None = None,
        search: str | None = None,
    ) -> dict[str, Any]:
        base = select(Employee).where(Employee.tenant_id == self.tenant_id)

        if status:
            base = base.where(Employee.status == EmployeeStatus(status))
        if department_id:
            base = base.where(Employee.department_id == department_id)
        if is_saudi is not None:
            base = base.where(Employee.is_saudi == is_saudi)
        if search:
            search_escaped = search.replace('%', '\\%').replace('_', '\\_')
            term = f"%{search_escaped}%"
            base = base.where(
                or_(
                    Employee.first_name.ilike(term),
                    Employee.last_name.ilike(term),
                    Employee.email.ilike(term),
                    Employee.employee_number.ilike(term),
                )
            )

        # Total count
        count_q = select(func.count()).select_from(base.subquery())
        total = (await self.db.execute(count_q)).scalar_one()

        # Paginated results
        offset = (page - 1) * per_page
        query = base.order_by(Employee.first_name).offset(offset).limit(per_page)
        result = await self.db.execute(query)
        employees = result.scalars().all()

        pages = (total + per_page - 1) // per_page if per_page else 1

        return {
            "items": employees,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
        }

    async def create_employee(self, data: dict[str, Any], flush_only: bool = False) -> Employee:
        # Check unique employee_number per tenant
        if data.get("employee_number"):
            existing = await self.db.execute(
                select(Employee).where(
                    Employee.tenant_id == self.tenant_id,
                    Employee.employee_number == data["employee_number"],
                )
            )
            if existing.scalar_one_or_none():
                raise ValueError(f"Employee number '{data['employee_number']}' already exists")

        # Check unique email per tenant
        existing_email = await self.db.execute(
            select(Employee).where(
                Employee.tenant_id == self.tenant_id,
                Employee.email == data["email"],
            )
        )
        if existing_email.scalar_one_or_none():
            raise ValueError(f"Email '{data['email']}' already exists")

        employee = Employee(tenant_id=self.tenant_id, **data)
        self.db.add(employee)
        if flush_only:
            await self.db.flush()
        else:
            await self.db.commit()
            await self.db.refresh(employee)
        return employee

    async def get_employee(self, employee_id: UUID) -> Employee | None:
        result = await self.db.execute(
            select(Employee).where(
                Employee.id == employee_id,
                Employee.tenant_id == self.tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def update_employee(self, employee_id: UUID, data: dict[str, Any]) -> Employee:
        employee = await self.get_employee(employee_id)
        if not employee:
            raise ValueError("Employee not found")

        # If changing employee_number, check uniqueness
        if "employee_number" in data and data["employee_number"] != employee.employee_number:
            existing = await self.db.execute(
                select(Employee).where(
                    Employee.tenant_id == self.tenant_id,
                    Employee.employee_number == data["employee_number"],
                    Employee.id != employee_id,
                )
            )
            if existing.scalar_one_or_none():
                raise ValueError(f"Employee number '{data['employee_number']}' already exists")

        # If changing email, check uniqueness
        if "email" in data and data["email"] != employee.email:
            existing = await self.db.execute(
                select(Employee).where(
                    Employee.tenant_id == self.tenant_id,
                    Employee.email == data["email"],
                    Employee.id != employee_id,
                )
            )
            if existing.scalar_one_or_none():
                raise ValueError(f"Email '{data['email']}' already exists")

        for key, value in data.items():
            if key in EMPLOYEE_UPDATABLE and hasattr(employee, key):
                setattr(employee, key, value)

        employee.updated_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(employee)
        return employee

    async def soft_delete_employee(self, employee_id: UUID) -> Employee:
        employee = await self.get_employee(employee_id)
        if not employee:
            raise ValueError("Employee not found")

        employee.status = EmployeeStatus.terminated
        employee.end_date = date.today()
        employee.updated_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(employee)
        return employee

    # ── Departments ────────────────────────────────────────────────

    async def list_departments_with_counts(self) -> list[dict[str, Any]]:
        # Get departments with active employee count
        query = (
            select(
                Department,
                func.count(Employee.id).filter(
                    Employee.status != EmployeeStatus.terminated
                ).label("active_count"),
            )
            .outerjoin(Employee, and_(
                Employee.department_id == Department.id,
                Employee.tenant_id == self.tenant_id,
            ))
            .where(Department.tenant_id == self.tenant_id)
            .group_by(Department.id)
            .order_by(Department.name)
        )
        result = await self.db.execute(query)
        rows = result.all()

        return [
            {
                "id": str(dept.id),
                "name": dept.name,
                "name_ar": dept.name_ar,
                "manager_id": str(dept.manager_id) if dept.manager_id else None,
                "headcount_budget": dept.headcount_budget,
                "cost_budget_sar": dept.cost_budget_sar,
                "active_employee_count": count,
            }
            for dept, count in rows
        ]

    async def create_department(self, data: dict[str, Any]) -> Department:
        department = Department(tenant_id=self.tenant_id, **data)
        self.db.add(department)
        await self.db.commit()
        await self.db.refresh(department)
        return department

    async def update_department(self, department_id: UUID, data: dict[str, Any]) -> Department:
        result = await self.db.execute(
            select(Department).where(
                Department.id == department_id,
                Department.tenant_id == self.tenant_id,
            )
        )
        department = result.scalar_one_or_none()
        if not department:
            raise ValueError("Department not found")

        for key, value in data.items():
            if key in DEPARTMENT_UPDATABLE and hasattr(department, key):
                setattr(department, key, value)

        await self.db.commit()
        await self.db.refresh(department)
        return department

    async def delete_department(self, department_id: UUID) -> None:
        result = await self.db.execute(
            select(Department).where(
                Department.id == department_id,
                Department.tenant_id == self.tenant_id,
            )
        )
        department = result.scalar_one_or_none()
        if not department:
            raise ValueError("Department not found")

        # Check for active employees
        active_count = (await self.db.execute(
            select(func.count(Employee.id)).where(
                Employee.department_id == department_id,
                Employee.tenant_id == self.tenant_id,
                Employee.status != EmployeeStatus.terminated,
            )
        )).scalar_one()

        if active_count > 0:
            raise PermissionError(
                f"Cannot delete department with {active_count} active employee(s)"
            )

        await self.db.delete(department)
        await self.db.commit()

    # ── CSV Import / Export ────────────────────────────────────────

    async def import_employees_csv(self, content: str) -> dict[str, Any]:
        """Parse CSV content, validate rows, create employees.

        Returns {created: int, errors: [{row, field, error}]}.
        """
        reader = csv.DictReader(io.StringIO(content))
        errors: list[dict[str, Any]] = []
        created = 0

        if not reader.fieldnames:
            return {"created": 0, "errors": [{"row": 0, "field": "", "error": "Empty or invalid CSV"}]}

        # Validate headers
        headers = set(reader.fieldnames)
        missing = CSV_REQUIRED_FIELDS - headers
        if missing:
            return {
                "created": 0,
                "errors": [{"row": 0, "field": f, "error": "Missing required column"} for f in missing],
            }

        for row_num, row in enumerate(reader, start=2):  # row 1 is header
            row_errors = []

            # Check required fields are non-empty
            for field in CSV_REQUIRED_FIELDS:
                if not row.get(field, "").strip():
                    row_errors.append({"row": row_num, "field": field, "error": "Required field is empty"})

            if row_errors:
                errors.extend(row_errors)
                continue

            # Build employee data
            data: dict[str, Any] = {}
            for col in CSV_VALID_COLUMNS:
                val = row.get(col, "").strip()
                if not val:
                    continue
                if col == "hire_date":
                    try:
                        data[col] = date.fromisoformat(val)
                    except ValueError:
                        row_errors.append({"row": row_num, "field": col, "error": "Invalid date format (use YYYY-MM-DD)"})
                elif col == "is_saudi":
                    data[col] = val.lower() in ("true", "1", "yes")
                elif col == "salary_sar":
                    try:
                        data[col] = int(val)
                    except ValueError:
                        row_errors.append({"row": row_num, "field": col, "error": "Must be an integer"})
                elif col == "department_id":
                    try:
                        data[col] = UUID(val)
                    except ValueError:
                        row_errors.append({"row": row_num, "field": col, "error": "Invalid UUID"})
                else:
                    data[col] = val

            if row_errors:
                errors.extend(row_errors)
                continue

            # Set defaults
            if "job_title" not in data:
                data["job_title"] = "Employee"

            # Check uniqueness
            try:
                await self.create_employee(data, flush_only=True)
                created += 1
            except ValueError as e:
                errors.append({"row": row_num, "field": "employee_number", "error": str(e)})

        if errors and created == 0:
            await self.db.rollback()
        elif created > 0:
            try:
                await self.db.commit()
            except Exception:
                await self.db.rollback()
                return {"created": 0, "errors": [{"row": 0, "field": "", "error": "Database error during import, all rows rolled back"}]}

        return {"created": created, "errors": errors}

    async def export_employees_csv(self) -> str:
        """Export all tenant employees as CSV string."""
        result = await self.db.execute(
            select(Employee)
            .where(Employee.tenant_id == self.tenant_id)
            .order_by(Employee.employee_number)
        )
        employees = result.scalars().all()

        output = io.StringIO()
        columns = [
            "employee_number", "first_name", "last_name", "first_name_ar", "last_name_ar",
            "email", "phone", "national_id", "job_title", "hire_date", "end_date",
            "status", "is_saudi", "salary_sar", "gender", "contract_type", "work_mode",
            "department_id", "whatsapp_number", "preferred_language", "preferred_channel",
        ]
        writer = csv.DictWriter(output, fieldnames=columns)
        writer.writeheader()

        for emp in employees:
            row = {}
            for col in columns:
                val = getattr(emp, col, None)
                if col == "national_id" and val:
                    row[col] = f"****{str(val)[-4:]}"
                elif col == "salary_sar":
                    row[col] = "***"
                elif val is None:
                    row[col] = ""
                elif isinstance(val, (date, datetime)):
                    row[col] = val.isoformat()
                elif hasattr(val, "value"):  # Enum
                    row[col] = val.value
                elif isinstance(val, bool):
                    row[col] = str(val).lower()
                else:
                    row[col] = str(val)
            writer.writerow(row)

        return output.getvalue()
