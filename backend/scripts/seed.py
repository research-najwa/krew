"""Seed the database with a sample Saudi company for development."""
import asyncio
import os
import sys
from pathlib import Path
from datetime import date
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text
from app.database import async_session
from app.models.tenant import Tenant, PlanTier
from app.models.employee import Employee, Department, EmployeeStatus, WorkMode, Gender
from app.models.leave import LeaveBalance, LeaveType
from app.models.leave_policy import LeavePolicy
from app.models.admin_user import AdminUser, AdminRole
from app.auth.passwords import hash_password


async def seed():
    async with async_session() as db:
        # Check if already seeded
        result = await db.execute(text("SELECT count(*) FROM tenants"))
        if result.scalar() > 0:
            print("Database already seeded. Skipping.")
            return

        # ── Tenant ──
        tenant_id = uuid4()
        tenant = Tenant(
            id=tenant_id,
            name="Noor Technologies",
            name_ar="تقنيات نور",
            domain="noortech.sa",
            plan=PlanTier.growth,
            employee_count=12,
            cr_number="1010234567",
            gosi_number="12345678",
        )
        db.add(tenant)

        # ── Departments ──
        eng_id = uuid4()
        hr_id = uuid4()
        sales_id = uuid4()

        departments = [
            Department(id=eng_id, tenant_id=tenant_id, name="Engineering", name_ar="الهندسة", headcount_budget=20, cost_budget_sar=500000),
            Department(id=hr_id, tenant_id=tenant_id, name="Human Resources", name_ar="الموارد البشرية", headcount_budget=5, cost_budget_sar=150000),
            Department(id=sales_id, tenant_id=tenant_id, name="Sales", name_ar="المبيعات", headcount_budget=10, cost_budget_sar=300000),
        ]
        for d in departments:
            db.add(d)
        await db.flush()

        # ── Employees ──
        employees_data = [
            {
                "id": uuid4(),
                "employee_number": "EMP-001",
                "first_name": "Ahmed", "last_name": "Al-Rashidi",
                "first_name_ar": "أحمد", "last_name_ar": "الراشدي",
                "email": "ahmed@noortech.sa", "phone": "+966501234567",
                "national_id": "1098765432",
                "job_title": "VP of Engineering", "job_title_ar": "نائب رئيس الهندسة",
                "department_id": eng_id,
                "hire_date": date(2023, 1, 15),
                "is_saudi": True, "salary_sar": 35000, "gosi_registered": True,
                "work_mode": WorkMode.hybrid, "wfh_days_per_week": 2,
                "work_location": "Riyadh HQ",
                "whatsapp_number": "+966501234567",
                "preferred_language": "ar",
                "gender": Gender.male,
                "probation_completed": True,
            },
            {
                "id": uuid4(),
                "employee_number": "EMP-002",
                "first_name": "Fatimah", "last_name": "Al-Zahrani",
                "first_name_ar": "فاطمة", "last_name_ar": "الزهراني",
                "email": "fatimah@noortech.sa", "phone": "+966502345678",
                "national_id": "1087654321",
                "job_title": "HR Manager", "job_title_ar": "مديرة الموارد البشرية",
                "department_id": hr_id,
                "hire_date": date(2023, 3, 1),
                "is_saudi": True, "salary_sar": 28000, "gosi_registered": True,
                "work_mode": WorkMode.onsite,
                "work_location": "Riyadh HQ",
                "whatsapp_number": "+966502345678",
                "preferred_language": "ar",
                "gender": Gender.female,
                "probation_completed": True,
            },
            {
                "id": uuid4(),
                "employee_number": "EMP-003",
                "first_name": "Omar", "last_name": "Hassan",
                "first_name_ar": "عمر", "last_name_ar": "حسن",
                "email": "omar@noortech.sa", "phone": "+966503456789",
                "national_id": "2198765432",
                "job_title": "Senior Developer", "job_title_ar": "مطور أول",
                "department_id": eng_id,
                "hire_date": date(2023, 6, 15),
                "is_saudi": False, "salary_sar": 22000, "gosi_registered": True,
                "work_mode": WorkMode.remote,
                "work_location": "Remote - Jeddah",
                "whatsapp_number": "+966503456789",
                "preferred_language": "en",
                "gender": Gender.male,
                "probation_completed": True,
            },
            {
                "id": uuid4(),
                "employee_number": "EMP-004",
                "first_name": "Sara", "last_name": "Al-Otaibi",
                "first_name_ar": "سارة", "last_name_ar": "العتيبي",
                "email": "sara@noortech.sa", "phone": "+966504567890",
                "national_id": "1076543210",
                "job_title": "Sales Executive", "job_title_ar": "تنفيذية مبيعات",
                "department_id": sales_id,
                "hire_date": date(2026, 1, 10),
                "is_saudi": True, "salary_sar": 18000, "gosi_registered": True,
                "work_mode": WorkMode.onsite,
                "work_location": "Riyadh HQ",
                "whatsapp_number": "+966504567890",
                "preferred_language": "ar",
                "gender": Gender.female,
                "probation_completed": False,
                "probation_end_date": date(2026, 4, 10),  # hire_date + 90 days
            },
            {
                "id": uuid4(),
                "employee_number": "EMP-005",
                "first_name": "Khalid", "last_name": "Al-Dossari",
                "first_name_ar": "خالد", "last_name_ar": "الدوسري",
                "email": "khalid@noortech.sa", "phone": "+966505678901",
                "national_id": "1065432109",
                "job_title": "Backend Developer", "job_title_ar": "مطور خلفي",
                "department_id": eng_id,
                "hire_date": date(2024, 3, 20),
                "is_saudi": True, "salary_sar": 20000, "gosi_registered": True,
                "work_mode": WorkMode.hybrid, "wfh_days_per_week": 3,
                "work_location": "Riyadh HQ",
                "whatsapp_number": "+966505678901",
                "preferred_language": "ar",
                "gender": Gender.male,
                "probation_completed": True,
            },
            {
                "id": uuid4(),
                "employee_number": "EMP-006",
                "first_name": "Noura", "last_name": "Al-Qahtani",
                "first_name_ar": "نورة", "last_name_ar": "القحطاني",
                "email": "noura@noortech.sa", "phone": "+966506789012",
                "national_id": "1054321098",
                "job_title": "UX Designer", "job_title_ar": "مصممة تجربة المستخدم",
                "department_id": eng_id,
                "hire_date": date(2024, 6, 1),
                "is_saudi": True, "salary_sar": 19000, "gosi_registered": True,
                "work_mode": WorkMode.hybrid, "wfh_days_per_week": 2,
                "work_location": "Riyadh HQ",
                "whatsapp_number": "+966506789012",
                "preferred_language": "ar",
                "gender": Gender.female,
                "probation_completed": True,
            },
        ]

        emp_objects = []
        for emp_data in employees_data:
            emp = Employee(tenant_id=tenant_id, status=EmployeeStatus.active, **emp_data)
            db.add(emp)
            emp_objects.append(emp)
        await db.flush()

        # Set department managers
        departments[0].manager_id = emp_objects[0].id  # Ahmed manages Engineering
        departments[1].manager_id = emp_objects[1].id  # Fatimah manages HR
        departments[2].manager_id = emp_objects[3].id  # Sara manages Sales

        # Set employee managers
        emp_objects[2].manager_id = emp_objects[0].id  # Omar reports to Ahmed
        emp_objects[4].manager_id = emp_objects[0].id  # Khalid reports to Ahmed
        emp_objects[5].manager_id = emp_objects[0].id  # Noura reports to Ahmed

        # ── Leave Balances (2026) ──
        year = 2026
        for emp in emp_objects:
            balances = [
                LeaveBalance(employee_id=emp.id, leave_type=LeaveType.annual, year=year, total_days=21, used_days=0),
                LeaveBalance(employee_id=emp.id, leave_type=LeaveType.sick, year=year, total_days=30, used_days=0),
                LeaveBalance(employee_id=emp.id, leave_type=LeaveType.emergency, year=year, total_days=5, used_days=0),
            ]
            if emp.is_saudi:
                balances.append(
                    LeaveBalance(employee_id=emp.id, leave_type=LeaveType.hajj, year=year, total_days=15, used_days=0)
                )
            for b in balances:
                db.add(b)

        # Give some employees used leave days for realism
        # Ahmed used 5 annual days
        ahmed_annual = [b for b in await _get_balances(db, emp_objects[0].id) if b.leave_type == LeaveType.annual]
        if ahmed_annual:
            ahmed_annual[0].used_days = 5

        # Sara used 2 sick days
        sara_sick = [b for b in await _get_balances(db, emp_objects[3].id) if b.leave_type == LeaveType.sick]
        if sara_sick:
            sara_sick[0].used_days = 2

        # ── Leave Policies (one per LeaveType) ──
        from datetime import timezone as _tz
        from datetime import datetime as _dt
        _now = _dt.now(_tz.utc)
        leave_policies = [
            LeavePolicy(
                tenant_id=tenant_id,
                leave_type=LeaveType.annual,
                default_days_per_year=21,
                extended_days_per_year=30,
                tenure_threshold_years=5,
                advance_notice_days=14,
                blocked_during_probation=True,
                requires_manager_approval=True,
                created_at=_now,
                updated_at=_now,
            ),
            LeavePolicy(
                tenant_id=tenant_id,
                leave_type=LeaveType.sick,
                default_days_per_year=30,
                auto_approve=True,
                auto_approve_max_days=3,
                requires_attachment=True,
                attachment_after_days=3,
                requires_manager_approval=True,
                created_at=_now,
                updated_at=_now,
            ),
            LeavePolicy(
                tenant_id=tenant_id,
                leave_type=LeaveType.emergency,
                default_days_per_year=5,
                auto_approve=True,
                auto_approve_max_days=1,
                requires_manager_approval=True,
                created_at=_now,
                updated_at=_now,
            ),
            LeavePolicy(
                tenant_id=tenant_id,
                leave_type=LeaveType.maternity,
                default_days_per_year=70,
                max_days_per_request=70,
                requires_hr_approval=True,
                requires_manager_approval=True,
                created_at=_now,
                updated_at=_now,
            ),
            LeavePolicy(
                tenant_id=tenant_id,
                leave_type=LeaveType.paternity,
                default_days_per_year=3,
                max_days_per_request=3,
                auto_approve=True,
                requires_manager_approval=True,
                created_at=_now,
                updated_at=_now,
            ),
            LeavePolicy(
                tenant_id=tenant_id,
                leave_type=LeaveType.hajj,
                default_days_per_year=15,
                max_days_per_request=15,
                advance_notice_days=30,
                requires_hr_approval=True,
                requires_manager_approval=True,
                created_at=_now,
                updated_at=_now,
            ),
            LeavePolicy(
                tenant_id=tenant_id,
                leave_type=LeaveType.bereavement,
                default_days_per_year=5,
                max_days_per_request=5,
                auto_approve=True,
                requires_manager_approval=True,
                created_at=_now,
                updated_at=_now,
            ),
            LeavePolicy(
                tenant_id=tenant_id,
                leave_type=LeaveType.unpaid,
                default_days_per_year=30,
                max_days_per_request=30,
                requires_hr_approval=True,
                requires_manager_approval=True,
                created_at=_now,
                updated_at=_now,
            ),
        ]
        for lp in leave_policies:
            db.add(lp)

        # ── Admin Users ──
        _default_super_pw = "ChangeMe123!"
        _default_tenant_pw = "NoorTech2026!"
        super_admin_pw = os.environ.get("KREW_SUPER_ADMIN_PASSWORD", _default_super_pw)
        tenant_admin_pw = os.environ.get("KREW_TENANT_ADMIN_PASSWORD", _default_tenant_pw)
        if super_admin_pw == _default_super_pw or tenant_admin_pw == _default_tenant_pw:
            print("  WARNING: Using default seed passwords. These are NOT safe for staging/production.")
            print("  Set KREW_SUPER_ADMIN_PASSWORD and KREW_TENANT_ADMIN_PASSWORD environment variables.")
        admin_users = [
            AdminUser(
                email="admin@krew.sa",
                full_name="Krew Super Admin",
                full_name_ar="مدير كرو",
                hashed_password=hash_password(super_admin_pw),
                role=AdminRole.super_admin,
                tenant_id=None,
                is_active=True,
            ),
            AdminUser(
                email="fatimah@noortech.sa",
                full_name="Fatimah Al-Zahrani",
                full_name_ar="فاطمة الزهراني",
                hashed_password=hash_password(tenant_admin_pw),
                role=AdminRole.tenant_admin,
                tenant_id=tenant_id,
                is_active=True,
            ),
            AdminUser(
                email="ahmed.hr@noortech.sa",
                full_name="Ahmed Al-Rashidi",
                full_name_ar="أحمد الراشدي",
                hashed_password=hash_password(tenant_admin_pw),
                role=AdminRole.hr_manager,
                tenant_id=tenant_id,
                is_active=True,
            ),
        ]
        for admin in admin_users:
            db.add(admin)

        await db.commit()

        print(f"Seeded successfully!")
        print(f"  Tenant: {tenant.name} ({tenant.name_ar})")
        print(f"  Departments: {len(departments)}")
        print(f"  Employees: {len(emp_objects)}")
        print(f"  Leave balances created for year {year}")
        print(f"  Leave policies: {len(leave_policies)}")
        print()
        print("Sample employees:")
        for emp in emp_objects:
            print(f"  {emp.employee_number} | {emp.first_name} {emp.last_name} | {emp.job_title} | {emp.id}")
        print()
        print("Admin users:")
        for admin in admin_users:
            print(f"  {admin.role.value} | {admin.email} | {admin.full_name}")


async def _get_balances(db, employee_id):
    from sqlalchemy import select
    result = await db.execute(
        select(LeaveBalance).where(LeaveBalance.employee_id == employee_id)
    )
    return result.scalars().all()


if __name__ == "__main__":
    asyncio.run(seed())
