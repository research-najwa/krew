"""Seed additional demo data — new hires, pending leaves, onboarding assignments.

Run AFTER seed.py (requires existing tenant + employees).
Idempotent: skips if demo data already exists.
"""
import asyncio
import sys
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select, text
from app.database import async_session
from app.models.tenant import Tenant
from app.models.employee import Employee, Department, EmployeeStatus, WorkMode, Gender
from app.models.leave import LeaveRequest, LeaveBalance, LeaveType, LeaveStatus
from app.models.onboarding import (
    OnboardingTemplate,
    OnboardingTemplateStep,
    OnboardingAssignment,
    OnboardingAssignmentStatus,
    OnboardingStepAssignment,
    OnboardingStepStatus,
    OnboardingStepType,
)


async def seed_demo():
    async with async_session() as db:
        # Find tenant
        result = await db.execute(select(Tenant).limit(1))
        tenant = result.scalar_one_or_none()
        if not tenant:
            print("No tenant found. Run seed.py first.")
            return
        tenant_id = tenant.id

        # Check if demo data already exists
        result = await db.execute(
            select(Employee).where(Employee.employee_number == "EMP-007")
        )
        if result.scalar_one_or_none():
            print("Demo data already seeded. Skipping.")
            return

        # Get existing employees and departments
        emp_result = await db.execute(
            select(Employee).where(Employee.tenant_id == tenant_id).order_by(Employee.employee_number)
        )
        existing_emps = {e.employee_number: e for e in emp_result.scalars().all()}

        dept_result = await db.execute(
            select(Department).where(Department.tenant_id == tenant_id)
        )
        depts = {d.name: d for d in dept_result.scalars().all()}

        ahmed = existing_emps.get("EMP-001")  # VP Engineering / Manager
        fatimah = existing_emps.get("EMP-002")  # HR Manager
        eng_dept = depts.get("Engineering")
        hr_dept = depts.get("Human Resources")
        sales_dept = depts.get("Sales")

        if not ahmed or not fatimah:
            print("Required employees (Ahmed/Fatimah) not found. Run seed.py first.")
            return

        # ── New Employees ──────────────────────────────────────────
        new_employees = [
            {
                "id": uuid4(),
                "employee_number": "EMP-007",
                "first_name": "Rayan", "last_name": "Al-Harbi",
                "first_name_ar": "ريان", "last_name_ar": "الحربي",
                "email": "rayan@noortech.sa", "phone": "+966507890123",
                "national_id": "1043210987",
                "job_title": "Frontend Developer", "job_title_ar": "مطور واجهات",
                "department_id": eng_dept.id,
                "manager_id": ahmed.id,
                "hire_date": date(2026, 3, 10),  # Very recent new hire
                "is_saudi": True, "salary_sar": 16000, "gosi_registered": True,
                "work_mode": WorkMode.hybrid, "wfh_days_per_week": 2,
                "work_location": "Riyadh HQ",
                "preferred_language": "ar",
                "gender": Gender.male,
                "probation_completed": False,
                "probation_end_date": date(2026, 6, 10),
            },
            {
                "id": uuid4(),
                "employee_number": "EMP-008",
                "first_name": "Lama", "last_name": "Al-Mutairi",
                "first_name_ar": "لمى", "last_name_ar": "المطيري",
                "email": "lama@noortech.sa", "phone": "+966508901234",
                "national_id": "1032109876",
                "job_title": "HR Coordinator", "job_title_ar": "منسقة موارد بشرية",
                "department_id": hr_dept.id,
                "manager_id": fatimah.id,
                "hire_date": date(2026, 3, 17),  # Just started last week
                "is_saudi": True, "salary_sar": 12000, "gosi_registered": True,
                "work_mode": WorkMode.onsite,
                "work_location": "Riyadh HQ",
                "preferred_language": "ar",
                "gender": Gender.female,
                "probation_completed": False,
                "probation_end_date": date(2026, 6, 17),
            },
            {
                "id": uuid4(),
                "employee_number": "EMP-009",
                "first_name": "Turki", "last_name": "Al-Shehri",
                "first_name_ar": "تركي", "last_name_ar": "الشهري",
                "email": "turki@noortech.sa", "phone": "+966509012345",
                "national_id": "2187654321",
                "job_title": "DevOps Engineer", "job_title_ar": "مهندس عمليات",
                "department_id": eng_dept.id,
                "manager_id": ahmed.id,
                "hire_date": date(2026, 2, 1),  # 7 weeks ago — should have some onboarding done
                "is_saudi": False, "salary_sar": 21000, "gosi_registered": True,
                "work_mode": WorkMode.remote,
                "work_location": "Remote - Dammam",
                "preferred_language": "en",
                "gender": Gender.male,
                "probation_completed": False,
                "probation_end_date": date(2026, 5, 1),
            },
            {
                "id": uuid4(),
                "employee_number": "EMP-010",
                "first_name": "Maha", "last_name": "Al-Subaie",
                "first_name_ar": "مها", "last_name_ar": "السبيعي",
                "email": "maha@noortech.sa", "phone": "+966510123456",
                "national_id": "1021098765",
                "job_title": "Sales Manager", "job_title_ar": "مديرة المبيعات",
                "department_id": sales_dept.id,
                "manager_id": ahmed.id,  # Reports to VP Eng (small startup)
                "hire_date": date(2024, 9, 1),
                "is_saudi": True, "salary_sar": 25000, "gosi_registered": True,
                "work_mode": WorkMode.onsite,
                "work_location": "Riyadh HQ",
                "preferred_language": "ar",
                "gender": Gender.female,
                "probation_completed": True,
            },
        ]

        emp_objects = {}
        for emp_data in new_employees:
            emp = Employee(tenant_id=tenant_id, status=EmployeeStatus.active, **emp_data)
            db.add(emp)
            emp_objects[emp_data["employee_number"]] = emp
        await db.flush()

        # Also make Sara (EMP-004) report to Maha (Sales Manager)
        sara = existing_emps.get("EMP-004")
        if sara:
            sara.manager_id = emp_objects["EMP-010"].id

        # ── Leave Balances for new employees (2026) ──
        year = 2026
        for emp in emp_objects.values():
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

        # ── Pending Leave Requests (for manager approval demo) ──
        # Khalid (EMP-005) wants annual leave
        khalid = existing_emps.get("EMP-005")
        omar = existing_emps.get("EMP-003")
        noura = existing_emps.get("EMP-006")

        pending_leaves = []
        if khalid:
            pending_leaves.append(LeaveRequest(
                employee_id=khalid.id,
                approver_id=ahmed.id,
                leave_type=LeaveType.annual,
                start_date=date(2026, 4, 6),
                end_date=date(2026, 4, 10),
                business_days=5,
                reason="Family trip to Abha",
                status=LeaveStatus.pending,
                created_by_agent="deema",
                created_via_channel="web",
            ))

        if omar:
            pending_leaves.append(LeaveRequest(
                employee_id=omar.id,
                approver_id=ahmed.id,
                leave_type=LeaveType.sick,
                start_date=date(2026, 3, 25),
                end_date=date(2026, 3, 26),
                business_days=2,
                reason="Doctor appointment + recovery",
                status=LeaveStatus.pending,
                created_by_agent="deema",
                created_via_channel="web",
            ))

        # Turki wants emergency leave
        turki = emp_objects["EMP-009"]
        pending_leaves.append(LeaveRequest(
            employee_id=turki.id,
            approver_id=ahmed.id,
            leave_type=LeaveType.emergency,
            start_date=date(2026, 3, 27),
            end_date=date(2026, 3, 27),
            business_days=1,
            reason="Family emergency",
            status=LeaveStatus.pending,
            created_by_agent="deema",
            created_via_channel="web",
        ))

        # An already-approved leave for calendar demo
        if noura:
            pending_leaves.append(LeaveRequest(
                employee_id=noura.id,
                approver_id=ahmed.id,
                leave_type=LeaveType.annual,
                start_date=date(2026, 4, 1),
                end_date=date(2026, 4, 3),
                business_days=3,
                reason="Personal",
                status=LeaveStatus.approved,
                approved_by=ahmed.id,
                approved_at=datetime.now(timezone.utc) - timedelta(days=3),
                created_by_agent="deema",
                created_via_channel="web",
            ))
            # Update Noura's balance
            noura_bal = await db.execute(
                select(LeaveBalance).where(
                    LeaveBalance.employee_id == noura.id,
                    LeaveBalance.leave_type == LeaveType.annual,
                    LeaveBalance.year == year,
                )
            )
            nb = noura_bal.scalar_one_or_none()
            if nb:
                nb.used_days = 3

        for lr in pending_leaves:
            db.add(lr)

        # ── Onboarding Template ──────────────────────────────────
        # Check if template already exists
        tmpl_result = await db.execute(
            select(OnboardingTemplate).where(
                OnboardingTemplate.tenant_id == tenant_id,
                OnboardingTemplate.is_default.is_(True),
            )
        )
        template = tmpl_result.scalar_one_or_none()

        if not template:
            template = OnboardingTemplate(
                tenant_id=tenant_id,
                name="Standard Onboarding",
                name_ar="التهيئة القياسية",
                description="Standard onboarding checklist for all new Noor Tech employees",
                is_active=True,
                is_default=True,
            )
            db.add(template)
            await db.flush()

            steps_data = [
                {"name": "Sign employment contract", "name_ar": "توقيع عقد العمل", "order": 1, "due_days": 1, "type": "manual"},
                {"name": "Complete GOSI registration", "name_ar": "اكمال تسجيل التأمينات", "order": 2, "due_days": 3, "type": "manual"},
                {"name": "Set up workstation & accounts", "name_ar": "تجهيز محطة العمل والحسابات", "order": 3, "due_days": 1, "type": "manual"},
                {"name": "Read & acknowledge company policies", "name_ar": "قراءة سياسات الشركة والموافقة", "order": 4, "due_days": 3, "type": "automatic", "trigger": "policy_acknowledged"},
                {"name": "Meet your team & manager", "name_ar": "تعرف على فريقك ومديرك", "order": 5, "due_days": 2, "type": "manual"},
                {"name": "Complete security training", "name_ar": "اكمال التدريب الأمني", "order": 6, "due_days": 7, "type": "manual"},
                {"name": "Submit bank account details", "name_ar": "تقديم بيانات الحساب البنكي", "order": 7, "due_days": 5, "type": "manual"},
                {"name": "First week check-in with HR", "name_ar": "متابعة الأسبوع الأول مع الموارد البشرية", "order": 8, "due_days": 7, "type": "agent_assisted"},
                {"name": "Complete department-specific orientation", "name_ar": "اكمال التوجيه الخاص بالقسم", "order": 9, "due_days": 14, "type": "manual"},
                {"name": "30-day performance check-in", "name_ar": "متابعة الأداء بعد 30 يوم", "order": 10, "due_days": 30, "type": "agent_assisted", "required": False},
            ]

            template_steps = []
            for sd in steps_data:
                step = OnboardingTemplateStep(
                    template_id=template.id,
                    name=sd["name"],
                    name_ar=sd["name_ar"],
                    order=sd["order"],
                    due_days_after_hire=sd["due_days"],
                    step_type=OnboardingStepType(sd["type"]),
                    is_required=sd.get("required", True),
                    auto_trigger=sd.get("trigger"),
                )
                db.add(step)
                template_steps.append(step)
            await db.flush()
        else:
            # Load existing steps
            step_result = await db.execute(
                select(OnboardingTemplateStep)
                .where(OnboardingTemplateStep.template_id == template.id)
                .order_by(OnboardingTemplateStep.order)
            )
            template_steps = list(step_result.scalars().all())

        # ── Onboarding Assignments ───────────────────────────────
        now = datetime.now(timezone.utc)

        async def create_assignment(emp, completed_step_indices: list[int], started_at=None):
            """Create an onboarding assignment with some steps completed."""
            # Check if already exists
            existing = await db.execute(
                select(OnboardingAssignment).where(
                    OnboardingAssignment.employee_id == emp.id,
                    OnboardingAssignment.template_id == template.id,
                )
            )
            if existing.scalar_one_or_none():
                return

            assignment = OnboardingAssignment(
                tenant_id=tenant_id,
                employee_id=emp.id,
                template_id=template.id,
                started_at=started_at or now,
            )
            db.add(assignment)
            await db.flush()

            for i, step in enumerate(template_steps):
                due_dt = datetime.combine(
                    emp.hire_date + timedelta(days=step.due_days_after_hire),
                    datetime.min.time(),
                ).replace(tzinfo=timezone.utc)

                is_completed = i in completed_step_indices
                step_assign = OnboardingStepAssignment(
                    assignment_id=assignment.id,
                    template_step_id=step.id,
                    order=step.order,
                    due_date=due_dt,
                    status=OnboardingStepStatus.completed if is_completed else OnboardingStepStatus.pending,
                    completed_at=now - timedelta(days=len(completed_step_indices) - completed_step_indices.index(i)) if is_completed else None,
                    completed_by=f"hr:{fatimah.id}" if is_completed else None,
                )
                db.add(step_assign)

        # Rayan (EMP-007) — hired March 10, 2 weeks ago, 3/10 steps done
        await create_assignment(
            emp_objects["EMP-007"],
            completed_step_indices=[0, 1, 2],  # Contract, GOSI, workstation
            started_at=datetime(2026, 3, 10, tzinfo=timezone.utc),
        )

        # Lama (EMP-008) — hired March 17, 1 week ago, 2/10 steps done
        await create_assignment(
            emp_objects["EMP-008"],
            completed_step_indices=[0, 2],  # Contract, workstation (skipped GOSI temporarily)
            started_at=datetime(2026, 3, 17, tzinfo=timezone.utc),
        )

        # Turki (EMP-009) — hired Feb 1, ~7 weeks ago, 7/10 steps done — almost complete
        await create_assignment(
            emp_objects["EMP-009"],
            completed_step_indices=[0, 1, 2, 3, 4, 5, 6],  # Missing week check-in, dept orientation, 30-day
            started_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
        )

        # Also create assignments for existing employees if they don't have one
        if khalid:
            await create_assignment(
                khalid,
                completed_step_indices=[0, 1, 2, 3, 4],  # 5/10 done (50%)
                started_at=datetime(2024, 3, 20, tzinfo=timezone.utc),
            )

        if noura:
            await create_assignment(
                noura,
                completed_step_indices=[0, 1],  # 2/10 done (25% — many overdue)
                started_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
            )

        await db.commit()

        print("Demo data seeded successfully!")
        print()
        print("New employees:")
        for num, emp in emp_objects.items():
            print(f"  {num} | {emp.first_name} {emp.last_name} ({emp.first_name_ar} {emp.last_name_ar}) | {emp.job_title}")
        print()
        print(f"Pending leave requests: {len([lr for lr in pending_leaves if lr.status == LeaveStatus.pending])}")
        print(f"Approved leave requests: {len([lr for lr in pending_leaves if lr.status == LeaveStatus.approved])}")
        print()
        print("Onboarding assignments:")
        print("  EMP-007 Rayan   — 3/10 steps (Day 14, some overdue)")
        print("  EMP-008 Lama    — 2/10 steps (Day 7, GOSI overdue)")
        print("  EMP-009 Turki   — 7/10 steps (Week 7, nearly complete)")
        print("  EMP-005 Khalid  — 5/10 steps (long overdue)")
        print("  EMP-006 Noura   — 2/10 steps (very overdue)")
        print()
        print("Ahmed (EMP-001) now manages: Omar, Khalid, Noura, Rayan, Turki, Maha (6 reports)")
        print("Fatimah (EMP-002) manages: Lama (1 report)")
        print("Maha (EMP-010) manages: Sara (1 report)")
        print()
        print("Demo scenarios ready:")
        print("  1. As Ahmed: 'show my team' / 'عرض فريقي'")
        print("  2. As Ahmed: 'pending approvals' / 'الموافقات المعلقة'")
        print("  3. As Ahmed: 'show leave calendar for April' / 'تقويم الإجازات'")
        print("  4. As Ahmed: 'team headcount' / 'عدد الموظفين'")
        print("  5. As anyone: 'onboarding dashboard' / 'لوحة التهيئة'")
        print("  6. As anyone: 'overdue onboarding steps' / 'خطوات التهيئة المتأخرة'")
        print("  7. As Ahmed: 'check onboarding for Rayan' / 'تهيئة ريان'")
        print("  8. As Ahmed: 'complete step X for Rayan'")


if __name__ == "__main__":
    asyncio.run(seed_demo())
