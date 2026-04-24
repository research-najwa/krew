I now have a thorough understanding of the entire codebase. Let me produce the complete technical design.

---

# Technical Design: Sprint 2 Batch C -- Reporting, Nitaqat, Onboarding, Employee Ticket Tracking

## File Structure (New Files)

```
backend/app/
  models/
    nitaqat.py              # C2: NitaqatConfig model
    onboarding.py           # C3: OnboardingTemplate, OnboardingStep, OnboardingAssignment models
  services/
    reporting.py            # C1: ReportingService (all report queries + caching)
    nitaqat.py              # C2: NitaqatService (calculator, simulator, alerts)
    onboarding.py           # C3: OnboardingService (template CRUD, assignment lifecycle, overdue checks)
  api/
    reports.py              # C1: All reporting endpoints
    nitaqat.py              # C2: Nitaqat dashboard + simulation endpoints
    onboarding.py           # C3: Onboarding admin endpoints
```

Modified files:
- `/backend/app/models/__init__.py` -- register new models
- `/backend/app/main.py` -- include new routers
- `/backend/app/agents/deema.py` -- add C4 tools (list_my_escalations, list_my_leave_requests) + proactive context
- `/backend/app/agents/base.py` -- add optional `get_proactive_context` hook
- `/backend/app/agents/waleed.py` -- wire to real onboarding data
- `/backend/app/models/notification.py` -- add `onboarding` to NotificationCategory
- `/backend/app/agents/orchestrator.py` -- add onboarding keywords to Waleed routing

---

## C1: HR Reporting Dashboard API

### 1. Data Models

No new tables needed. All reports are aggregation queries over existing tables: `employees`, `leave_requests`, `leave_balances`, `conversations`, `messages`, `escalation_tickets`, `departments`.

### 2. Service Layer: ReportingService

```python
# /backend/app/services/reporting.py
"""Reporting service — aggregated queries for HR dashboards with Redis caching."""
import json
import hashlib
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, func, case, and_, extract
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee, EmployeeStatus, Department
from app.models.leave import LeaveRequest, LeaveBalance, LeaveType, LeaveStatus
from app.models.conversation import Conversation, Message, ConversationStatus
from app.models.escalation import EscalationTicket, EscalationStatus, EscalationCategory, EscalationUrgency

logger = logging.getLogger(__name__)

# In-memory fallback cache: {cache_key: (expiry_timestamp, data)}
_memory_cache: dict[str, tuple[float, Any]] = {}
CACHE_TTL_SECONDS = 300  # 5 minutes


async def _get_redis():
    """Try to get Redis connection, return None if unavailable."""
    try:
        from app.security.rate_limiter import get_redis
        return await get_redis()
    except Exception:
        return None


async def _cache_get(key: str) -> Any | None:
    """Read from Redis, fall back to in-memory."""
    redis = await _get_redis()
    if redis:
        try:
            val = await redis.get(key)
            if val:
                return json.loads(val)
        except Exception:
            pass
    # In-memory fallback
    if key in _memory_cache:
        expiry, data = _memory_cache[key]
        if datetime.now(timezone.utc).timestamp() < expiry:
            return data
        else:
            del _memory_cache[key]
    return None


async def _cache_set(key: str, data: Any, ttl: int = CACHE_TTL_SECONDS) -> None:
    """Write to Redis, fall back to in-memory."""
    redis = await _get_redis()
    if redis:
        try:
            await redis.set(key, json.dumps(data, default=str), ex=ttl)
            return
        except Exception:
            pass
    # In-memory fallback
    expiry = datetime.now(timezone.utc).timestamp() + ttl
    _memory_cache[key] = (expiry, data)


def _cache_key(tenant_id: uuid.UUID, report: str, **params) -> str:
    """Build a deterministic cache key."""
    param_str = json.dumps(params, sort_keys=True, default=str)
    h = hashlib.md5(param_str.encode()).hexdigest()[:12]
    return f"report:{tenant_id}:{report}:{h}"


class ReportingService:
    """Aggregated reporting queries, all tenant-scoped."""

    def __init__(self, db: AsyncSession, tenant_id: uuid.UUID):
        self.db = db
        self.tenant_id = tenant_id

    # ── C1-a: Leave Utilization Report ──────────────────────────

    async def leave_utilization(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
        department_id: uuid.UUID | None = None,
    ) -> dict:
        cache_key = _cache_key(
            self.tenant_id, "leave_util",
            start=start_date, end=end_date, dept=department_id,
        )
        cached = await _cache_get(cache_key)
        if cached:
            return cached

        # Default to current year
        if not start_date:
            start_date = date(date.today().year, 1, 1)
        if not end_date:
            end_date = date.today()

        # Base filter: tenant-scoped, within date range, approved/pending
        base_filter = [
            Employee.tenant_id == self.tenant_id,
            LeaveRequest.start_date >= start_date,
            LeaveRequest.start_date <= end_date,
            LeaveRequest.status.in_([LeaveStatus.approved, LeaveStatus.pending]),
        ]
        if department_id:
            base_filter.append(Employee.department_id == department_id)

        # Usage by type
        by_type = await self.db.execute(
            select(
                LeaveRequest.leave_type,
                func.count(LeaveRequest.id).label("request_count"),
                func.coalesce(func.sum(LeaveRequest.business_days), 0).label("total_days"),
            )
            .join(Employee, LeaveRequest.employee_id == Employee.id)
            .where(*base_filter)
            .group_by(LeaveRequest.leave_type)
        )

        # Usage by month
        by_month = await self.db.execute(
            select(
                extract("year", LeaveRequest.start_date).label("year"),
                extract("month", LeaveRequest.start_date).label("month"),
                func.count(LeaveRequest.id).label("request_count"),
                func.coalesce(func.sum(LeaveRequest.business_days), 0).label("total_days"),
            )
            .join(Employee, LeaveRequest.employee_id == Employee.id)
            .where(*base_filter)
            .group_by("year", "month")
            .order_by("year", "month")
        )

        # Usage by department
        by_dept = await self.db.execute(
            select(
                Department.id,
                Department.name,
                Department.name_ar,
                func.count(LeaveRequest.id).label("request_count"),
                func.coalesce(func.sum(LeaveRequest.business_days), 0).label("total_days"),
            )
            .join(Employee, LeaveRequest.employee_id == Employee.id)
            .join(Department, Employee.department_id == Department.id)
            .where(*base_filter)
            .group_by(Department.id, Department.name, Department.name_ar)
        )

        # Top leave takers (top 10)
        top_takers = await self.db.execute(
            select(
                Employee.id,
                Employee.first_name,
                Employee.last_name,
                Employee.first_name_ar,
                Employee.last_name_ar,
                func.coalesce(func.sum(LeaveRequest.business_days), 0).label("total_days"),
            )
            .join(LeaveRequest, LeaveRequest.employee_id == Employee.id)
            .where(*base_filter)
            .group_by(Employee.id, Employee.first_name, Employee.last_name,
                       Employee.first_name_ar, Employee.last_name_ar)
            .order_by(func.sum(LeaveRequest.business_days).desc())
            .limit(10)
        )

        # Remaining balances summary (current year)
        year = date.today().year
        balance_filter = [Employee.tenant_id == self.tenant_id]
        if department_id:
            balance_filter.append(Employee.department_id == department_id)

        balances = await self.db.execute(
            select(
                LeaveBalance.leave_type,
                func.sum(LeaveBalance.total_days).label("total_entitled"),
                func.sum(LeaveBalance.used_days).label("total_used"),
                func.sum(LeaveBalance.total_days - LeaveBalance.used_days).label("total_remaining"),
            )
            .join(Employee, LeaveBalance.employee_id == Employee.id)
            .where(*balance_filter, LeaveBalance.year == year)
            .group_by(LeaveBalance.leave_type)
        )

        result = {
            "period": {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
            "by_type": [
                {"leave_type": r.leave_type.value, "request_count": r.request_count,
                 "total_days": int(r.total_days)}
                for r in by_type
            ],
            "by_month": [
                {"year": int(r.year), "month": int(r.month),
                 "request_count": r.request_count, "total_days": int(r.total_days)}
                for r in by_month
            ],
            "by_department": [
                {"department_id": str(r.id), "name": r.name, "name_ar": r.name_ar,
                 "request_count": r.request_count, "total_days": int(r.total_days)}
                for r in by_dept
            ],
            "top_leave_takers": [
                {"employee_id": str(r.id), "name": f"{r.first_name} {r.last_name}",
                 "name_ar": f"{r.first_name_ar or ''} {r.last_name_ar or ''}".strip(),
                 "total_days": int(r.total_days)}
                for r in top_takers
            ],
            "balance_summary": [
                {"leave_type": r.leave_type.value, "total_entitled": int(r.total_entitled),
                 "total_used": int(r.total_used), "total_remaining": int(r.total_remaining)}
                for r in balances
            ],
        }

        await _cache_set(cache_key, result)
        return result

    # ── C1-b: Agent Performance Report ──────────────────────────

    async def agent_performance(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict:
        cache_key = _cache_key(self.tenant_id, "agent_perf", start=start_date, end=end_date)
        cached = await _cache_get(cache_key)
        if cached:
            return cached

        if not start_date:
            start_date = date.today() - timedelta(days=30)
        if not end_date:
            end_date = date.today()

        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())

        # Messages per agent
        msgs_per_agent = await self.db.execute(
            select(
                Conversation.agent_name,
                func.count(Message.id).label("message_count"),
            )
            .join(Message, Message.conversation_id == Conversation.id)
            .where(
                Conversation.tenant_id == self.tenant_id,
                Message.role == "agent",
                Message.created_at >= start_dt,
                Message.created_at <= end_dt,
            )
            .group_by(Conversation.agent_name)
        )

        # Conversations per agent with resolution stats
        conv_stats = await self.db.execute(
            select(
                Conversation.agent_name,
                func.count(Conversation.id).label("total_conversations"),
                func.sum(case(
                    (Conversation.status == ConversationStatus.resolved, 1), else_=0
                )).label("resolved_count"),
                func.sum(case(
                    (Conversation.resolved_automatically == True, 1), else_=0
                )).label("auto_resolved_count"),
                func.sum(case(
                    (Conversation.status == ConversationStatus.escalated, 1), else_=0
                )).label("escalated_count"),
                func.avg(Conversation.satisfaction_score).label("avg_satisfaction"),
            )
            .where(
                Conversation.tenant_id == self.tenant_id,
                Conversation.started_at >= start_dt,
                Conversation.started_at <= end_dt,
            )
            .group_by(Conversation.agent_name)
        )

        msgs_map = {r.agent_name: r.message_count for r in msgs_per_agent}

        agents = []
        for r in conv_stats:
            total = r.total_conversations or 0
            resolved = r.resolved_count or 0
            escalated = r.escalated_count or 0
            agents.append({
                "agent_name": r.agent_name,
                "total_conversations": total,
                "messages_handled": msgs_map.get(r.agent_name, 0),
                "resolved_count": resolved,
                "auto_resolved_count": r.auto_resolved_count or 0,
                "escalated_count": escalated,
                "resolution_rate": round((resolved / total * 100) if total > 0 else 0, 1),
                "escalation_rate": round((escalated / total * 100) if total > 0 else 0, 1),
                "avg_satisfaction": round(float(r.avg_satisfaction), 2) if r.avg_satisfaction else None,
            })

        result = {
            "period": {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
            "agents": agents,
        }
        await _cache_set(cache_key, result)
        return result

    # ── C1-c: Escalation Report ─────────────────────────────────

    async def escalation_report(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict:
        cache_key = _cache_key(self.tenant_id, "escalation", start=start_date, end=end_date)
        cached = await _cache_get(cache_key)
        if cached:
            return cached

        if not start_date:
            start_date = date.today() - timedelta(days=30)
        if not end_date:
            end_date = date.today()

        start_dt = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        end_dt = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=timezone.utc)

        base = [
            EscalationTicket.tenant_id == self.tenant_id,
            EscalationTicket.created_at >= start_dt,
            EscalationTicket.created_at <= end_dt,
        ]

        # Counts by status
        by_status = await self.db.execute(
            select(
                EscalationTicket.status,
                func.count(EscalationTicket.id).label("count"),
            ).where(*base).group_by(EscalationTicket.status)
        )

        # Counts by category
        by_category = await self.db.execute(
            select(
                EscalationTicket.category,
                func.count(EscalationTicket.id).label("count"),
            ).where(*base).group_by(EscalationTicket.category)
        )

        # Counts by urgency
        by_urgency = await self.db.execute(
            select(
                EscalationTicket.urgency,
                func.count(EscalationTicket.id).label("count"),
            ).where(*base).group_by(EscalationTicket.urgency)
        )

        # Avg resolution time (resolved tickets only)
        avg_resolution = await self.db.execute(
            select(
                func.avg(
                    extract("epoch", EscalationTicket.resolved_at) -
                    extract("epoch", EscalationTicket.created_at)
                ).label("avg_seconds")
            ).where(
                *base,
                EscalationTicket.status == EscalationStatus.resolved,
                EscalationTicket.resolved_at.isnot(None),
            )
        )
        avg_res_seconds = avg_resolution.scalar_one()

        result = {
            "period": {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
            "by_status": [
                {"status": r.status.value, "count": r.count} for r in by_status
            ],
            "by_category": [
                {"category": r.category.value, "count": r.count} for r in by_category
            ],
            "by_urgency": [
                {"urgency": r.urgency.value, "count": r.count} for r in by_urgency
            ],
            "avg_resolution_time_hours": round(avg_res_seconds / 3600, 1) if avg_res_seconds else None,
        }
        await _cache_set(cache_key, result)
        return result

    # ── C1-d: Headcount Report ──────────────────────────────────

    async def headcount_report(
        self,
        department_id: uuid.UUID | None = None,
    ) -> dict:
        cache_key = _cache_key(self.tenant_id, "headcount", dept=department_id)
        cached = await _cache_get(cache_key)
        if cached:
            return cached

        base = [Employee.tenant_id == self.tenant_id]
        if department_id:
            base.append(Employee.department_id == department_id)

        # By status
        by_status = await self.db.execute(
            select(
                Employee.status,
                func.count(Employee.id).label("count"),
            ).where(*base).group_by(Employee.status)
        )

        # By nationality (Saudi / non-Saudi) among active
        by_nationality = await self.db.execute(
            select(
                Employee.is_saudi,
                func.count(Employee.id).label("count"),
            ).where(*base, Employee.status == EmployeeStatus.active)
            .group_by(Employee.is_saudi)
        )

        # By department (active only)
        by_dept = await self.db.execute(
            select(
                Department.id,
                Department.name,
                Department.name_ar,
                func.count(Employee.id).label("count"),
            )
            .join(Department, Employee.department_id == Department.id)
            .where(*base, Employee.status == EmployeeStatus.active)
            .group_by(Department.id, Department.name, Department.name_ar)
        )

        # New hires by month (last 12 months)
        twelve_months_ago = date.today() - timedelta(days=365)
        new_hires = await self.db.execute(
            select(
                extract("year", Employee.hire_date).label("year"),
                extract("month", Employee.hire_date).label("month"),
                func.count(Employee.id).label("count"),
            )
            .where(*base, Employee.hire_date >= twelve_months_ago)
            .group_by("year", "month")
            .order_by("year", "month")
        )

        # Terminations by month (last 12 months)
        terminations = await self.db.execute(
            select(
                extract("year", Employee.end_date).label("year"),
                extract("month", Employee.end_date).label("month"),
                func.count(Employee.id).label("count"),
            )
            .where(
                *base,
                Employee.status == EmployeeStatus.terminated,
                Employee.end_date >= twelve_months_ago,
                Employee.end_date.isnot(None),
            )
            .group_by("year", "month")
            .order_by("year", "month")
        )

        # By gender (active)
        by_gender = await self.db.execute(
            select(
                Employee.gender,
                func.count(Employee.id).label("count"),
            ).where(*base, Employee.status == EmployeeStatus.active)
            .group_by(Employee.gender)
        )

        result = {
            "by_status": [
                {"status": r.status.value, "count": r.count} for r in by_status
            ],
            "by_nationality": [
                {"is_saudi": r.is_saudi, "count": r.count} for r in by_nationality
            ],
            "by_department": [
                {"department_id": str(r.id), "name": r.name, "name_ar": r.name_ar, "count": r.count}
                for r in by_dept
            ],
            "by_gender": [
                {"gender": r.gender.value if r.gender else "unspecified", "count": r.count}
                for r in by_gender
            ],
            "new_hires_by_month": [
                {"year": int(r.year), "month": int(r.month), "count": r.count}
                for r in new_hires
            ],
            "terminations_by_month": [
                {"year": int(r.year), "month": int(r.month), "count": r.count}
                for r in terminations
            ],
        }
        await _cache_set(cache_key, result)
        return result

    # ── C1-e: Attendance Summary (who is on leave) ──────────────

    async def attendance_summary(
        self,
        department_id: uuid.UUID | None = None,
    ) -> dict:
        cache_key = _cache_key(self.tenant_id, "attendance", dept=department_id)
        cached = await _cache_get(cache_key)
        if cached:
            return cached

        today = date.today()
        week_end = today + timedelta(days=(3 - today.weekday()) % 7)  # Thursday
        if week_end < today:
            week_end += timedelta(days=7)

        base = [
            Employee.tenant_id == self.tenant_id,
            LeaveRequest.status == LeaveStatus.approved,
        ]
        if department_id:
            base.append(Employee.department_id == department_id)

        # On leave today
        on_leave_today = await self.db.execute(
            select(
                Employee.id, Employee.first_name, Employee.last_name,
                Employee.first_name_ar, Employee.last_name_ar,
                LeaveRequest.leave_type, LeaveRequest.start_date, LeaveRequest.end_date,
            )
            .join(LeaveRequest, LeaveRequest.employee_id == Employee.id)
            .where(*base, LeaveRequest.start_date <= today, LeaveRequest.end_date >= today)
        )

        # On leave this week
        on_leave_week = await self.db.execute(
            select(
                Employee.id, Employee.first_name, Employee.last_name,
                Employee.first_name_ar, Employee.last_name_ar,
                LeaveRequest.leave_type, LeaveRequest.start_date, LeaveRequest.end_date,
            )
            .join(LeaveRequest, LeaveRequest.employee_id == Employee.id)
            .where(*base, LeaveRequest.start_date <= week_end, LeaveRequest.end_date >= today)
        )

        # Upcoming leaves (next 14 days, not yet started)
        upcoming_end = today + timedelta(days=14)
        upcoming = await self.db.execute(
            select(
                Employee.id, Employee.first_name, Employee.last_name,
                Employee.first_name_ar, Employee.last_name_ar,
                LeaveRequest.leave_type, LeaveRequest.start_date, LeaveRequest.end_date,
                LeaveRequest.business_days,
            )
            .join(LeaveRequest, LeaveRequest.employee_id == Employee.id)
            .where(*base, LeaveRequest.start_date > today, LeaveRequest.start_date <= upcoming_end)
            .order_by(LeaveRequest.start_date)
        )

        def _fmt(r):
            return {
                "employee_id": str(r.id),
                "name": f"{r.first_name} {r.last_name}",
                "name_ar": f"{r.first_name_ar or ''} {r.last_name_ar or ''}".strip(),
                "leave_type": r.leave_type.value,
                "start_date": r.start_date.isoformat(),
                "end_date": r.end_date.isoformat(),
            }

        result = {
            "date": today.isoformat(),
            "on_leave_today": [_fmt(r) for r in on_leave_today],
            "on_leave_today_count": len(list(on_leave_today.mappings())),
            "on_leave_this_week": [_fmt(r) for r in on_leave_week],
            "upcoming_leaves": [
                {**_fmt(r), "business_days": r.business_days} for r in upcoming
            ],
        }
        await _cache_set(cache_key, result)
        return result
```

### 3. API Endpoints

```python
# /backend/app/api/reports.py
"""Reporting API — HR manager dashboard reports."""
from uuid import UUID
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.admin_user import AdminUser, AdminRole
from app.auth.dependencies import require_role, require_tenant
from app.services.reporting import ReportingService

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/leave-utilization")
async def leave_utilization_report(
    start_date: date | None = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: date | None = Query(None, description="End date (YYYY-MM-DD)"),
    department_id: UUID | None = Query(None),
    current_user: AdminUser = Depends(require_role(AdminRole.hr_manager)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Leave usage by type, department, and month. Top leave takers. Balance summary."""
    svc = ReportingService(db, tenant_id)
    return await svc.leave_utilization(start_date, end_date, department_id)


@router.get("/agent-performance")
async def agent_performance_report(
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    current_user: AdminUser = Depends(require_role(AdminRole.hr_manager)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Agent messages, resolution rate, escalation rate, satisfaction scores."""
    svc = ReportingService(db, tenant_id)
    return await svc.agent_performance(start_date, end_date)


@router.get("/escalations")
async def escalation_report(
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    current_user: AdminUser = Depends(require_role(AdminRole.hr_manager)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Escalation counts by status, category, urgency. Avg resolution time."""
    svc = ReportingService(db, tenant_id)
    return await svc.escalation_report(start_date, end_date)


@router.get("/headcount")
async def headcount_report(
    department_id: UUID | None = Query(None),
    current_user: AdminUser = Depends(require_role(AdminRole.hr_manager)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Headcount by status, nationality, department, gender. Hire/termination trends."""
    svc = ReportingService(db, tenant_id)
    return await svc.headcount_report(department_id)


@router.get("/attendance")
async def attendance_summary(
    department_id: UUID | None = Query(None),
    current_user: AdminUser = Depends(require_role(AdminRole.hr_manager)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Who is on leave today, this week, and upcoming."""
    svc = ReportingService(db, tenant_id)
    return await svc.attendance_summary(department_id)
```

### API Contract Table (C1)

| Method | Path | Query Params | Response | Auth |
|--------|------|-------------|----------|------|
| GET | `/api/v1/reports/leave-utilization` | `start_date`, `end_date`, `department_id` | `{period, by_type[], by_month[], by_department[], top_leave_takers[], balance_summary[]}` | hr_manager+ |
| GET | `/api/v1/reports/agent-performance` | `start_date`, `end_date` | `{period, agents[{agent_name, total_conversations, messages_handled, resolution_rate, escalation_rate, avg_satisfaction}]}` | hr_manager+ |
| GET | `/api/v1/reports/escalations` | `start_date`, `end_date` | `{period, by_status[], by_category[], by_urgency[], avg_resolution_time_hours}` | hr_manager+ |
| GET | `/api/v1/reports/headcount` | `department_id` | `{by_status[], by_nationality[], by_department[], by_gender[], new_hires_by_month[], terminations_by_month[]}` | hr_manager+ |
| GET | `/api/v1/reports/attendance` | `department_id` | `{date, on_leave_today[], on_leave_today_count, on_leave_this_week[], upcoming_leaves[]}` | hr_manager+ |

---

## C2: Nitaqat/Saudization Compliance

### 1. Data Model

```python
# /backend/app/models/nitaqat.py
"""Nitaqat configuration — per-tenant Saudization thresholds and tracking."""
import uuid
import enum
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Integer, Float, ForeignKey, Boolean, UniqueConstraint, Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class NitaqatBand(str, enum.Enum):
    platinum = "platinum"
    green_high = "green_high"
    green_low = "green_low"
    yellow = "yellow"
    red = "red"


class CompanySizeCategory(str, enum.Enum):
    micro = "micro"        # 1-5
    small = "small"        # 6-49
    medium = "medium"      # 50-499
    large = "large"        # 500-2999
    giant = "giant"        # 3000+


class NitaqatConfig(Base):
    """Per-tenant Nitaqat configuration.

    Stores the tenant's industry, size category, and custom band thresholds.
    One row per tenant — upserted on first configuration.
    """
    __tablename__ = "nitaqat_configs"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_nitaqat_config_tenant"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))

    # Company classification
    industry: Mapped[str] = mapped_column(String(255), default="general")
    industry_ar: Mapped[str | None] = mapped_column(String(255), nullable=True)
    size_category: Mapped[CompanySizeCategory] = mapped_column(
        SAEnum(CompanySizeCategory), default=CompanySizeCategory.small
    )

    # Thresholds (percentages) — configurable per tenant
    # Default simplified thresholds; real ones vary by industry/size
    platinum_threshold: Mapped[float] = mapped_column(Float, default=40.0)
    green_high_threshold: Mapped[float] = mapped_column(Float, default=26.0)
    green_low_threshold: Mapped[float] = mapped_column(Float, default=17.0)
    yellow_threshold: Mapped[float] = mapped_column(Float, default=6.0)
    # Below yellow_threshold = Red

    # Target ratio — what the company is aiming for (can differ from band minimum)
    target_saudization_pct: Mapped[float] = mapped_column(Float, default=26.0)

    # Alert thresholds
    alert_when_below_target: Mapped[bool] = mapped_column(Boolean, default=True)
    alert_buffer_pct: Mapped[float] = mapped_column(Float, default=2.0)
    # Alert when ratio drops within buffer_pct of the next lower band boundary

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    tenant = relationship("Tenant")
```

### 2. Service Layer

```python
# /backend/app/services/nitaqat.py
"""Nitaqat/Saudization compliance service."""
import uuid
import logging
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee, EmployeeStatus
from app.models.nitaqat import NitaqatConfig, NitaqatBand

logger = logging.getLogger(__name__)

# Default thresholds when no NitaqatConfig exists
_DEFAULT_THRESHOLDS = {
    "platinum": 40.0,
    "green_high": 26.0,
    "green_low": 17.0,
    "yellow": 6.0,
}


class NitaqatService:
    """Nitaqat band calculation, gap analysis, and what-if simulation."""

    def __init__(self, db: AsyncSession, tenant_id: uuid.UUID):
        self.db = db
        self.tenant_id = tenant_id

    async def _get_config(self) -> NitaqatConfig | None:
        result = await self.db.execute(
            select(NitaqatConfig).where(NitaqatConfig.tenant_id == self.tenant_id)
        )
        return result.scalar_one_or_none()

    async def _get_headcount(self) -> tuple[int, int]:
        """Returns (total_active, saudi_active)."""
        total = (await self.db.execute(
            select(func.count(Employee.id)).where(
                Employee.tenant_id == self.tenant_id,
                Employee.status == EmployeeStatus.active,
            )
        )).scalar_one()

        saudi = (await self.db.execute(
            select(func.count(Employee.id)).where(
                Employee.tenant_id == self.tenant_id,
                Employee.status == EmployeeStatus.active,
                Employee.is_saudi == True,
            )
        )).scalar_one()

        return total, saudi

    def _calculate_band(
        self, ratio: float, config: NitaqatConfig | None
    ) -> NitaqatBand:
        if config:
            thresholds = {
                "platinum": config.platinum_threshold,
                "green_high": config.green_high_threshold,
                "green_low": config.green_low_threshold,
                "yellow": config.yellow_threshold,
            }
        else:
            thresholds = _DEFAULT_THRESHOLDS

        if ratio >= thresholds["platinum"]:
            return NitaqatBand.platinum
        elif ratio >= thresholds["green_high"]:
            return NitaqatBand.green_high
        elif ratio >= thresholds["green_low"]:
            return NitaqatBand.green_low
        elif ratio >= thresholds["yellow"]:
            return NitaqatBand.yellow
        else:
            return NitaqatBand.red

    def _gap_analysis(
        self, total: int, saudi: int, config: NitaqatConfig | None
    ) -> dict:
        """How many Saudis needed to reach target / next band."""
        target_pct = config.target_saudization_pct if config else 26.0
        ratio = (saudi / total * 100) if total > 0 else 0

        # Saudis needed for target
        if total > 0:
            needed_for_target = max(0, int((target_pct / 100 * total) - saudi + 0.999))
        else:
            needed_for_target = 0

        # Current band and next band up
        band = self._calculate_band(ratio, config)
        thresholds = (
            {
                NitaqatBand.red: config.yellow_threshold if config else 6.0,
                NitaqatBand.yellow: config.green_low_threshold if config else 17.0,
                NitaqatBand.green_low: config.green_high_threshold if config else 26.0,
                NitaqatBand.green_high: config.platinum_threshold if config else 40.0,
                NitaqatBand.platinum: None,
            }
        )
        next_threshold = thresholds.get(band)
        needed_for_next_band = 0
        if next_threshold and total > 0:
            needed_for_next_band = max(0, int((next_threshold / 100 * total) - saudi + 0.999))

        return {
            "saudis_needed_for_target": needed_for_target,
            "target_pct": target_pct,
            "saudis_needed_for_next_band": needed_for_next_band,
            "next_band": band.value if band == NitaqatBand.platinum else thresholds.get(band),
        }

    async def get_current_status(self) -> dict:
        """Full Nitaqat status: ratio, band, gap analysis."""
        config = await self._get_config()
        total, saudi = await self._get_headcount()
        ratio = round((saudi / total * 100) if total > 0 else 0, 2)
        band = self._calculate_band(ratio, config)
        gap = self._gap_analysis(total, saudi, config)

        return {
            "total_employees": total,
            "saudi_employees": saudi,
            "non_saudi_employees": total - saudi,
            "saudization_ratio": ratio,
            "current_band": band.value,
            "gap_analysis": gap,
            "config": {
                "industry": config.industry if config else "general",
                "size_category": config.size_category.value if config else "small",
                "target_pct": config.target_saudization_pct if config else 26.0,
                "platinum_threshold": config.platinum_threshold if config else 40.0,
                "green_high_threshold": config.green_high_threshold if config else 26.0,
                "green_low_threshold": config.green_low_threshold if config else 17.0,
                "yellow_threshold": config.yellow_threshold if config else 6.0,
            },
        }

    async def simulate(
        self,
        hire_saudi: int = 0,
        hire_non_saudi: int = 0,
        terminate_saudi: int = 0,
        terminate_non_saudi: int = 0,
    ) -> dict:
        """What-if simulation: project new ratio and band after hypothetical changes."""
        config = await self._get_config()
        total, saudi = await self._get_headcount()

        new_saudi = saudi + hire_saudi - terminate_saudi
        new_total = total + hire_saudi + hire_non_saudi - terminate_saudi - terminate_non_saudi

        if new_saudi < 0:
            new_saudi = 0
        if new_total < 0:
            new_total = 0

        current_ratio = round((saudi / total * 100) if total > 0 else 0, 2)
        new_ratio = round((new_saudi / new_total * 100) if new_total > 0 else 0, 2)

        current_band = self._calculate_band(current_ratio, config)
        new_band = self._calculate_band(new_ratio, config)

        band_order = [NitaqatBand.red, NitaqatBand.yellow, NitaqatBand.green_low,
                       NitaqatBand.green_high, NitaqatBand.platinum]
        band_change = "unchanged"
        if band_order.index(new_band) > band_order.index(current_band):
            band_change = "improved"
        elif band_order.index(new_band) < band_order.index(current_band):
            band_change = "degraded"

        return {
            "current": {
                "total": total, "saudi": saudi, "ratio": current_ratio,
                "band": current_band.value,
            },
            "simulated": {
                "total": new_total, "saudi": new_saudi, "ratio": new_ratio,
                "band": new_band.value,
            },
            "changes": {
                "hire_saudi": hire_saudi, "hire_non_saudi": hire_non_saudi,
                "terminate_saudi": terminate_saudi, "terminate_non_saudi": terminate_non_saudi,
            },
            "band_change": band_change,
            "gap_analysis": self._gap_analysis(new_total, new_saudi, config),
        }

    async def check_termination_impact(self, employee_id: uuid.UUID) -> dict:
        """Check if terminating a specific employee would cause a band drop.

        Called as an integration point when employee status changes.
        """
        config = await self._get_config()
        total, saudi = await self._get_headcount()

        # Look up the employee
        result = await self.db.execute(
            select(Employee).where(
                Employee.id == employee_id,
                Employee.tenant_id == self.tenant_id,
            )
        )
        emp = result.scalar_one_or_none()
        if not emp:
            return {"warning": False, "reason": "Employee not found"}

        new_total = total - 1
        new_saudi = saudi - 1 if emp.is_saudi else saudi

        current_ratio = (saudi / total * 100) if total > 0 else 0
        new_ratio = (new_saudi / new_total * 100) if new_total > 0 else 0

        current_band = self._calculate_band(current_ratio, config)
        new_band = self._calculate_band(new_ratio, config)

        # Check if near target
        target_pct = config.target_saudization_pct if config else 26.0
        buffer = config.alert_buffer_pct if config else 2.0

        warning = False
        reasons = []

        if new_band != current_band:
            warning = True
            reasons.append(
                f"Nitaqat band will drop from {current_band.value} to {new_band.value}"
            )

        if new_ratio < target_pct and current_ratio >= target_pct:
            warning = True
            reasons.append(
                f"Saudization ratio will drop below target ({target_pct}%)"
            )

        if new_ratio < (target_pct - buffer):
            warning = True
            reasons.append(
                f"Saudization ratio will be {buffer}%+ below target"
            )

        return {
            "employee_id": str(employee_id),
            "employee_is_saudi": emp.is_saudi,
            "current_ratio": round(current_ratio, 2),
            "projected_ratio": round(new_ratio, 2),
            "current_band": current_band.value,
            "projected_band": new_band.value,
            "warning": warning,
            "reasons": reasons,
        }
```

### 3. API Endpoints

```python
# /backend/app/api/nitaqat.py
"""Nitaqat/Saudization compliance API."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.admin_user import AdminUser, AdminRole
from app.auth.dependencies import require_role, require_tenant
from app.services.nitaqat import NitaqatService
from app.models.nitaqat import NitaqatConfig, CompanySizeCategory

router = APIRouter(prefix="/nitaqat", tags=["nitaqat"])


class NitaqatConfigUpdate(BaseModel):
    industry: str | None = None
    industry_ar: str | None = None
    size_category: str | None = None
    platinum_threshold: float | None = Field(None, ge=0, le=100)
    green_high_threshold: float | None = Field(None, ge=0, le=100)
    green_low_threshold: float | None = Field(None, ge=0, le=100)
    yellow_threshold: float | None = Field(None, ge=0, le=100)
    target_saudization_pct: float | None = Field(None, ge=0, le=100)
    alert_when_below_target: bool | None = None
    alert_buffer_pct: float | None = Field(None, ge=0, le=50)


class SimulationRequest(BaseModel):
    hire_saudi: int = Field(0, ge=0)
    hire_non_saudi: int = Field(0, ge=0)
    terminate_saudi: int = Field(0, ge=0)
    terminate_non_saudi: int = Field(0, ge=0)


@router.get("/status")
async def get_nitaqat_status(
    current_user: AdminUser = Depends(require_role(AdminRole.hr_manager)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Current Nitaqat status: ratio, band, gap analysis, thresholds."""
    svc = NitaqatService(db, tenant_id)
    return await svc.get_current_status()


@router.post("/simulate")
async def simulate_nitaqat(
    req: SimulationRequest,
    current_user: AdminUser = Depends(require_role(AdminRole.hr_manager)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """What-if simulator: project Nitaqat band after hypothetical hire/terminate changes."""
    svc = NitaqatService(db, tenant_id)
    return await svc.simulate(
        hire_saudi=req.hire_saudi,
        hire_non_saudi=req.hire_non_saudi,
        terminate_saudi=req.terminate_saudi,
        terminate_non_saudi=req.terminate_non_saudi,
    )


@router.get("/termination-impact/{employee_id}")
async def check_termination_impact(
    employee_id: UUID,
    current_user: AdminUser = Depends(require_role(AdminRole.hr_manager)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Check if terminating a specific employee would cause a Nitaqat band drop."""
    svc = NitaqatService(db, tenant_id)
    return await svc.check_termination_impact(employee_id)


@router.put("/config")
async def update_nitaqat_config(
    data: NitaqatConfigUpdate,
    current_user: AdminUser = Depends(require_role(AdminRole.tenant_admin)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    """Create or update Nitaqat configuration for the tenant."""
    from sqlalchemy import select
    result = await db.execute(
        select(NitaqatConfig).where(NitaqatConfig.tenant_id == tenant_id)
    )
    config = result.scalar_one_or_none()

    if not config:
        config = NitaqatConfig(tenant_id=tenant_id)
        db.add(config)

    update_fields = data.model_dump(exclude_unset=True)
    if "size_category" in update_fields and update_fields["size_category"]:
        update_fields["size_category"] = CompanySizeCategory(update_fields["size_category"])

    for field, value in update_fields.items():
        if value is not None:
            setattr(config, field, value)

    await db.commit()
    await db.refresh(config)

    return {
        "status": "updated",
        "config": {
            "industry": config.industry,
            "industry_ar": config.industry_ar,
            "size_category": config.size_category.value,
            "platinum_threshold": config.platinum_threshold,
            "green_high_threshold": config.green_high_threshold,
            "green_low_threshold": config.green_low_threshold,
            "yellow_threshold": config.yellow_threshold,
            "target_saudization_pct": config.target_saudization_pct,
            "alert_when_below_target": config.alert_when_below_target,
            "alert_buffer_pct": config.alert_buffer_pct,
        },
    }
```

### API Contract Table (C2)

| Method | Path | Request | Response | Auth |
|--------|------|---------|----------|------|
| GET | `/api/v1/nitaqat/status` | -- | `{total_employees, saudi_employees, saudization_ratio, current_band, gap_analysis, config}` | hr_manager+ |
| POST | `/api/v1/nitaqat/simulate` | `{hire_saudi, hire_non_saudi, terminate_saudi, terminate_non_saudi}` | `{current, simulated, band_change, gap_analysis}` | hr_manager+ |
| GET | `/api/v1/nitaqat/termination-impact/{employee_id}` | -- | `{warning, reasons[], current_band, projected_band, current_ratio, projected_ratio}` | hr_manager+ |
| PUT | `/api/v1/nitaqat/config` | `NitaqatConfigUpdate` | `{status, config}` | tenant_admin+ |

---

## C3: Onboarding Flow

### 1. Data Models

```python
# /backend/app/models/onboarding.py
"""Onboarding checklist templates and employee assignments."""
import uuid
import enum
from datetime import datetime, timezone

from sqlalchemy import (
    String, DateTime, Integer, Boolean, ForeignKey, Text,
    UniqueConstraint, Index, Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class OnboardingStepType(str, enum.Enum):
    manual = "manual"          # HR marks complete
    automatic = "automatic"    # System detects completion (e.g., policy acknowledged)
    agent_assisted = "agent_assisted"  # Deema/Waleed guides the employee


class OnboardingStepStatus(str, enum.Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    skipped = "skipped"


class OnboardingTemplate(Base):
    """Tenant-configurable onboarding checklist template."""
    __tablename__ = "onboarding_templates"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_onboarding_template_tenant_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    name: Mapped[str] = mapped_column(String(255))
    name_ar: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    # If is_default=True, auto-assigned to new hires when no specific template is specified

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    steps: Mapped[list["OnboardingTemplateStep"]] = relationship(
        back_populates="template", order_by="OnboardingTemplateStep.order"
    )
    tenant = relationship("Tenant")


class OnboardingTemplateStep(Base):
    """A step within an onboarding template (the blueprint)."""
    __tablename__ = "onboarding_template_steps"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    template_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("onboarding_templates.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(500))
    name_ar: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_ar: Mapped[str | None] = mapped_column(Text, nullable=True)
    step_type: Mapped[OnboardingStepType] = mapped_column(
        SAEnum(OnboardingStepType), default=OnboardingStepType.manual
    )
    order: Mapped[int] = mapped_column(Integer)
    due_days_after_hire: Mapped[int] = mapped_column(Integer, default=7)
    # e.g., 3 means due 3 days after hire_date
    is_required: Mapped[bool] = mapped_column(Boolean, default=True)

    # For automatic steps: what triggers completion
    auto_trigger: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # e.g., "policy_acknowledged", "document_uploaded:employment_contract"

    template: Mapped["OnboardingTemplate"] = relationship(back_populates="steps")


class OnboardingAssignment(Base):
    """An onboarding instance assigned to a specific employee."""
    __tablename__ = "onboarding_assignments"
    __table_args__ = (
        UniqueConstraint("employee_id", "template_id", name="uq_onboarding_assignment_emp_template"),
        Index("ix_onboarding_assignment_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id"))
    template_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("onboarding_templates.id"))

    status: Mapped[str] = mapped_column(String(20), default="in_progress")
    # "in_progress", "completed", "cancelled"
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    step_statuses: Mapped[list["OnboardingStepAssignment"]] = relationship(
        back_populates="assignment", order_by="OnboardingStepAssignment.order"
    )
    employee = relationship("Employee")
    template = relationship("OnboardingTemplate")


class OnboardingStepAssignment(Base):
    """Status of a single onboarding step for a specific employee."""
    __tablename__ = "onboarding_step_assignments"
    __table_args__ = (
        UniqueConstraint(
            "assignment_id", "template_step_id",
            name="uq_onboarding_step_assignment_unique"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    assignment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("onboarding_assignments.id", ondelete="CASCADE")
    )
    template_step_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("onboarding_template_steps.id")
    )

    status: Mapped[OnboardingStepStatus] = mapped_column(
        SAEnum(OnboardingStepStatus), default=OnboardingStepStatus.pending
    )
    order: Mapped[int] = mapped_column(Integer)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # "hr:<admin_user_id>", "system:policy_acknowledged", "agent:deema"
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    assignment: Mapped["OnboardingAssignment"] = relationship(back_populates="step_statuses")
    template_step: Mapped["OnboardingTemplateStep"] = relationship()
```

### 2. Service Layer

```python
# /backend/app/services/onboarding.py
"""Onboarding service — template management, assignment lifecycle, overdue detection."""
import uuid
import logging
from datetime import datetime, timedelta, timezone, date

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.employee import Employee
from app.models.onboarding import (
    OnboardingTemplate,
    OnboardingTemplateStep,
    OnboardingAssignment,
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
                    OnboardingTemplate.is_active == True,
                )
                .options(selectinload(OnboardingTemplate.steps))
            )
        else:
            result = await self.db.execute(
                select(OnboardingTemplate)
                .where(
                    OnboardingTemplate.tenant_id == self.tenant_id,
                    OnboardingTemplate.is_default == True,
                    OnboardingTemplate.is_active == True,
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

        # Create assignment
        assignment = OnboardingAssignment(
            tenant_id=self.tenant_id,
            employee_id=employee_id,
            template_id=template.id,
        )
        self.db.add(assignment)
        await self.db.flush()

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
                OnboardingAssignment.status == "in_progress",
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
        self, assignment_id: uuid.UUID, step_id: uuid.UUID, completed_by: str
    ) -> dict:
        """Mark a single onboarding step as completed."""
        result = await self.db.execute(
            select(OnboardingStepAssignment).where(
                OnboardingStepAssignment.id == step_id,
                OnboardingStepAssignment.assignment_id == assignment_id,
            )
        )
        step = result.scalar_one_or_none()
        if not step:
            return {"error": "Step not found."}

        step.status = OnboardingStepStatus.completed
        step.completed_at = datetime.now(timezone.utc)
        step.completed_by = completed_by

        # Check if all required steps are done -> mark assignment completed
        all_steps = await self.db.execute(
            select(OnboardingStepAssignment)
            .join(OnboardingTemplateStep, OnboardingStepAssignment.template_step_id == OnboardingTemplateStep.id)
            .where(
                OnboardingStepAssignment.assignment_id == assignment_id,
                OnboardingTemplateStep.is_required == True,
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
            assignment.status = "completed"
            assignment.completed_at = datetime.now(timezone.utc)

        await self.db.commit()
        return {"status": "completed", "step_id": str(step_id), "all_done": all_done}

    async def get_onboarding_dashboard(self) -> list[dict]:
        """HR dashboard: all in-progress onboarding assignments with progress."""
        result = await self.db.execute(
            select(OnboardingAssignment, Employee)
            .join(Employee, OnboardingAssignment.employee_id == Employee.id)
            .where(
                OnboardingAssignment.tenant_id == self.tenant_id,
                OnboardingAssignment.status == "in_progress",
            )
            .options(selectinload(OnboardingAssignment.step_statuses))
            .order_by(OnboardingAssignment.started_at.desc())
        )
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
                "hire_date": emp.hire_date.isoformat(),
                "progress_pct": round((completed / total * 100) if total > 0 else 0),
                "completed_steps": completed,
                "total_steps": total,
                "overdue_steps": overdue,
                "started_at": assignment.started_at.isoformat(),
            })

        return items

    async def get_overdue_steps(self) -> list[dict]:
        """Find all overdue onboarding steps for notification purposes."""
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(OnboardingStepAssignment, OnboardingAssignment, Employee, OnboardingTemplateStep)
            .join(OnboardingAssignment, OnboardingStepAssignment.assignment_id == OnboardingAssignment.id)
            .join(Employee, OnboardingAssignment.employee_id == Employee.id)
            .join(OnboardingTemplateStep, OnboardingStepAssignment.template_step_id == OnboardingTemplateStep.id)
            .where(
                OnboardingAssignment.tenant_id == self.tenant_id,
                OnboardingAssignment.status == "in_progress",
                OnboardingStepAssignment.status.in_([
                    OnboardingStepStatus.pending, OnboardingStepStatus.in_progress
                ]),
                OnboardingStepAssignment.due_date < now,
            )
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
```

### 3. API Endpoints

```python
# /backend/app/api/onboarding.py
"""Onboarding API — template management and employee onboarding tracking."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.admin_user import AdminUser, AdminRole
from app.auth.dependencies import require_role, require_tenant
from app.services.onboarding import OnboardingService

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


class StepDefinition(BaseModel):
    name: str
    name_ar: str | None = None
    description: str | None = None
    description_ar: str | None = None
    step_type: str = "manual"  # manual, automatic, agent_assisted
    order: int | None = None
    due_days_after_hire: int = 7
    is_required: bool = True
    auto_trigger: str | None = None


class CreateTemplateRequest(BaseModel):
    name: str
    name_ar: str | None = None
    description: str | None = None
    is_default: bool = False
    steps: list[StepDefinition]


class AssignRequest(BaseModel):
    employee_id: UUID
    template_id: UUID | None = None  # None = use default


class CompleteStepRequest(BaseModel):
    step_id: UUID


# ── Templates ───────────────────────────────────────────────

@router.post("/templates")
async def create_template(
    req: CreateTemplateRequest,
    current_user: AdminUser = Depends(require_role(AdminRole.hr_manager)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    svc = OnboardingService(db, tenant_id)
    return await svc.create_template(
        name=req.name, name_ar=req.name_ar, description=req.description,
        is_default=req.is_default, steps=[s.model_dump() for s in req.steps],
    )


@router.get("/templates")
async def list_templates(
    current_user: AdminUser = Depends(require_role(AdminRole.hr_specialist)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    svc = OnboardingService(db, tenant_id)
    return await svc.list_templates()


# ── Assignments ─────────────────────────────────────────────

@router.post("/assign")
async def assign_onboarding(
    req: AssignRequest,
    current_user: AdminUser = Depends(require_role(AdminRole.hr_specialist)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    svc = OnboardingService(db, tenant_id)
    result = await svc.assign_to_employee(req.employee_id, req.template_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/employee/{employee_id}")
async def get_employee_onboarding(
    employee_id: UUID,
    current_user: AdminUser = Depends(require_role(AdminRole.hr_specialist)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    svc = OnboardingService(db, tenant_id)
    result = await svc.get_employee_onboarding(employee_id)
    if not result:
        raise HTTPException(status_code=404, detail="No active onboarding found for this employee")
    return result


@router.post("/assignments/{assignment_id}/complete-step")
async def complete_step(
    assignment_id: UUID,
    req: CompleteStepRequest,
    current_user: AdminUser = Depends(require_role(AdminRole.hr_specialist)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    svc = OnboardingService(db, tenant_id)
    result = await svc.complete_step(assignment_id, req.step_id, f"hr:{current_user.id}")
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/dashboard")
async def onboarding_dashboard(
    current_user: AdminUser = Depends(require_role(AdminRole.hr_specialist)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    svc = OnboardingService(db, tenant_id)
    return await svc.get_onboarding_dashboard()


@router.get("/overdue")
async def overdue_steps(
    current_user: AdminUser = Depends(require_role(AdminRole.hr_specialist)),
    tenant_id: UUID = Depends(require_tenant()),
    db: AsyncSession = Depends(get_db),
):
    svc = OnboardingService(db, tenant_id)
    return await svc.get_overdue_steps()
```

### API Contract Table (C3)

| Method | Path | Request | Response | Auth |
|--------|------|---------|----------|------|
| POST | `/api/v1/onboarding/templates` | `CreateTemplateRequest` | `{template_id, name, step_count}` | hr_manager+ |
| GET | `/api/v1/onboarding/templates` | -- | `[{id, name, name_ar, is_active, is_default, step_count}]` | hr_specialist+ |
| POST | `/api/v1/onboarding/assign` | `{employee_id, template_id?}` | `{assignment_id, employee_id, template, step_count}` | hr_specialist+ |
| GET | `/api/v1/onboarding/employee/{employee_id}` | -- | `{assignment_id, progress_pct, steps[]}` | hr_specialist+ |
| POST | `/api/v1/onboarding/assignments/{id}/complete-step` | `{step_id}` | `{status, step_id, all_done}` | hr_specialist+ |
| GET | `/api/v1/onboarding/dashboard` | -- | `[{employee_name, progress_pct, overdue_steps, ...}]` | hr_specialist+ |
| GET | `/api/v1/onboarding/overdue` | -- | `[{employee_name, step_name, days_overdue, ...}]` | hr_specialist+ |

---

## C4: Employee Ticket Tracking (Deema Tools)

### 1. New Deema Tool Schemas

Add these two tools to `DeemaAgent.get_tools()`:

```json
{
    "name": "list_my_escalations",
    "description": "List all escalation tickets for the current employee. Shows open, assigned, and resolved tickets sorted by most recent. Use when the employee asks about their requests/tickets/طلباتي/تذاكري.",
    "input_schema": {
        "type": "object",
        "properties": {
            "employee_id": {
                "type": "string",
                "description": "The employee's UUID"
            },
            "status": {
                "type": "string",
                "enum": ["open", "assigned", "resolved"],
                "description": "Filter by ticket status (optional — omit for all)"
            }
        },
        "required": ["employee_id"]
    }
}
```

```json
{
    "name": "list_my_leave_requests",
    "description": "List the employee's leave requests with full approval details: who approved/rejected, when, and rejection reasons. Use when the employee asks about their leave history or approval status. More detailed than get_leave_requests.",
    "input_schema": {
        "type": "object",
        "properties": {
            "employee_id": {
                "type": "string",
                "description": "The employee's UUID"
            },
            "status": {
                "type": "string",
                "enum": ["pending", "approved", "rejected", "cancelled"],
                "description": "Filter by status (optional — omit for all)"
            }
        },
        "required": ["employee_id"]
    }
}
```

### 2. Tool Implementations (additions to `deema.py`)

```python
# Add to DeemaAgent.handle_tool_call:
elif tool_name == "list_my_escalations":
    return await self._list_my_escalations(
        UUID(tool_input["employee_id"]),
        tool_input.get("status"),
    )
elif tool_name == "list_my_leave_requests":
    return await self._list_my_leave_requests(
        UUID(tool_input["employee_id"]),
        tool_input.get("status"),
    )

# ── New tool implementations ───────────────────────────────

async def _list_my_escalations(
    self, employee_id: UUID, status: str | None = None
) -> str:
    """List all escalation tickets belonging to this employee."""
    # Ownership check
    if self._employee_id and str(employee_id) != str(self._employee_id):
        return json.dumps({
            "error": "You can only view your own tickets.",
            "error_ar": "يمكنك فقط عرض تذاكرك الخاصة.",
        })

    emp = await self._verify_employee(employee_id)
    if not emp:
        return json.dumps({"error": "Employee not found"})

    query = (
        select(EscalationTicket)
        .where(
            EscalationTicket.tenant_id == self.tenant_id,
            EscalationTicket.employee_id == employee_id,
        )
        .order_by(EscalationTicket.created_at.desc())
        .limit(20)
    )
    if status:
        query = query.where(
            EscalationTicket.status == EscalationStatus(status)
        )

    result = await self.db.execute(query)
    tickets = result.scalars().all()

    if not tickets:
        return json.dumps({
            "message": "No escalation tickets found.",
            "message_ar": "لم يتم العثور على تذاكر تصعيد.",
            "count": 0,
        })

    STATUS_AR = {"open": "مفتوحة", "assigned": "قيد المعالجة", "resolved": "محلولة"}
    CATEGORY_AR = {
        "employee_request": "طلب موظف",
        "agent_failure": "خطأ نظام",
        "sensitive_topic": "موضوع حساس",
        "policy_gap": "فجوة في السياسة",
    }

    return json.dumps({
        "count": len(tickets),
        "tickets": [
            {
                "ticket_id": str(t.id),
                "status": t.status.value,
                "status_ar": STATUS_AR.get(t.status.value, t.status.value),
                "category": t.category.value,
                "category_ar": CATEGORY_AR.get(t.category.value, t.category.value),
                "urgency": t.urgency.value,
                "reason": t.reason,
                "summary": t.summary,
                "assigned_to": t.assigned_to,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "resolved_at": t.resolved_at.isoformat() if t.resolved_at else None,
            }
            for t in tickets
        ],
    })


async def _list_my_leave_requests(
    self, employee_id: UUID, status: str | None = None
) -> str:
    """Enhanced leave request list with approval details."""
    if self._employee_id and str(employee_id) != str(self._employee_id):
        return json.dumps({
            "error": "You can only view your own leave requests.",
            "error_ar": "يمكنك فقط عرض طلبات إجازتك الخاصة.",
        })

    emp = await self._verify_employee(employee_id)
    if not emp:
        return json.dumps({"error": "Employee not found"})

    query = (
        select(LeaveRequest)
        .where(LeaveRequest.employee_id == employee_id)
        .order_by(LeaveRequest.created_at.desc())
        .limit(20)
    )
    if status:
        query = query.where(LeaveRequest.status == LeaveStatus(status))

    result = await self.db.execute(query)
    requests = result.scalars().all()

    if not requests:
        return json.dumps({
            "message": "No leave requests found.",
            "message_ar": "لم يتم العثور على طلبات إجازة.",
            "count": 0,
        })

    STATUS_AR = {
        "pending": "معلقة", "approved": "موافق عليها",
        "rejected": "مرفوضة", "cancelled": "ملغاة",
    }
    LEAVE_TYPE_AR = {
        "annual": "سنوية", "sick": "مرضية", "emergency": "طوارئ",
        "maternity": "أمومة", "paternity": "أبوة", "hajj": "حج",
        "bereavement": "وفاة", "unpaid": "بدون راتب",
    }

    # Batch-fetch approver/rejector names
    approver_ids = set()
    for r in requests:
        if r.approved_by:
            approver_ids.add(r.approved_by)
        if r.rejected_by:
            approver_ids.add(r.rejected_by)

    name_map = {}
    if approver_ids:
        names_result = await self.db.execute(
            select(Employee.id, Employee.first_name, Employee.last_name)
            .where(Employee.id.in_(approver_ids))
        )
        for row in names_result:
            name_map[row.id] = f"{row.first_name} {row.last_name}"

    return json.dumps({
        "count": len(requests),
        "requests": [
            {
                "id": str(r.id),
                "leave_type": r.leave_type.value,
                "leave_type_ar": LEAVE_TYPE_AR.get(r.leave_type.value, r.leave_type.value),
                "start_date": r.start_date.isoformat(),
                "end_date": r.end_date.isoformat(),
                "business_days": r.business_days,
                "status": r.status.value,
                "status_ar": STATUS_AR.get(r.status.value, r.status.value),
                "reason": r.reason,
                "auto_approved": r.auto_approved,
                "approved_by": name_map.get(r.approved_by) if r.approved_by else None,
                "approved_at": r.approved_at.isoformat() if r.approved_at else None,
                "rejected_by": name_map.get(r.rejected_by) if r.rejected_by else None,
                "rejected_at": r.rejected_at.isoformat() if r.rejected_at else None,
                "rejection_reason": r.rejection_reason,
                "created_at": r.created_at.isoformat(),
            }
            for r in requests
        ],
    })
```

### 3. Proactive Context (Deema System Prompt Update)

Modify `BaseAgent.get_system_prompt` to call an optional hook, and implement it in Deema.

In `base.py`, add after the main system prompt return:

```python
# In BaseAgent class, add:
async def get_proactive_context(self, employee_id: str) -> str | None:
    """Override to inject proactive context at conversation start. Returns None by default."""
    return None
```

In `deema.py`, override:

```python
async def get_proactive_context(self, employee_id: str) -> str | None:
    """Check for open tickets and pending leave requests to mention proactively."""
    if not employee_id:
        return None

    try:
        emp_uuid = UUID(employee_id)
    except ValueError:
        return None

    context_parts = []

    # Open escalation tickets
    ticket_result = await self.db.execute(
        select(EscalationTicket).where(
            EscalationTicket.tenant_id == self.tenant_id,
            EscalationTicket.employee_id == emp_uuid,
            EscalationTicket.status.in_([EscalationStatus.open, EscalationStatus.assigned]),
        ).order_by(EscalationTicket.created_at.desc()).limit(5)
    )
    open_tickets = ticket_result.scalars().all()
    if open_tickets:
        ticket_summaries = ", ".join(
            f"#{str(t.id)[:8]} ({t.status.value}: {t.summary or t.reason[:50]})"
            for t in open_tickets
        )
        context_parts.append(
            f"This employee has {len(open_tickets)} open escalation ticket(s): {ticket_summaries}. "
            "Proactively mention them if this is a new conversation."
        )

    # Pending leave requests
    pending_result = await self.db.execute(
        select(func.count(LeaveRequest.id)).where(
            LeaveRequest.employee_id == emp_uuid,
            LeaveRequest.status == LeaveStatus.pending,
        )
    )
    pending_count = pending_result.scalar_one()
    if pending_count > 0:
        context_parts.append(
            f"This employee has {pending_count} pending leave request(s) awaiting approval."
        )

    # Onboarding in progress
    try:
        from app.models.onboarding import OnboardingAssignment
        onboard_result = await self.db.execute(
            select(OnboardingAssignment).where(
                OnboardingAssignment.tenant_id == self.tenant_id,
                OnboardingAssignment.employee_id == emp_uuid,
                OnboardingAssignment.status == "in_progress",
            )
        )
        onboarding = onboard_result.scalar_one_or_none()
        if onboarding:
            context_parts.append(
                "This employee has an onboarding checklist in progress. "
                "If this appears to be their first conversation, welcome them warmly and offer to guide through pending steps."
            )
    except Exception:
        pass  # Onboarding tables may not exist yet during migration

    if not context_parts:
        return None

    return "\n\nProactive context for this employee:\n" + "\n".join(f"- {p}" for p in context_parts)
```

Then in `base.py`, the `respond` method should inject proactive context into the system prompt. Add this between the policy context injection and the hardening step:

```python
# In BaseAgent.respond, after policy context and before build_hardened_system_prompt:
proactive = await self.get_proactive_context(employee_id)
if proactive:
    system_prompt += proactive
```

This requires adding `from sqlalchemy import func, select` to deema.py imports (the `select` import already exists; add `func`).

### 4. Orchestrator Keyword Updates

Add to `INTENT_KEYWORDS["deema"]` in orchestrator.py:

```python
"طلباتي", "تذاكري", "my requests", "my tickets", "track",
```

---

## Database Migration Notes

### New Tables

1. **`nitaqat_configs`** -- One row per tenant. Columns: `id`, `tenant_id` (FK+unique), `industry`, `industry_ar`, `size_category` (enum), 4 threshold floats, `target_saudization_pct`, `alert_when_below_target`, `alert_buffer_pct`, timestamps.

2. **`onboarding_templates`** -- Columns: `id`, `tenant_id` (FK), `name`, `name_ar`, `description`, `is_active`, `is_default`, timestamps. Unique constraint on `(tenant_id, name)`.

3. **`onboarding_template_steps`** -- Columns: `id`, `template_id` (FK CASCADE), `name`, `name_ar`, `description`, `description_ar`, `step_type` (enum), `order`, `due_days_after_hire`, `is_required`, `auto_trigger`.

4. **`onboarding_assignments`** -- Columns: `id`, `tenant_id` (FK), `employee_id` (FK), `template_id` (FK), `status`, `started_at`, `completed_at`. Unique constraint on `(employee_id, template_id)`. Index on `(tenant_id, status)`.

5. **`onboarding_step_assignments`** -- Columns: `id`, `assignment_id` (FK CASCADE), `template_step_id` (FK), `status` (enum), `order`, `due_date`, `completed_at`, `completed_by`, `notes`. Unique constraint on `(assignment_id, template_step_id)`.

### New Enums (Postgres)

- `nitaqatband`: platinum, green_high, green_low, yellow, red
- `companysizecategory`: micro, small, medium, large, giant
- `onboardingsteptype`: manual, automatic, agent_assisted
- `onboardingstepstatus`: pending, in_progress, completed, skipped

### New Indexes

- `ix_onboarding_assignment_tenant_status` on `onboarding_assignments(tenant_id, status)`
- Implicit indexes from FK constraints and unique constraints

### Recommended Indexes on Existing Tables (for reporting performance)

- `ix_leave_requests_employee_status` on `leave_requests(employee_id, status)` -- speeds up leave utilization queries
- `ix_escalation_tickets_tenant_status` on `escalation_tickets(tenant_id, status)` -- speeds up escalation reports
- `ix_conversations_tenant_agent_started` on `conversations(tenant_id, agent_name, started_at)` -- speeds up agent performance

### Model Registration

Add to `/backend/app/models/__init__.py`:

```python
from app.models.nitaqat import NitaqatConfig
from app.models.onboarding import (
    OnboardingTemplate, OnboardingTemplateStep,
    OnboardingAssignment, OnboardingStepAssignment,
)
```

And extend `__all__`.

### Router Registration

Add to `/backend/app/main.py`:

```python
from app.api import reports, nitaqat, onboarding

app.include_router(reports.router, prefix="/api/v1")
app.include_router(nitaqat.router, prefix="/api/v1")
app.include_router(onboarding.router, prefix="/api/v1")
```

### Notification Category Extension

Add `onboarding = "onboarding"` to `NotificationCategory` in `/backend/app/models/notification.py`, and add `onboarding_notifications: Mapped[bool]` to `NotificationPreference`. This is an additive enum change -- safe for Postgres with `ALTER TYPE ... ADD VALUE`.

---

## Integration Points

### C1 (Reporting) Integration

```
HR Dashboard UI
    |
    v
GET /api/v1/reports/*  (require_role: hr_manager+)
    |
    v
ReportingService (queries existing tables, no writes)
    |
    v
Redis cache (5 min TTL) --> fallback: in-memory dict
    |
    v
Existing tables: employees, leave_requests, leave_balances,
                  conversations, messages, escalation_tickets, departments
```

No writes, no side effects. Pure read-only aggregation.

### C2 (Nitaqat) Integration

```
HR Dashboard UI
    |
    v
/api/v1/nitaqat/*  (require_role: hr_manager+ or tenant_admin for config)
    |
    v
NitaqatService
    |
    +---> reads employees table (is_saudi, status)
    +---> reads/writes nitaqat_configs table
    |
    v
Integration trigger (future): Employee status change webhook
    --> NitaqatService.check_termination_impact()
        --> NotificationService.send() to HR managers if warning=True
```

The termination impact check should be wired into the employee status update flow. For now, Rania should expose it as an API endpoint that the employee management UI calls before confirming a termination. A future sprint can wire it as an automatic trigger.

### C3 (Onboarding) Integration

```
HR Admin UI                        Employee (via Deema/Waleed)
    |                                     |
    v                                     v
/api/v1/onboarding/*              Waleed agent tools (get_onboarding_checklist)
    |                              Deema proactive context
    v                                     |
OnboardingService                         |
    |                                     |
    +---> onboarding_* tables <-----------+
    +---> Employee.hire_date (due date calc)
    +---> NotificationService (overdue alerts)
    |
    v
Automatic step completion triggers:
    - PolicyAcknowledgment created --> complete "policy_acknowledged" step
    - Document uploaded --> complete "document_uploaded:*" step
    (These integrations are wired by checking auto_trigger field)
```

### C4 (Ticket Tracking) Integration

```
Employee chat
    |
    v
Deema agent (respond)
    |
    +---> get_proactive_context() --> queries escalation_tickets, leave_requests, onboarding_assignments
    |     (injected into system prompt at conversation start)
    |
    +---> list_my_escalations tool --> queries escalation_tickets WHERE employee_id = self
    +---> list_my_leave_requests tool --> queries leave_requests with approval details
```

---

## Open Questions for CTO

1. **Nitaqat threshold source of truth.** The design uses simplified default thresholds. Real Nitaqat thresholds vary by economic activity code and company size bracket (MOL publishes these). Should we hardcode the full MOL lookup table in a future sprint, or is tenant-configurable sufficient for launch?

2. **Onboarding auto-assignment.** Should onboarding be auto-assigned when a new employee is created via the API (POST /employees), or should HR always trigger it manually? I have designed the service to support both -- the question is which path to wire by default.

3. **Automatic step completion triggers.** The `auto_trigger` field on template steps (e.g., `policy_acknowledged`, `document_uploaded:employment_contract`) needs event listeners. Should we implement these as part of this sprint (by adding hooks into the PolicyAcknowledgment and Document creation flows), or defer to a dedicated "event bus" sprint?

4. **Report export.** The reporting endpoints return JSON for chart rendering. Should we add CSV/Excel export in this sprint, or defer? If so, the service layer is already structured to support it -- we just need a serialization layer.

5. **Cache invalidation.** The 5-minute TTL is a simple approach. Should we add explicit cache invalidation when leave requests or employee records change, or is eventual consistency acceptable for dashboard data?

6. **Waleed agent wiring.** Waleed currently has stub tool implementations. Should Rania wire Waleed's `get_onboarding_checklist` to the real `OnboardingService` in this sprint, or keep it as a follow-up?

---

## Key Files Reference

Existing files to modify:
- `/backend/app/models/__init__.py` -- register new models
- `/backend/app/main.py` -- register new routers
- `/backend/app/agents/deema.py` -- add 2 tools + proactive context override
- `/backend/app/agents/base.py` -- add `get_proactive_context` hook + inject in `respond`
- `/backend/app/agents/orchestrator.py` -- add keywords for ticket tracking
- `/backend/app/models/notification.py` -- add `onboarding` category

New files:
- `/backend/app/models/nitaqat.py`
- `/backend/app/models/onboarding.py`
- `/backend/app/services/reporting.py`
- `/backend/app/services/nitaqat.py`
- `/backend/app/services/onboarding.py`
- `/backend/app/api/reports.py`
- `/backend/app/api/nitaqat.py`
- `/backend/app/api/onboarding.py`