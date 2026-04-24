"""Employee role derivation -- determines access role from existing model data."""
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee, Department


async def derive_employee_role(
    db: AsyncSession, tenant_id: UUID, employee_id: UUID
) -> str:
    """Derive an employee's access role from existing model data.

    Role hierarchy (highest wins):
    - "c_suite"          -- job_title contains CEO/CFO/COO/CTO/CHRO/VP (EN or AR)
    - "hr_admin"         -- job_title contains 'HR Director' / 'HR Admin'
    - "hr_manager"       -- job_title contains 'HR Manager'
    - "hr_specialist"    -- job_title contains 'HR Specialist' / 'HR Coordinator'
    - "department_head"  -- employee is Department.manager_id for any department
    - "manager"          -- employee is manager_id for at least one other employee
    - "employee"         -- default

    HR roles are checked before department_head so that an HR Manager who also
    manages the HR department gets the broader hr_manager privileges (org-wide)
    rather than the narrower department_head scope.
    """
    emp_result = await db.execute(
        select(Employee).where(
            Employee.id == employee_id,
            Employee.tenant_id == tenant_id,
        )
    )
    emp = emp_result.scalar_one_or_none()
    if not emp:
        return "employee"

    title_lower = (emp.job_title or "").lower()
    title_ar = emp.job_title_ar or ""

    # C-suite check — use word-boundary regex to avoid false positives
    # (e.g., "coordinator" must not match "coo")
    import re
    c_suite_pattern = re.compile(
        r"\b(ceo|cfo|coo|cto|chro|chief|vice president)\b|^vp\b|\bvp$|\bvp\s",
        re.IGNORECASE,
    )
    c_suite_keywords_ar = ["رئيس تنفيذي", "نائب الرئيس"]
    if c_suite_pattern.search(title_lower) or any(kw in title_ar for kw in c_suite_keywords_ar):
        return "c_suite"

    # HR role checks — evaluated before department_head so HR staff who
    # also manage the HR department get org-wide HR privileges.
    hr_admin_kw = ["hr director", "hr admin", "head of hr", "مدير الموارد البشرية"]
    if any(kw in title_lower or kw in title_ar for kw in hr_admin_kw):
        return "hr_admin"

    hr_mgr_kw = ["hr manager", "مدير الموارد", "hr lead"]
    if any(kw in title_lower or kw in title_ar for kw in hr_mgr_kw):
        return "hr_manager"

    hr_spec_kw = ["hr specialist", "hr coordinator", "hr officer", "أخصائي موارد بشرية", "منسق موارد بشرية"]
    if any(kw in title_lower or kw in title_ar for kw in hr_spec_kw):
        return "hr_specialist"

    # Department head check
    dept_result = await db.execute(
        select(func.count()).select_from(Department).where(
            Department.manager_id == employee_id,
            Department.tenant_id == tenant_id,
        )
    )
    is_dept_head = (dept_result.scalar() or 0) > 0

    if is_dept_head:
        return "department_head"

    # Manager check -- has direct reports
    report_result = await db.execute(
        select(func.count()).select_from(Employee).where(
            Employee.manager_id == employee_id,
            Employee.tenant_id == tenant_id,
        )
    )
    if report_result.scalar() > 0:
        return "manager"

    return "employee"
