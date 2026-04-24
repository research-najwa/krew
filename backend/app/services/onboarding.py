"""Onboarding service — template management, assignment lifecycle, overdue detection."""
import uuid
import logging
from datetime import datetime, timedelta, timezone, date

from sqlalchemy import select, func, and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.employee import Employee
from app.models.onboarding import (
    OnboardingTemplate,
    OnboardingTemplateStep,
    OnboardingAssignment,
    OnboardingAssignmentStatus,
    OnboardingStepAssignment,
    OnboardingStepStatus,
    OnboardingStepType,
)

logger = logging.getLogger(__name__)


class OnboardingService:

    def __init__(self, db: AsyncSession, tenant_id: uuid.UUID):
        self.db = db
        self.tenant_id = tenant_id

    # ── Template CRUD ───────────────────────────────────────────

    async def create_template(self, name: str, name_ar: str | None, description: str | None,
                               is_default: bool, steps: list[dict]) -> dict:
        template = OnboardingTemplate(
            tenant_id=self.tenant_id,
            name=name,
            name_ar=name_ar,
            description=description,
            is_default=is_default,
        )
        self.db.add(template)
        await self.db.flush()

        for i, step_data in enumerate(steps):
            step = OnboardingTemplateStep(
                template_id=template.id,
                name=step_data["name"],
                name_ar=step_data.get("name_ar"),
                description=step_data.get("description"),
                description_ar=step_data.get("description_ar"),
                step_type=OnboardingStepType(step_data.get("step_type", "manual")),
                order=step_data.get("order", i + 1),
                due_days_after_hire=step_data.get("due_days_after_hire", 7),
                is_required=step_data.get("is_required", True),
                auto_trigger=step_data.get("auto_trigger"),
            )
            self.db.add(step)

        await self.db.commit()
        await self.db.refresh(template)
        return {"template_id": str(template.id), "name": template.name, "step_count": len(steps)}

    async def list_templates(self) -> list[dict]:
        result = await self.db.execute(
            select(OnboardingTemplate)
            .where(OnboardingTemplate.tenant_id == self.tenant_id)
            .options(selectinload(OnboardingTemplate.steps))
            .order_by(OnboardingTemplate.created_at.desc())
        )
        templates = result.scalars().all()
        return [
            {
                "id": str(t.id), "name": t.name, "name_ar": t.name_ar,
                "is_active": t.is_active, "is_default": t.is_default,
                "step_count": len(t.steps),
            }
            for t in templates
        ]

    # ── Assignment Lifecycle ────────────────────────────────────

    async def assign_to_employee(
        self, employee_id: uuid.UUID, template_id: uuid.UUID | None = None
    ) -> dict:
        """Assign an onboarding checklist to an employee.

        If template_id is None, use the tenant's default template.
        """
        # Resolve template
        if template_id:
            result = await self.db.execute(
                select(OnboardingTemplate)
                .where(
                    OnboardingTemplate.id == template_id,
                    OnboardingTemplate.tenant_id == self.tenant_id,
                    OnboardingTemplate.is_active.is_(True),
                )
                .options(selectinload(OnboardingTemplate.steps))
            )
        else:
            result = await self.db.execute(
                select(OnboardingTemplate)
                .where(
                    OnboardingTemplate.tenant_id == self.tenant_id,
                    OnboardingTemplate.is_default.is_(True),
                    OnboardingTemplate.is_active.is_(True),
                )
                .options(selectinload(OnboardingTemplate.steps))
            )
        template = result.scalar_one_or_none()
        if not template:
            return {"error": "No active onboarding template found."}

        # Get employee hire_date for due date calculation
        emp_result = await self.db.execute(
            select(Employee).where(
                Employee.id == employee_id,
                Employee.tenant_id == self.tenant_id,
            )
        )
        employee = emp_result.scalar_one_or_none()
        if not employee:
            return {"error": "Employee not found."}

        if not employee.hire_date:
            return {"error": "Employee has no hire date set. Cannot calculate step due dates."}

        # Create assignment
        assignment = OnboardingAssignment(
            tenant_id=self.tenant_id,
            employee_id=employee_id,
            template_id=template.id,
        )
        self.db.add(assignment)
        try:
            await self.db.flush()
        except IntegrityError:
            await self.db.rollback()
            return {"error": "This employee already has an active onboarding assignment for this template."}

        # Create step assignments
        for step in template.steps:
            due_dt = datetime.combine(
                employee.hire_date + timedelta(days=step.due_days_after_hire),
                datetime.min.time(),
            ).replace(tzinfo=timezone.utc)

            step_assignment = OnboardingStepAssignment(
                assignment_id=assignment.id,
                template_step_id=step.id,
                order=step.order,
                due_date=due_dt,
            )
            self.db.add(step_assignment)

        await self.db.commit()
        return {
            "assignment_id": str(assignment.id),
            "employee_id": str(employee_id),
            "template": template.name,
            "step_count": len(template.steps),
        }

    async def get_employee_onboarding(self, employee_id: uuid.UUID) -> dict | None:
        """Get the current onboarding status for an employee."""
        result = await self.db.execute(
            select(OnboardingAssignment)
            .where(
                OnboardingAssignment.tenant_id == self.tenant_id,
                OnboardingAssignment.employee_id == employee_id,
                OnboardingAssignment.status == OnboardingAssignmentStatus.in_progress,
            )
            .options(
                selectinload(OnboardingAssignment.step_statuses)
                .selectinload(OnboardingStepAssignment.template_step)
            )
        )
        assignment = result.scalar_one_or_none()
        if not assignment:
            return None

        now = datetime.now(timezone.utc)
        steps = []
        completed_count = 0
        for sa in assignment.step_statuses:
            is_overdue = (
                sa.status in (OnboardingStepStatus.pending, OnboardingStepStatus.in_progress)
                and sa.due_date
                and now > sa.due_date
            )
            step_info = {
                "step_id": str(sa.id),
                "name": sa.template_step.name,
                "name_ar": sa.template_step.name_ar,
                "step_type": sa.template_step.step_type.value,
                "status": sa.status.value,
                "due_date": sa.due_date.isoformat() if sa.due_date else None,
                "is_overdue": is_overdue,
                "is_required": sa.template_step.is_required,
                "completed_at": sa.completed_at.isoformat() if sa.completed_at else None,
            }
            steps.append(step_info)
            if sa.status == OnboardingStepStatus.completed:
                completed_count += 1

        total = len(steps)
        return {
            "assignment_id": str(assignment.id),
            "status": assignment.status,
            "progress_pct": round((completed_count / total * 100) if total > 0 else 0),
            "completed_steps": completed_count,
            "total_steps": total,
            "steps": steps,
        }

    async def complete_step(
        self, assignment_id: uuid.UUID, step_id: uuid.UUID, completed_by: str,
        employee_id: uuid.UUID | None = None,
    ) -> dict:
        """Mark a single onboarding step as completed.

        Args:
            employee_id: When provided, verifies the assignment belongs to this
                         employee (defense-in-depth ownership check).
        """
        conditions = [
            OnboardingStepAssignment.id == step_id,
            OnboardingStepAssignment.assignment_id == assignment_id,
            OnboardingAssignment.tenant_id == self.tenant_id,
        ]
        if employee_id is not None:
            conditions.append(OnboardingAssignment.employee_id == employee_id)

        result = await self.db.execute(
            select(OnboardingStepAssignment)
            .join(OnboardingAssignment, OnboardingStepAssignment.assignment_id == OnboardingAssignment.id)
            .where(*conditions)
        )
        step = result.scalar_one_or_none()
        if not step:
            return {"error": "Step not found.", "error_ar": "الخطوة غير موجودة."}

        if step.status == OnboardingStepStatus.completed:
            return {"status": "already_completed", "step_id": str(step_id)}

        step.status = OnboardingStepStatus.completed
        step.completed_at = datetime.now(timezone.utc)
        step.completed_by = completed_by

        await self.db.flush()

        # Check if all required steps are done -> mark assignment completed
        all_steps = await self.db.execute(
            select(OnboardingStepAssignment)
            .join(OnboardingTemplateStep, OnboardingStepAssignment.template_step_id == OnboardingTemplateStep.id)
            .where(
                OnboardingStepAssignment.assignment_id == assignment_id,
                OnboardingTemplateStep.is_required.is_(True),
            )
        )
        required_steps = all_steps.scalars().all()
        all_done = all(
            s.status in (OnboardingStepStatus.completed, OnboardingStepStatus.skipped)
            for s in required_steps
        )

        if all_done:
            assign_result = await self.db.execute(
                select(OnboardingAssignment).where(OnboardingAssignment.id == assignment_id)
            )
            assignment = assign_result.scalar_one()
            assignment.status = OnboardingAssignmentStatus.completed
            assignment.completed_at = datetime.now(timezone.utc)

        await self.db.commit()
        return {"status": "completed", "step_id": str(step_id), "all_done": all_done}

    async def get_onboarding_dashboard(
        self, requesting_employee_id: uuid.UUID | None = None,
    ) -> list[dict]:
        """HR dashboard: in-progress onboarding assignments with progress.

        When requesting_employee_id is provided, results are scoped to
        the requester's own assignment plus assignments of their direct reports.
        """
        query = (
            select(OnboardingAssignment, Employee)
            .join(Employee, OnboardingAssignment.employee_id == Employee.id)
            .where(
                OnboardingAssignment.tenant_id == self.tenant_id,
                OnboardingAssignment.status == OnboardingAssignmentStatus.in_progress,
            )
            .options(selectinload(OnboardingAssignment.step_statuses))
            .order_by(OnboardingAssignment.started_at.desc())
        )
        if requesting_employee_id is not None:
            # Scope to own data + direct reports

            query = query.where(
                or_(
                    OnboardingAssignment.employee_id == requesting_employee_id,
                    Employee.manager_id == requesting_employee_id,
                )
            )
        result = await self.db.execute(query)
        rows = result.all()
        now = datetime.now(timezone.utc)

        items = []
        for assignment, emp in rows:
            total = len(assignment.step_statuses)
            completed = sum(
                1 for s in assignment.step_statuses
                if s.status == OnboardingStepStatus.completed
            )
            overdue = sum(
                1 for s in assignment.step_statuses
                if s.status in (OnboardingStepStatus.pending, OnboardingStepStatus.in_progress)
                and s.due_date and now > s.due_date
            )
            items.append({
                "assignment_id": str(assignment.id),
                "employee_id": str(emp.id),
                "employee_name": emp.full_name,
                "employee_name_ar": f"{emp.first_name_ar or ''} {emp.last_name_ar or ''}".strip(),
                "hire_date": emp.hire_date.isoformat() if emp.hire_date else None,
                "progress_pct": round((completed / total * 100) if total > 0 else 0),
                "completed_steps": completed,
                "total_steps": total,
                "overdue_steps": overdue,
                "started_at": assignment.started_at.isoformat(),
            })

        return items

    async def get_overdue_steps(
        self, requesting_employee_id: uuid.UUID | None = None,
    ) -> list[dict]:
        """Find overdue onboarding steps.

        When requesting_employee_id is provided, results are scoped to
        the requester's own steps plus steps of their direct reports.
        """
        now = datetime.now(timezone.utc)
        conditions = [
            OnboardingAssignment.tenant_id == self.tenant_id,
            OnboardingAssignment.status == OnboardingAssignmentStatus.in_progress,
            OnboardingStepAssignment.status.in_([
                OnboardingStepStatus.pending, OnboardingStepStatus.in_progress
            ]),
            OnboardingStepAssignment.due_date < now,
        ]
        if requesting_employee_id is not None:

            conditions.append(
                or_(
                    OnboardingAssignment.employee_id == requesting_employee_id,
                    Employee.manager_id == requesting_employee_id,
                )
            )
        result = await self.db.execute(
            select(OnboardingStepAssignment, OnboardingAssignment, Employee, OnboardingTemplateStep)
            .join(OnboardingAssignment, OnboardingStepAssignment.assignment_id == OnboardingAssignment.id)
            .join(Employee, OnboardingAssignment.employee_id == Employee.id)
            .join(OnboardingTemplateStep, OnboardingStepAssignment.template_step_id == OnboardingTemplateStep.id)
            .where(*conditions)
        )
        rows = result.all()
        return [
            {
                "employee_id": str(emp.id),
                "employee_name": emp.full_name,
                "step_name": tpl_step.name,
                "step_name_ar": tpl_step.name_ar,
                "due_date": step.due_date.isoformat() if step.due_date else None,
                "days_overdue": (now - step.due_date).days if step.due_date else 0,
            }
            for step, assignment, emp, tpl_step in rows
        ]
