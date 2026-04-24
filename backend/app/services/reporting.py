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

CACHE_TTL_SECONDS = 300  # 5 minutes


async def _get_redis():
    """Try to get Redis connection, return None if unavailable."""
    try:
        from app.security.rate_limiter import get_redis
        return await get_redis()
    except Exception:
        return None


async def _cache_get(key: str) -> Any | None:
    """Read from Redis. Returns None if Redis is unavailable."""
    redis = await _get_redis()
    if redis:
        try:
            val = await redis.get(key)
            if val:
                return json.loads(val)
        except Exception:
            pass
    return None


async def _cache_set(key: str, data: Any, ttl: int = CACHE_TTL_SECONDS) -> None:
    """Write to Redis. Skips caching silently if Redis is unavailable."""
    redis = await _get_redis()
    if redis:
        try:
            await redis.set(key, json.dumps(data, default=str), ex=ttl)
        except Exception:
            pass


def _cache_key(tenant_id: uuid.UUID, report: str, **params) -> str:
    """Build a deterministic cache key."""
    param_str = json.dumps(params, sort_keys=True, default=str)
    h = hashlib.sha256(param_str.encode()).hexdigest()[:12]
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

        start_dt = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        end_dt = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=timezone.utc)

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
                    (Conversation.resolved_automatically.is_(True), 1), else_=0
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
        # Saudi work week: Sunday-Thursday (weekend = Friday + Saturday)
        days_since_sunday = (today.weekday() + 1) % 7  # Sunday=0
        week_start = today - timedelta(days=days_since_sunday)
        week_end = week_start + timedelta(days=4)  # Thursday
        if today > week_end:
            week_start += timedelta(days=7)
            week_end += timedelta(days=7)

        base = [
            Employee.tenant_id == self.tenant_id,
            LeaveRequest.status == LeaveStatus.approved,
        ]
        if department_id:
            base.append(Employee.department_id == department_id)

        # On leave today
        on_leave_today_result = await self.db.execute(
            select(
                Employee.id, Employee.first_name, Employee.last_name,
                Employee.first_name_ar, Employee.last_name_ar,
                LeaveRequest.leave_type, LeaveRequest.start_date, LeaveRequest.end_date,
            )
            .join(LeaveRequest, LeaveRequest.employee_id == Employee.id)
            .where(*base, LeaveRequest.start_date <= today, LeaveRequest.end_date >= today)
        )
        today_rows = on_leave_today_result.all()

        # On leave this week
        on_leave_week_result = await self.db.execute(
            select(
                Employee.id, Employee.first_name, Employee.last_name,
                Employee.first_name_ar, Employee.last_name_ar,
                LeaveRequest.leave_type, LeaveRequest.start_date, LeaveRequest.end_date,
            )
            .join(LeaveRequest, LeaveRequest.employee_id == Employee.id)
            .where(*base, LeaveRequest.start_date <= week_end, LeaveRequest.end_date >= today)
        )
        week_rows = on_leave_week_result.all()

        # Upcoming leaves (next 14 days, not yet started)
        upcoming_end = today + timedelta(days=14)
        upcoming_result = await self.db.execute(
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
        upcoming_rows = upcoming_result.all()

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
            "on_leave_today": [_fmt(r) for r in today_rows],
            "on_leave_today_count": len(today_rows),
            "on_leave_this_week": [_fmt(r) for r in week_rows],
            "upcoming_leaves": [
                {**_fmt(r), "business_days": r.business_days} for r in upcoming_rows
            ],
        }
        await _cache_set(cache_key, result)
        return result
