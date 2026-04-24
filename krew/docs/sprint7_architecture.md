# Sprint 7 Technical Architecture

**Author:** Faisal (System Architect)
**Date:** 2026-03-28
**Status:** Ready for Implementation
**Tracks:** Ahmad A2 (5 Cross-Domain Analytics Tools) + Conversational UX (3 Features)

---

## Table of Contents

1. [Track 1: Ahmad A2 — Cross-Domain Analytics](#track-1-ahmad-a2--cross-domain-analytics)
   - [A2-01: get_recruitment_analytics](#a2-01-get_recruitment_analytics)
   - [A2-02: get_leave_analytics](#a2-02-get_leave_analytics)
   - [A2-03: get_attendance_analytics](#a2-03-get_attendance_analytics)
   - [A2-04: get_onboarding_analytics](#a2-04-get_onboarding_analytics)
   - [A2-05: get_payroll_summary](#a2-05-get_payroll_summary)
2. [Track 2: Conversational UX](#track-2-conversational-ux)
   - [CUX-01: Suggestions API](#cux-01-suggestions-api)
   - [CUX-02: Follow-Up Chips](#cux-02-follow-up-chips)
   - [CUX-03: Quick Actions Bar](#cux-03-quick-actions-bar)
3. [Database Migration Notes](#database-migration-notes)
4. [Integration Matrix](#integration-matrix)
5. [Open Questions](#open-questions)

---

## Track 1: Ahmad A2 — Cross-Domain Analytics

### Design Principles (inherited from A1)

- **Read-only**: Ahmad never modifies data. All tools are SELECT-only.
- **Multi-tenant**: Every query filters by `tenant_id`. Candidate/LeaveRequest/LeaveBalance lack tenant_id; isolation enforced via JOINs to Employee or JobPosting.
- **k-anonymity**: `MIN_GROUP_SIZE = 5`. Any group with fewer than 5 members gets its detailed metrics suppressed with a privacy note.
- **No PII in output**: Never return names, emails, phone numbers, national IDs, or individual records.
- **Error pattern**: All tools return `json.dumps({"error": "..."})` on validation failure. Unexpected exceptions caught in `handle_tool_call` dispatch.
- **months parameter**: Clamped to `max(1, min(60, value))` with default 12, matching the A1 turnover tool pattern.
- **department_id validation**: UUID validation in `handle_tool_call` before dispatch, matching existing A1 pattern.

### New Imports Required in `ahmad.py`

```python
# Add to existing imports
from app.models.candidate import JobPosting, Candidate, PostingStatus, CandidateStage
from app.models.leave import LeaveRequest, LeaveBalance, LeaveType, LeaveStatus
from app.models.attendance import AttendanceRecord, AttendanceStatus
from app.models.onboarding import (
    OnboardingAssignment, OnboardingAssignmentStatus,
    OnboardingStepAssignment, OnboardingStepStatus,
    OnboardingTemplateStep,
)
from app.models.payslip import Payslip
```

---

### A2-01: get_recruitment_analytics

#### Tool Definition

```json
{
    "name": "get_recruitment_analytics",
    "description": "Get recruitment pipeline analytics: funnel stages (applied → screened → interviewed → offered → hired), open positions count, time-to-fill, average AI match score. Filters by department and time period. PRIVACY: No candidate names or personal data.",
    "input_schema": {
        "type": "object",
        "properties": {
            "department_id": {
                "type": "string",
                "description": "Optional department UUID to filter job postings by"
            },
            "months": {
                "type": "integer",
                "description": "Lookback period in months (default 12, max 60)"
            }
        },
        "required": []
    }
}
```

#### Method Signature & Query Plan

```python
async def _get_recruitment_analytics(self, tool_input: dict) -> str:
```

**Tables:** `JobPosting`, `Candidate`, `Interview` (via `JobPosting.tenant_id` for isolation)

**Query 1 — Open positions count:**
```python
open_q = (
    select(func.count(JobPosting.id))
    .where(
        JobPosting.tenant_id == self.tenant_id,
        JobPosting.status == PostingStatus.open,
    )
)
# Optional: .where(JobPosting.department_id == department_id)
```

**Query 2 — Funnel stages (all stages including rejected/withdrawn for complete picture):**
```python
cutoff = date.today() - timedelta(days=months * 30)
funnel_q = (
    select(
        Candidate.stage,
        func.count(Candidate.id).label("count"),
    )
    .join(JobPosting, Candidate.job_posting_id == JobPosting.id)
    .where(
        JobPosting.tenant_id == self.tenant_id,
        Candidate.created_at >= cutoff,
    )
    .group_by(Candidate.stage)
)
# Optional: .where(JobPosting.department_id == department_id)
```

**Query 3 — Time-to-fill (avg days from posting to first hired candidate):**
```python
# Subquery: for each posting with at least one hired candidate, compute
# (min_hired_date - posting_created_at) in days
from sqlalchemy import literal_column

hired_sub = (
    select(
        JobPosting.id.label("jp_id"),
        JobPosting.created_at.label("posted_at"),
        func.min(Candidate.created_at).label("hired_at"),
    )
    .join(Candidate, Candidate.job_posting_id == JobPosting.id)
    .where(
        JobPosting.tenant_id == self.tenant_id,
        Candidate.stage == CandidateStage.hired,
        JobPosting.created_at >= cutoff,
    )
    .group_by(JobPosting.id, JobPosting.created_at)
).subquery()

# Average in Python after fetching rows (PostgreSQL date arithmetic varies):
# avg_ttf = mean([(row.hired_at - row.posted_at).days for row in rows])
```

**Query 4 — Average AI match score (hired candidates only vs all):**
```python
score_q = (
    select(
        func.avg(Candidate.ai_match_score).label("avg_score"),
        func.count(Candidate.id).label("scored_count"),
    )
    .join(JobPosting, Candidate.job_posting_id == JobPosting.id)
    .where(
        JobPosting.tenant_id == self.tenant_id,
        Candidate.ai_match_score.isnot(None),
        Candidate.created_at >= cutoff,
    )
)
```

**Query 5 — Postings by status (for overview):**
```python
status_q = (
    select(
        JobPosting.status,
        func.count(JobPosting.id).label("count"),
    )
    .where(
        JobPosting.tenant_id == self.tenant_id,
        JobPosting.created_at >= cutoff,
    )
    .group_by(JobPosting.status)
)
```

#### Response Schema

```json
{
    "period_months": 12,
    "open_positions": 5,
    "postings_by_status": {
        "draft": 2,
        "open": 5,
        "closed": 8,
        "on_hold": 1
    },
    "funnel": {
        "applied": 120,
        "screened": 85,
        "shortlisted": 40,
        "interview_scheduled": 30,
        "interviewed": 28,
        "offer_sent": 12,
        "hired": 10,
        "rejected": 25,
        "withdrawn": 5
    },
    "conversion_rates": {
        "applied_to_screened_pct": 70.8,
        "screened_to_interviewed_pct": 32.9,
        "interviewed_to_offered_pct": 42.9,
        "offered_to_hired_pct": 83.3,
        "overall_pct": 8.3
    },
    "avg_time_to_fill_days": 34.5,
    "avg_ai_match_score": 72.3,
    "candidates_scored": 95,
    "privacy_note": "Aggregated pipeline data only. No candidate names or personal data."
}
```

#### Privacy & Security

- Tenant isolation via `JobPosting.tenant_id`. Candidate has no tenant_id; always JOIN through JobPosting.
- No candidate names, emails, phones, or resume URLs in output.
- No individual posting titles (aggregate counts only).
- k-anonymity not applicable here (funnel is org-wide, not per-person).

#### Error Handling

- Invalid `department_id` UUID: caught in `handle_tool_call` dispatcher (existing pattern).
- No postings found: return `{"message": "No job postings found for this period.", "open_positions": 0, ...}`.
- Zero candidates: funnel with all zeroes, conversion rates as `0.0`.

#### Model Dependencies

- `JobPosting` -- exists, has `tenant_id`, `department_id`, `status`, `created_at`. All needed fields present.
- `Candidate` -- exists, has `stage`, `ai_match_score`, `created_at`, `job_posting_id`. All needed fields present.
- `Interview` -- exists but NOT needed for funnel. Candidate.stage already tracks progression. Interview data is supplementary for future A3 enrichment.
- **No missing models or fields.**

---

### A2-02: get_leave_analytics

#### Tool Definition

```json
{
    "name": "get_leave_analytics",
    "description": "Get leave analytics: usage by leave type (annual, sick, hajj, maternity, etc.), department comparison, approval/rejection rates, seasonal patterns, and balance utilization. Saudi-specific: tracks Hajj leave, Ramadan patterns. PRIVACY: Aggregated only.",
    "input_schema": {
        "type": "object",
        "properties": {
            "department_id": {
                "type": "string",
                "description": "Optional department UUID to filter by"
            },
            "months": {
                "type": "integer",
                "description": "Lookback period in months (default 12, max 60)"
            }
        },
        "required": []
    }
}
```

#### Method Signature & Query Plan

```python
async def _get_leave_analytics(self, tool_input: dict) -> str:
```

**Tables:** `LeaveRequest`, `LeaveBalance`, `Employee`, `Department`

**Tenant isolation:** LeaveRequest and LeaveBalance lack `tenant_id`. Isolation enforced via JOIN to `Employee.tenant_id == self.tenant_id`.

**Query 1 — Usage by leave type (approved requests in period):**
```python
cutoff = date.today() - timedelta(days=months * 30)
by_type_q = (
    select(
        LeaveRequest.leave_type,
        func.coalesce(func.sum(LeaveRequest.business_days), 0).label("total_days"),
        func.count(LeaveRequest.id).label("request_count"),
    )
    .join(Employee, LeaveRequest.employee_id == Employee.id)
    .where(
        Employee.tenant_id == self.tenant_id,
        LeaveRequest.status == LeaveStatus.approved,
        LeaveRequest.start_date >= cutoff,
    )
    .group_by(LeaveRequest.leave_type)
)
# Optional department filter: .where(Employee.department_id == department_id)
```

**Query 2 — Approval/rejection rates:**
```python
decision_q = (
    select(
        LeaveRequest.status,
        func.count(LeaveRequest.id).label("count"),
    )
    .join(Employee, LeaveRequest.employee_id == Employee.id)
    .where(
        Employee.tenant_id == self.tenant_id,
        LeaveRequest.created_at >= cutoff,
        LeaveRequest.status.in_([
            LeaveStatus.approved, LeaveStatus.rejected, LeaveStatus.pending
        ]),
    )
    .group_by(LeaveRequest.status)
)
```

**Query 3 — Department comparison (approved days per department):**
```python
dept_q = (
    select(
        Department.name.label("dept_name"),
        Department.id.label("dept_id"),
        func.coalesce(func.sum(LeaveRequest.business_days), 0).label("total_days"),
        func.count(LeaveRequest.id).label("request_count"),
        func.count(func.distinct(LeaveRequest.employee_id)).label("unique_employees"),
    )
    .join(Employee, LeaveRequest.employee_id == Employee.id)
    .join(Department, Employee.department_id == Department.id)
    .where(
        Employee.tenant_id == self.tenant_id,
        LeaveRequest.status == LeaveStatus.approved,
        LeaveRequest.start_date >= cutoff,
    )
    .group_by(Department.id, Department.name)
)
```

**Query 4 — Monthly seasonal pattern:**
```python
monthly_q = (
    select(
        func.extract("month", LeaveRequest.start_date).label("month"),
        func.coalesce(func.sum(LeaveRequest.business_days), 0).label("days"),
        func.count(LeaveRequest.id).label("requests"),
    )
    .join(Employee, LeaveRequest.employee_id == Employee.id)
    .where(
        Employee.tenant_id == self.tenant_id,
        LeaveRequest.status == LeaveStatus.approved,
        LeaveRequest.start_date >= cutoff,
    )
    .group_by(func.extract("month", LeaveRequest.start_date))
    .order_by(func.extract("month", LeaveRequest.start_date))
)
```

**Query 5 — Balance utilization (current year):**
```python
current_year = date.today().year
util_q = (
    select(
        LeaveBalance.leave_type,
        func.coalesce(func.sum(LeaveBalance.total_days), 0).label("entitled"),
        func.coalesce(func.sum(LeaveBalance.used_days), 0).label("used"),
    )
    .join(Employee, LeaveBalance.employee_id == Employee.id)
    .where(
        Employee.tenant_id == self.tenant_id,
        LeaveBalance.year == current_year,
    )
    .group_by(LeaveBalance.leave_type)
)
```

**Query 6 — Pending requests count:**
```python
pending_q = (
    select(func.count(LeaveRequest.id))
    .join(Employee, LeaveRequest.employee_id == Employee.id)
    .where(
        Employee.tenant_id == self.tenant_id,
        LeaveRequest.status == LeaveStatus.pending,
    )
)
```

#### Response Schema

```json
{
    "period_months": 12,
    "by_type": [
        {"leave_type": "annual", "total_days": 450, "request_count": 45},
        {"leave_type": "sick", "total_days": 120, "request_count": 60},
        {"leave_type": "hajj", "total_days": 30, "request_count": 2},
        {"leave_type": "maternity", "total_days": 70, "request_count": 1},
        {"leave_type": "emergency", "total_days": 15, "request_count": 8}
    ],
    "approval_rates": {
        "total_requests": 130,
        "approved": 110,
        "rejected": 12,
        "pending": 8,
        "approval_rate_pct": 84.6,
        "rejection_rate_pct": 9.2
    },
    "department_comparison": [
        {
            "department": "Engineering",
            "department_id": "uuid",
            "total_days": 180,
            "request_count": 20,
            "unique_employees": 15,
            "avg_days_per_employee": 12.0
        }
    ],
    "monthly_pattern": [
        {"month": 1, "month_name": "January", "days": 30, "requests": 8},
        {"month": 3, "month_name": "March", "days": 80, "requests": 25, "note": "Ramadan period"},
        {"month": 6, "month_name": "June", "days": 60, "requests": 15, "note": "Hajj season"}
    ],
    "balance_utilization": [
        {"leave_type": "annual", "entitled": 1500, "used": 450, "utilization_pct": 30.0}
    ],
    "pending_requests": 8,
    "saudi_insights": {
        "hajj_leaves_taken": 2,
        "hajj_note": "Hajj leave is a one-time entitlement during employment.",
        "peak_months": ["March", "June"],
        "peak_note": "Leave peaks align with Ramadan and Hajj seasons."
    }
}
```

#### Saudi-Specific Logic (computed in Python after queries)

```python
# Identify Ramadan/Hajj months from saudi_holidays module
# Tag monthly_pattern entries with notes when month falls in:
# - Ramadan period (approximately month 3 for 2026, varies by Hijri calendar)
# - Hajj season (approximately month 6 for 2026)
# - Summer break (July-August — common annual leave peak)
# Use app.saudi_holidays._EID_DATES to determine approximate months
```

#### Privacy & Security

- No individual leave records. Aggregated by type, department, month.
- k-anonymity applied to department comparison: suppress if `unique_employees < MIN_GROUP_SIZE`.
- Pending count is org-wide (no per-employee detail).

#### Error Handling

- No leave requests in period: `{"message": "No leave requests found for the last N months.", ...}` with zero-filled structure.
- Invalid department: caught by dispatcher.

#### Model Dependencies

- `LeaveRequest` -- has `employee_id`, `leave_type`, `business_days`, `status`, `start_date`, `created_at`. All present.
- `LeaveBalance` -- has `employee_id`, `leave_type`, `year`, `total_days`, `used_days`. All present.
- **Neither has `tenant_id`** -- isolation via Employee JOIN (documented above).
- **No missing fields.**

---

### A2-03: get_attendance_analytics

#### Tool Definition

```json
{
    "name": "get_attendance_analytics",
    "description": "Get attendance analytics: attendance rate, late arrival rate, absence rate, overtime hours, department comparison, day-of-week patterns. Saudi context: Fri/Sat weekend, prayer time considerations. PRIVACY: Aggregated rates only.",
    "input_schema": {
        "type": "object",
        "properties": {
            "department_id": {
                "type": "string",
                "description": "Optional department UUID to filter by"
            },
            "months": {
                "type": "integer",
                "description": "Lookback period in months (default 3, max 12)"
            }
        },
        "required": []
    }
}
```

Note: Default is 3 months (not 12) because attendance data is high-volume. Max capped at 12 to prevent expensive queries.

#### Method Signature & Query Plan

```python
async def _get_attendance_analytics(self, tool_input: dict) -> str:
```

**Tables:** `AttendanceRecord`, `Employee`, `Department`

**Tenant isolation:** `AttendanceRecord.tenant_id == self.tenant_id` (AttendanceRecord has its own tenant_id).

**Query 1 — Status breakdown (exclude weekend/holiday records):**
```python
months = max(1, min(12, tool_input.get("months", 3)))
cutoff = date.today() - timedelta(days=months * 30)

status_q = (
    select(
        AttendanceRecord.status,
        func.count(AttendanceRecord.id).label("count"),
    )
    .where(
        AttendanceRecord.tenant_id == self.tenant_id,
        AttendanceRecord.date >= cutoff,
        AttendanceRecord.status.notin_([
            AttendanceStatus.weekend, AttendanceStatus.holiday,
        ]),
    )
    .group_by(AttendanceRecord.status)
)
# Optional department filter via subquery or JOIN to Employee
```

If `department_id` provided, add JOIN:
```python
status_q = status_q.join(
    Employee, AttendanceRecord.employee_id == Employee.id
).where(Employee.department_id == department_id)
```

**Query 2 — Overtime summary:**
```python
ot_q = (
    select(
        func.coalesce(func.sum(AttendanceRecord.overtime_hours), 0.0).label("total_ot"),
        func.count(func.distinct(AttendanceRecord.employee_id)).label("employees_with_ot"),
        func.avg(AttendanceRecord.overtime_hours).label("avg_ot_per_record"),
    )
    .where(
        AttendanceRecord.tenant_id == self.tenant_id,
        AttendanceRecord.date >= cutoff,
        AttendanceRecord.overtime_hours > 0,
    )
)
```

**Query 3 — Department comparison:**
```python
dept_q = (
    select(
        Department.name.label("dept_name"),
        Department.id.label("dept_id"),
        func.count(AttendanceRecord.id).label("total_records"),
        func.sum(case((AttendanceRecord.status == AttendanceStatus.present, 1), else_=0)).label("present"),
        func.sum(case((AttendanceRecord.status == AttendanceStatus.late, 1), else_=0)).label("late"),
        func.sum(case((AttendanceRecord.status == AttendanceStatus.absent, 1), else_=0)).label("absent"),
        func.coalesce(func.sum(AttendanceRecord.overtime_hours), 0.0).label("overtime"),
    )
    .join(Employee, AttendanceRecord.employee_id == Employee.id)
    .join(Department, Employee.department_id == Department.id)
    .where(
        AttendanceRecord.tenant_id == self.tenant_id,
        AttendanceRecord.date >= cutoff,
        AttendanceRecord.status.notin_([
            AttendanceStatus.weekend, AttendanceStatus.holiday,
        ]),
    )
    .group_by(Department.id, Department.name)
)
```

**Query 4 — Day-of-week pattern:**
```python
# PostgreSQL: EXTRACT(DOW FROM date) returns 0=Sunday, 6=Saturday
dow_q = (
    select(
        func.extract("dow", AttendanceRecord.date).label("day_of_week"),
        func.count(AttendanceRecord.id).label("total"),
        func.sum(case(
            (AttendanceRecord.status.in_([AttendanceStatus.present, AttendanceStatus.late]), 1),
            else_=0,
        )).label("present_count"),
        func.sum(case(
            (AttendanceRecord.status == AttendanceStatus.late, 1),
            else_=0,
        )).label("late_count"),
    )
    .where(
        AttendanceRecord.tenant_id == self.tenant_id,
        AttendanceRecord.date >= cutoff,
        AttendanceRecord.status.notin_([
            AttendanceStatus.weekend, AttendanceStatus.holiday,
        ]),
    )
    .group_by(func.extract("dow", AttendanceRecord.date))
    .order_by(func.extract("dow", AttendanceRecord.date))
)
```

#### Response Schema

```json
{
    "period_months": 3,
    "summary": {
        "total_work_records": 5400,
        "present": 4800,
        "late": 300,
        "absent": 180,
        "half_day": 50,
        "on_leave": 70,
        "attendance_rate_pct": 94.4,
        "late_rate_pct": 5.6,
        "absence_rate_pct": 3.3
    },
    "overtime": {
        "total_hours": 1250.5,
        "employees_with_overtime": 42,
        "avg_hours_per_record": 2.3
    },
    "department_comparison": [
        {
            "department": "Engineering",
            "department_id": "uuid",
            "total_records": 1200,
            "present": 1100,
            "late": 60,
            "absent": 40,
            "attendance_rate_pct": 96.7,
            "late_rate_pct": 5.0,
            "overtime_hours": 350.0
        }
    ],
    "day_of_week_pattern": [
        {"day": "Sunday", "day_ar": "الأحد", "attendance_rate_pct": 96.2, "late_rate_pct": 4.1},
        {"day": "Monday", "day_ar": "الاثنين", "attendance_rate_pct": 95.8, "late_rate_pct": 5.3},
        {"day": "Thursday", "day_ar": "الخميس", "attendance_rate_pct": 92.1, "late_rate_pct": 8.5, "note": "Pre-weekend dip typical"}
    ],
    "saudi_context": {
        "weekend_days": "Friday & Saturday",
        "work_week": "Sunday to Thursday",
        "note": "Attendance rates exclude Fri/Sat weekends and public holidays."
    }
}
```

#### Saudi-Specific Logic

```python
# Day-of-week mapping for Saudi context (Sun-Thu = work week):
DOW_NAMES = {
    0: ("Sunday", "الأحد"),
    1: ("Monday", "الاثنين"),
    2: ("Tuesday", "الثلاثاء"),
    3: ("Wednesday", "الأربعاء"),
    4: ("Thursday", "الخميس"),
    5: ("Friday", "الجمعة"),    # Weekend
    6: ("Saturday", "السبت"),    # Weekend
}

# Thursday gets a "pre-weekend" flag if late_rate > avg
# Sunday gets a "start-of-week" flag if late_rate > avg
```

#### Privacy & Security

- No individual attendance records. All aggregated by status/department/day.
- k-anonymity applied to department comparison: suppress if fewer than 5 unique employees in department's records for the period.
- Overtime is aggregate sum, not per-employee.

#### Error Handling

- No attendance records: `{"message": "No attendance records found for this period. Attendance tracking may not be configured yet."}`.
- months capped at 12 (not 60) to prevent query overload on high-volume table.

#### Model Dependencies

- `AttendanceRecord` -- has `tenant_id`, `employee_id`, `date`, `status`, `overtime_hours`, `check_in`, `check_out`. All present.
- `AttendanceStatus` enum -- has `present`, `absent`, `late`, `half_day`, `on_leave`, `holiday`, `weekend`. All present.
- **No missing fields.**

---

### A2-04: get_onboarding_analytics

#### Tool Definition

```json
{
    "name": "get_onboarding_analytics",
    "description": "Get onboarding analytics: completion rate, average completion time (days), bottleneck steps (lowest completion rate), overdue step count, department breakdown. Tracks new hire onboarding health.",
    "input_schema": {
        "type": "object",
        "properties": {
            "department_id": {
                "type": "string",
                "description": "Optional department UUID to filter by"
            },
            "months": {
                "type": "integer",
                "description": "Lookback period in months for started assignments (default 6, max 24)"
            }
        },
        "required": []
    }
}
```

#### Method Signature & Query Plan

```python
async def _get_onboarding_analytics(self, tool_input: dict) -> str:
```

**Tables:** `OnboardingAssignment`, `OnboardingStepAssignment`, `OnboardingTemplateStep`, `Employee`, `Department`

**Tenant isolation:** `OnboardingAssignment.tenant_id == self.tenant_id`.

**Query 1 — Overall completion stats:**
```python
months = max(1, min(24, tool_input.get("months", 6)))
cutoff = datetime.now(timezone.utc) - timedelta(days=months * 30)

stats_q = (
    select(
        func.count(OnboardingAssignment.id).label("total"),
        func.sum(case(
            (OnboardingAssignment.status == OnboardingAssignmentStatus.completed, 1),
            else_=0,
        )).label("completed"),
        func.sum(case(
            (OnboardingAssignment.status == OnboardingAssignmentStatus.in_progress, 1),
            else_=0,
        )).label("in_progress"),
        func.sum(case(
            (OnboardingAssignment.status == OnboardingAssignmentStatus.cancelled, 1),
            else_=0,
        )).label("cancelled"),
    )
    .where(
        OnboardingAssignment.tenant_id == self.tenant_id,
        OnboardingAssignment.started_at >= cutoff,
    )
)
# Optional department filter via JOIN to Employee
```

If `department_id` provided:
```python
stats_q = stats_q.join(
    Employee, OnboardingAssignment.employee_id == Employee.id
).where(Employee.department_id == department_id)
```

**Query 2 — Average completion time (completed assignments only):**
```python
avg_q = (
    select(
        func.avg(
            func.extract("epoch",
                OnboardingAssignment.completed_at - OnboardingAssignment.started_at
            ) / 86400
        ).label("avg_days"),
        func.min(
            func.extract("epoch",
                OnboardingAssignment.completed_at - OnboardingAssignment.started_at
            ) / 86400
        ).label("min_days"),
        func.max(
            func.extract("epoch",
                OnboardingAssignment.completed_at - OnboardingAssignment.started_at
            ) / 86400
        ).label("max_days"),
    )
    .where(
        OnboardingAssignment.tenant_id == self.tenant_id,
        OnboardingAssignment.status == OnboardingAssignmentStatus.completed,
        OnboardingAssignment.started_at >= cutoff,
        OnboardingAssignment.completed_at.isnot(None),
    )
)
```

**Query 3 — Bottleneck steps (lowest completion rate across all assignments):**
```python
bottleneck_q = (
    select(
        OnboardingTemplateStep.name.label("step_name"),
        OnboardingTemplateStep.name_ar.label("step_name_ar"),
        OnboardingTemplateStep.order.label("step_order"),
        func.count(OnboardingStepAssignment.id).label("total"),
        func.sum(case(
            (OnboardingStepAssignment.status == OnboardingStepStatus.completed, 1),
            else_=0,
        )).label("completed"),
    )
    .join(
        OnboardingAssignment,
        OnboardingStepAssignment.assignment_id == OnboardingAssignment.id,
    )
    .join(
        OnboardingTemplateStep,
        OnboardingStepAssignment.template_step_id == OnboardingTemplateStep.id,
    )
    .where(OnboardingAssignment.tenant_id == self.tenant_id)
    .group_by(
        OnboardingTemplateStep.id,
        OnboardingTemplateStep.name,
        OnboardingTemplateStep.name_ar,
        OnboardingTemplateStep.order,
    )
    .order_by(OnboardingTemplateStep.order)
)
```
Compute `completion_rate_pct` in Python per step; sort by rate ascending to identify bottlenecks.

**Query 4 — Overdue steps count:**
```python
from datetime import datetime, timezone as tz

overdue_q = (
    select(func.count(OnboardingStepAssignment.id))
    .join(
        OnboardingAssignment,
        OnboardingStepAssignment.assignment_id == OnboardingAssignment.id,
    )
    .where(
        OnboardingAssignment.tenant_id == self.tenant_id,
        OnboardingAssignment.status == OnboardingAssignmentStatus.in_progress,
        OnboardingStepAssignment.status.in_([
            OnboardingStepStatus.pending,
            OnboardingStepStatus.in_progress,
        ]),
        OnboardingStepAssignment.due_date < datetime.now(tz.utc),
    )
)
```

#### Response Schema

```json
{
    "period_months": 6,
    "summary": {
        "total_assignments": 25,
        "completed": 18,
        "in_progress": 5,
        "cancelled": 2,
        "completion_rate_pct": 72.0
    },
    "completion_time": {
        "avg_days": 12.3,
        "min_days": 5.0,
        "max_days": 28.0
    },
    "overdue_steps": 7,
    "bottleneck_steps": [
        {
            "step_name": "IT Equipment Setup",
            "step_name_ar": "إعداد المعدات التقنية",
            "step_order": 3,
            "total_assignments": 25,
            "completed": 15,
            "completion_rate_pct": 60.0,
            "is_bottleneck": true
        },
        {
            "step_name": "Policy Acknowledgment",
            "step_name_ar": "الإقرار بالسياسات",
            "step_order": 5,
            "total_assignments": 25,
            "completed": 20,
            "completion_rate_pct": 80.0,
            "is_bottleneck": false
        }
    ],
    "department_breakdown": [
        {
            "department": "Engineering",
            "total": 8,
            "completed": 6,
            "in_progress": 2,
            "completion_rate_pct": 75.0
        }
    ]
}
```

#### Privacy & Security

- No employee names. Aggregated by step, department, status.
- k-anonymity on department_breakdown: suppress if total < MIN_GROUP_SIZE.
- Bottleneck step names come from the template (not PII).

#### Error Handling

- No assignments found: `{"message": "No onboarding assignments found for this period.", ...}`.
- No completed assignments: `completion_time` returns nulls.

#### Model Dependencies

- `OnboardingAssignment` -- has `tenant_id`, `employee_id`, `status`, `started_at`, `completed_at`. All present.
- `OnboardingStepAssignment` -- has `assignment_id`, `template_step_id`, `status`, `due_date`, `completed_at`, `order`. All present.
- `OnboardingTemplateStep` -- has `name`, `name_ar`, `order`. All present.
- **No missing fields.**

---

### A2-05: get_payroll_summary

#### Tool Definition

```json
{
    "name": "get_payroll_summary",
    "description": "Get payroll summary: monthly cost trends, gross/net/deductions totals, GOSI breakdown (employer 12% + employee 10%), department cost comparison, headcount vs cost. PRIVACY: k-anonymity enforced for small departments.",
    "input_schema": {
        "type": "object",
        "properties": {
            "department_id": {
                "type": "string",
                "description": "Optional department UUID to filter by"
            },
            "months": {
                "type": "integer",
                "description": "Lookback period in months (default 6, max 24)"
            }
        },
        "required": []
    }
}
```

#### Method Signature & Query Plan

```python
async def _get_payroll_summary(self, tool_input: dict) -> str:
```

**Tables:** `Payslip`, `Employee`, `Department`

**Tenant isolation:** `Payslip.tenant_id == self.tenant_id`.

**Compute year/month range from months parameter:**
```python
months = max(1, min(24, tool_input.get("months", 6)))
today = date.today()
# Build (year, month) pairs for the range
start_date = today - timedelta(days=months * 30)
start_year, start_month = start_date.year, start_date.month
```

**Query 1 — Aggregate totals:**
```python
total_q = (
    select(
        func.coalesce(func.sum(Payslip.gross_salary), 0).label("total_gross"),
        func.coalesce(func.sum(Payslip.total_deductions), 0).label("total_deductions"),
        func.coalesce(func.sum(Payslip.net_salary), 0).label("total_net"),
        func.coalesce(func.sum(Payslip.basic_salary), 0).label("total_basic"),
        func.coalesce(func.sum(Payslip.housing_allowance), 0).label("total_housing"),
        func.coalesce(func.sum(Payslip.transport_allowance), 0).label("total_transport"),
        func.coalesce(func.sum(Payslip.other_allowances), 0).label("total_other_allow"),
        func.coalesce(func.sum(Payslip.gosi_employee), 0).label("total_gosi_employee"),
        func.coalesce(func.sum(Payslip.absent_deduction), 0).label("total_absent_ded"),
        func.coalesce(func.sum(Payslip.other_deductions), 0).label("total_other_ded"),
        func.count(func.distinct(Payslip.employee_id)).label("unique_employees"),
        func.count(Payslip.id).label("payslip_count"),
    )
    .where(
        Payslip.tenant_id == self.tenant_id,
        # Year/month range filter (see helper below)
    )
)
```

Year/month filter helper (since Payslip stores year+month separately):
```python
# Use (year * 100 + month) for range comparison
payslip_ym = Payslip.year * 100 + Payslip.month
start_ym = start_year * 100 + start_month
end_ym = today.year * 100 + today.month
total_q = total_q.where(payslip_ym >= start_ym, payslip_ym <= end_ym)
```

If `department_id`:
```python
total_q = total_q.join(
    Employee, Payslip.employee_id == Employee.id
).where(Employee.department_id == department_id)
```

**Query 2 — Monthly trend:**
```python
monthly_q = (
    select(
        Payslip.year,
        Payslip.month,
        func.sum(Payslip.gross_salary).label("gross"),
        func.sum(Payslip.net_salary).label("net"),
        func.sum(Payslip.total_deductions).label("deductions"),
        func.count(func.distinct(Payslip.employee_id)).label("headcount"),
    )
    .where(
        Payslip.tenant_id == self.tenant_id,
        payslip_ym >= start_ym,
        payslip_ym <= end_ym,
    )
    .group_by(Payslip.year, Payslip.month)
    .order_by(Payslip.year, Payslip.month)
)
```

**Query 3 — Department comparison (k-anonymity enforced):**
```python
dept_q = (
    select(
        Department.name.label("dept_name"),
        Department.id.label("dept_id"),
        func.sum(Payslip.gross_salary).label("gross"),
        func.sum(Payslip.net_salary).label("net"),
        func.sum(Payslip.gosi_employee).label("gosi_employee"),
        func.count(func.distinct(Payslip.employee_id)).label("headcount"),
    )
    .join(Employee, Payslip.employee_id == Employee.id)
    .join(Department, Employee.department_id == Department.id)
    .where(
        Payslip.tenant_id == self.tenant_id,
        payslip_ym >= start_ym,
        payslip_ym <= end_ym,
    )
    .group_by(Department.id, Department.name)
)
```

**GOSI calculation (in Python):**
```python
# GOSI rates for Saudi employees (2026):
# - Employee contribution: 10% of basic salary (9.75% pension + 0.25% SANED)
# - Employer contribution: 12% of basic salary (9.75% pension + 1% occupational hazard + 1.25% SANED)
# The Payslip.gosi_employee column stores the employee's share.
# Employer share is estimated as: total_basic * 0.12 (since employer pays 12%)
# This is an estimate — actual GOSI billing may differ slightly.
gosi_employer_estimate = total_basic * 12 // 100
gosi_total = total_gosi_employee + gosi_employer_estimate
```

#### Response Schema

```json
{
    "period_months": 6,
    "totals": {
        "gross_salary_sar": 4500000,
        "net_salary_sar": 3825000,
        "total_deductions_sar": 675000,
        "basic_salary_sar": 3000000,
        "housing_allowance_sar": 750000,
        "transport_allowance_sar": 375000,
        "other_allowances_sar": 375000,
        "unique_employees": 75,
        "payslip_count": 450
    },
    "gosi_breakdown": {
        "employee_contribution_sar": 300000,
        "employer_contribution_estimated_sar": 360000,
        "total_gosi_estimated_sar": 660000,
        "note": "Employee 10% + Employer 12% of basic salary. Employer share is estimated."
    },
    "deductions_breakdown": {
        "gosi_employee_sar": 300000,
        "absent_deduction_sar": 25000,
        "other_deductions_sar": 350000
    },
    "monthly_trend": [
        {
            "year": 2025,
            "month": 10,
            "month_name": "October",
            "gross_sar": 750000,
            "net_sar": 637500,
            "deductions_sar": 112500,
            "headcount": 75
        }
    ],
    "department_comparison": [
        {
            "department": "Engineering",
            "department_id": "uuid",
            "gross_sar": 1200000,
            "net_sar": 1020000,
            "gosi_employee_sar": 80000,
            "headcount": 20,
            "avg_gross_per_employee_sar": 60000
        }
    ],
    "privacy_note": "Aggregated payroll data. Departments with fewer than 5 employees have details suppressed."
}
```

#### Privacy & Security

- **k-anonymity**: Department comparison entries where `headcount < MIN_GROUP_SIZE` get their monetary values replaced with `"note": "Suppressed — fewer than 5 employees (privacy threshold)."` (same pattern as A1 salary_distribution).
- No individual payslip records. All aggregated.
- GOSI employer share is an estimate (not pulled from a billing system).

#### Error Handling

- No payslips found: `{"message": "No payroll data found for this period.", ...}`.
- Invalid department: caught by dispatcher.

#### Model Dependencies

- `Payslip` -- has `tenant_id`, `employee_id`, `year`, `month`, all salary/deduction fields, `gross_salary`, `net_salary`, `total_deductions`. All present.
- **No missing fields.**

---

### Updated `get_tools()` and `handle_tool_call()` Additions

The five new tools append to the existing `get_tools()` list. The `handle_tool_call()` method adds five new `elif` branches following the existing pattern:

```python
elif tool_name == "get_recruitment_analytics":
    return await self._get_recruitment_analytics(tool_input)
elif tool_name == "get_leave_analytics":
    return await self._get_leave_analytics(tool_input)
elif tool_name == "get_attendance_analytics":
    return await self._get_attendance_analytics(tool_input)
elif tool_name == "get_onboarding_analytics":
    return await self._get_onboarding_analytics(tool_input)
elif tool_name == "get_payroll_summary":
    return await self._get_payroll_summary(tool_input)
```

### Updated `_get_scope_rules()` Addition

Add to Ahmad's scope rules:
```python
"8. Recruitment pipeline analytics (funnel, time-to-fill, AI match scores)\n"
"9. Leave analytics (usage by type, department comparison, seasonal patterns)\n"
"10. Attendance analytics (rates, overtime, day-of-week patterns)\n"
"11. Onboarding health (completion rates, bottleneck steps, overdue tasks)\n"
"12. Payroll summaries (cost trends, GOSI breakdown, department comparison)\n"
```

### Updated Orchestrator Keywords

Add to Ahmad's `INTENT_KEYWORDS` in the orchestrator:
```python
# A2 keywords (already partially listed in existing config)
"recruitment funnel", "time to fill", "hiring analytics",
"leave trends", "leave analytics", "leave usage",
"attendance rate", "overtime analytics", "late arrivals",
"onboarding progress", "onboarding completion", "bottleneck steps",
"payroll cost", "payroll trend", "gosi breakdown",
"تحليل التوظيف", "تحليل الإجازات", "تحليل الحضور",
"تكلفة الرواتب", "تحليل التأهيل",
```

---

## Track 2: Conversational UX

### CUX-01: Suggestions API

#### Endpoint Definition

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/v1/suggestions` | JWT (chat token) | Get contextual suggestions for an employee |

#### Request Schema

Query parameters (no request body for GET):
```
employee_id: UUID (from JWT — not a query param, extracted from token)
language: str = "ar" (optional query param, default from employee record)
```

#### Implementation: New File `backend/app/api/suggestions.py`

```python
router = APIRouter(prefix="/suggestions", tags=["suggestions"])

class Suggestion(BaseModel):
    text: str           # Display text in detected/requested language
    text_ar: str        # Arabic version
    text_en: str        # English version
    agent_target: str   # Which agent handles this (e.g., "deema", "ahmad")
    action_type: str    # "query" | "action" | "status_check"
    priority: int       # 1=high, 2=medium, 3=low (for ordering)
    icon: str           # Emoji for frontend rendering

class SuggestionsResponse(BaseModel):
    suggestions: list[Suggestion]
    generated_at: str   # ISO timestamp
```

#### Rule Engine Architecture

The rule engine evaluates rules in priority order and collects up to 6 suggestions. Rules are functions that receive context and return 0-N suggestions.

```python
class SuggestionContext:
    employee_id: UUID
    tenant_id: UUID
    language: str
    now: datetime          # Current time in Asia/Riyadh
    today: date
    day_of_week: int       # 0=Mon, 6=Sun
    is_ramadan: bool
    is_near_eid: bool
    pending_leave_count: int
    incomplete_onboarding_steps: int
    recent_agent: str | None    # Last agent the employee spoke with
    employee_role: str          # job_title for role-based rules
    is_manager: bool            # Has direct reports
```

**Rule Categories:**

1. **Pending-item rules** (priority 1 — highest):
```python
async def _rule_pending_leaves(ctx, db) -> list[Suggestion]:
    """If employee has pending leave requests, suggest checking status."""
    count = await db.scalar(
        select(func.count(LeaveRequest.id))
        .where(
            LeaveRequest.employee_id == ctx.employee_id,
            LeaveRequest.status == LeaveStatus.pending,
        )
    )
    if count > 0:
        return [Suggestion(
            text_en=f"Check {count} pending leave request(s)",
            text_ar=f"تحقق من {count} طلب(ات) إجازة معلقة",
            agent_target="deema",
            action_type="status_check",
            priority=1,
            icon="📋",
        )]
    return []

async def _rule_incomplete_onboarding(ctx, db) -> list[Suggestion]:
    """If employee has in-progress onboarding, suggest continuing."""
    count = await db.scalar(
        select(func.count(OnboardingStepAssignment.id))
        .join(OnboardingAssignment, ...)
        .where(
            OnboardingAssignment.employee_id == ctx.employee_id,
            OnboardingAssignment.status == OnboardingAssignmentStatus.in_progress,
            OnboardingStepAssignment.status.in_([
                OnboardingStepStatus.pending, OnboardingStepStatus.in_progress,
            ]),
        )
    )
    if count > 0:
        return [Suggestion(
            text_en=f"Continue onboarding ({count} steps remaining)",
            text_ar=f"أكمل التأهيل ({count} خطوات متبقية)",
            agent_target="waleed",
            action_type="action",
            priority=1,
            icon="🚀",
        )]
    return []
```

2. **Time-based rules** (priority 2):
```python
async def _rule_morning_greeting(ctx, db) -> list[Suggestion]:
    """Morning: suggest checking today's schedule / leave balance."""
    if ctx.now.hour < 10:
        return [Suggestion(
            text_en="Check my leave balance",
            text_ar="رصيد إجازاتي",
            agent_target="deema",
            action_type="query",
            priority=2,
            icon="📅",
        )]
    return []

async def _rule_end_of_month(ctx, db) -> list[Suggestion]:
    """Last 3 days of month: suggest payslip check."""
    if ctx.today.day >= 28:
        return [Suggestion(
            text_en="View my latest payslip",
            text_ar="عرض كشف الراتب",
            agent_target="deema",
            action_type="query",
            priority=2,
            icon="💰",
        )]
    return []
```

3. **Seasonal rules** (priority 2):
```python
async def _rule_ramadan(ctx, db) -> list[Suggestion]:
    """During Ramadan, suggest checking Ramadan work schedule."""
    if ctx.is_ramadan:
        return [Suggestion(
            text_en="What are Ramadan working hours?",
            text_ar="ما هي ساعات العمل في رمضان؟",
            agent_target="deema",
            action_type="query",
            priority=2,
            icon="🌙",
        )]
    return []

async def _rule_hajj_season(ctx, db) -> list[Suggestion]:
    """Near Hajj season, suggest Hajj leave info."""
    # Check if within 45 days of Eid Al-Adha
    # ...
```

4. **Role-based rules** (priority 3):
```python
async def _rule_manager_dashboard(ctx, db) -> list[Suggestion]:
    """Managers get team-related suggestions."""
    if ctx.is_manager:
        return [
            Suggestion(
                text_en="Team leave requests",
                text_ar="طلبات إجازات الفريق",
                agent_target="waleed",
                action_type="query",
                priority=3,
                icon="👥",
            ),
            Suggestion(
                text_en="Workforce overview",
                text_ar="نظرة عامة على القوى العاملة",
                agent_target="ahmad",
                action_type="query",
                priority=3,
                icon="📊",
            ),
        ]
    return []
```

5. **Fallback rules** (priority 3 — always available):
```python
async def _rule_defaults(ctx, db) -> list[Suggestion]:
    """Default suggestions when nothing else applies."""
    return [
        Suggestion(
            text_en="Company leave policy",
            text_ar="سياسة الإجازات",
            agent_target="deema",
            action_type="query",
            priority=3,
            icon="📋",
        ),
    ]
```

**Query plan:** The endpoint runs up to 3 DB queries in parallel (pending leaves, incomplete onboarding, recent conversation) then evaluates rules synchronously. Total latency target: <100ms.

```python
@router.get("", response_model=SuggestionsResponse)
async def get_suggestions(
    db: AsyncSession = Depends(get_db),
    chat_emp: ChatEmployee = Depends(get_chat_employee),
    language: str = Query(default=""),
):
    # Build context (parallel DB queries)
    # Run rules in priority order
    # Collect up to 6 suggestions, deduplicate by text
    # Return sorted by priority
```

#### Error Handling

- Unauthenticated: 401 (handled by `get_chat_employee` dependency).
- Employee not found: 404.
- DB errors: return empty suggestions list with 200 (non-critical endpoint; frontend falls back to static suggestions).

#### Dependencies

- Queries: `LeaveRequest`, `OnboardingAssignment`, `OnboardingStepAssignment`, `Conversation`, `Employee`.
- Uses `app.saudi_holidays` for seasonal detection.
- **No new models or tables needed.**

---

### CUX-02: Follow-Up Chips

#### Design

Extend `ChatResponse` with an optional `suggestions` field, and add a `_generate_suggestions()` method to `BaseAgent`.

**Current frontend already handles this.** The frontend's `extractSuggestions()` function parses numbered lists from the end of agent messages. The system prompt already instructs agents to append 1-3 numbered suggestions. This feature **formalizes** it as structured data rather than relying on text parsing.

#### ChatResponse Change

```python
class ChatResponse(BaseModel):
    agent: str
    response: str
    conversation_id: str
    topic: str = ""
    suggestions: list[str] = []  # NEW — follow-up chip texts
```

#### BaseAgent Addition

```python
# In BaseAgent class:

def _generate_suggestions(
    self, tool_name: str, tool_result: dict, language: str = "ar"
) -> list[str]:
    """Generate follow-up suggestions based on the last tool call.

    Override in subclasses for domain-specific suggestions.
    Returns up to 3 short strings (< 60 chars each).
    Default: empty list (falls back to LLM-generated suggestions in text).
    """
    return []
```

**Important design decision:** The LLM already generates suggestions as numbered lists in its response text. The `_generate_suggestions` method provides a **deterministic fallback/override** when the LLM output does not include suggestions or when we want guaranteed suggestions for specific tool results. The structured `suggestions` field in ChatResponse gives the frontend structured data instead of relying on regex parsing.

#### Integration in `respond()` method

After the tool loop completes and we have the final text response:
```python
# In BaseAgent.respond(), after extracting final text:
suggestions = []

# Try to extract from the last tool call result (deterministic)
if last_tool_name and last_tool_result:
    suggestions = self._generate_suggestions(
        last_tool_name,
        json.loads(last_tool_result) if isinstance(last_tool_result, str) else last_tool_result,
        language,
    )

# Return suggestions alongside the response text
# The caller (chat.py) adds them to ChatResponse
return raw_text, suggestions  # Change return type from str to tuple
```

**Breaking change note:** `respond()` currently returns `str`. Changing to `tuple[str, list[str]]` requires updating the call site in `chat.py` and `orchestrator.py`. An alternative is to store suggestions as an instance attribute (`self._last_suggestions`) that the caller reads after `respond()` returns — this avoids changing the return type.

**Recommended approach: Instance attribute** (less invasive):

```python
# In BaseAgent.__init__:
self._last_suggestions: list[str] = []

# In BaseAgent.respond(), after tool loop:
if last_tool_name and last_tool_result:
    self._last_suggestions = self._generate_suggestions(...)

# In chat.py, after orchestrator.handle_message():
agent_instance = orchestrator.last_agent  # Need to expose this
suggestions = agent_instance._last_suggestions if agent_instance else []
```

#### Ahmad-Specific Overrides

```python
# In AhmadAgent:

def _generate_suggestions(self, tool_name: str, tool_result: dict, language: str = "ar") -> list[str]:
    ar = language == "ar"
    suggestions = {
        "get_headcount_summary": [
            "عرض وضع السعودة" if ar else "Show Saudization status",
            "ميزانية القسم" if ar else "Department budget",
            "عرض توزيع الرواتب" if ar else "Salary distribution",
        ],
        "get_saudization_status": [
            "ملخص القوى العاملة" if ar else "Workforce overview",
            "عرض معدل الدوران" if ar else "Show turnover metrics",
            "وضع الامتثال" if ar else "Compliance status",
        ],
        "get_turnover_metrics": [
            "ملخص عدد الموظفين" if ar else "Headcount summary",
            "تحليل الحضور" if ar else "Attendance analytics",
            "ملخص الرواتب" if ar else "Payroll summary",
        ],
        "get_salary_distribution": [
            "ميزانية القسم" if ar else "Department budget",
            "ملخص الرواتب" if ar else "Payroll summary",
            "وضع السعودة" if ar else "Saudization status",
        ],
        "get_recruitment_analytics": [
            "ملخص عدد الموظفين" if ar else "Headcount summary",
            "تحليل التأهيل" if ar else "Onboarding analytics",
            "معدل الدوران" if ar else "Turnover metrics",
        ],
        "get_leave_analytics": [
            "تحليل الحضور" if ar else "Attendance analytics",
            "ملخص القوى العاملة" if ar else "Workforce overview",
            "ملخص عدد الموظفين" if ar else "Headcount summary",
        ],
        "get_attendance_analytics": [
            "تحليل الإجازات" if ar else "Leave analytics",
            "ملخص عدد الموظفين" if ar else "Headcount summary",
            "تحليل التأهيل" if ar else "Onboarding analytics",
        ],
        "get_onboarding_analytics": [
            "تحليل التوظيف" if ar else "Recruitment analytics",
            "ملخص عدد الموظفين" if ar else "Headcount summary",
            "معدل الدوران" if ar else "Turnover metrics",
        ],
        "get_payroll_summary": [
            "ميزانية القسم" if ar else "Department budget",
            "توزيع الرواتب" if ar else "Salary distribution",
            "وضع الامتثال" if ar else "Compliance status",
        ],
    }
    return suggestions.get(tool_name, [])[:3]
```

#### Frontend Change

In `chat.html`, after receiving `ChatResponse`:
```javascript
// If structured suggestions are available, prefer them over text extraction
if (data.suggestions && data.suggestions.length > 0) {
    // Render as suggestion chips (using existing .msg-suggestions pattern)
    renderSuggestionChips(data.suggestions);
} else {
    // Fall back to existing extractSuggestions() from response text
    const suggestions = extractSuggestions(data.response);
    if (suggestions.length > 0) renderSuggestionChips(suggestions);
}
```

---

### CUX-03: Quick Actions Bar

#### Design

The quick actions bar already exists in `chat.html` (hardcoded 4 buttons). This feature makes it:
1. **Role-based** — managers see team actions, employees see self-service actions
2. **Configurable** — served from backend so changes don't require frontend deploy
3. **Language-aware** — labels switch with selected language

#### Approach: Static Config Endpoint

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/v1/quick-actions` | JWT | Get role-based quick actions |

#### Response Schema

```python
class QuickAction(BaseModel):
    label: str       # Display label (language-appropriate)
    label_ar: str
    label_en: str
    message: str     # The message to send when clicked
    agent: str       # Target agent hint (optional, for routing)
    icon: str        # Emoji
    category: str    # "self_service" | "team" | "analytics"

class QuickActionsResponse(BaseModel):
    actions: list[QuickAction]
```

#### Role-Based Configuration

```python
# In backend/app/api/suggestions.py (same file as CUX-01)

QUICK_ACTIONS_EMPLOYEE = [
    QuickAction(
        label_en="Leave Balance", label_ar="رصيد الإجازات",
        message="What is my leave balance?",
        agent="deema", icon="📅", category="self_service",
    ),
    QuickAction(
        label_en="Request Leave", label_ar="طلب إجازة",
        message="I want to request a vacation",
        agent="deema", icon="🏖️", category="self_service",
    ),
    QuickAction(
        label_en="My Info", label_ar="معلوماتي",
        message="Show me my employee information",
        agent="deema", icon="👤", category="self_service",
    ),
    QuickAction(
        label_en="Company Policy", label_ar="سياسة الشركة",
        message="What is the company leave policy?",
        agent="deema", icon="📋", category="self_service",
    ),
    QuickAction(
        label_en="My Payslip", label_ar="كشف الراتب",
        message="Show my latest payslip",
        agent="deema", icon="💰", category="self_service",
    ),
]

QUICK_ACTIONS_MANAGER = QUICK_ACTIONS_EMPLOYEE + [
    QuickAction(
        label_en="Team Overview", label_ar="نظرة على الفريق",
        message="Show my team overview",
        agent="waleed", icon="👥", category="team",
    ),
    QuickAction(
        label_en="Pending Approvals", label_ar="الموافقات المعلقة",
        message="Show pending leave requests for my team",
        agent="waleed", icon="✅", category="team",
    ),
    QuickAction(
        label_en="HR Dashboard", label_ar="لوحة الموارد البشرية",
        message="Give me a workforce overview",
        agent="ahmad", icon="📊", category="analytics",
    ),
]
```

#### Endpoint Implementation

```python
@router.get("/quick-actions", response_model=QuickActionsResponse)
async def get_quick_actions(
    db: AsyncSession = Depends(get_db),
    chat_emp: ChatEmployee = Depends(get_chat_employee),
):
    # Determine if employee is a manager
    emp_result = await db.execute(
        select(Employee).where(
            Employee.id == chat_emp.employee_id,
            Employee.tenant_id == chat_emp.tenant_id,
        )
    )
    employee = emp_result.scalar_one_or_none()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Check if this employee manages anyone
    mgr_result = await db.execute(
        select(func.count(Employee.id)).where(
            Employee.manager_id == employee.id,
            Employee.tenant_id == chat_emp.tenant_id,
            Employee.status.in_([EmployeeStatus.active, EmployeeStatus.onboarding]),
        )
    )
    is_manager = (mgr_result.scalar() or 0) > 0

    actions = QUICK_ACTIONS_MANAGER if is_manager else QUICK_ACTIONS_EMPLOYEE

    # Set display label based on employee language
    lang = employee.preferred_language
    for a in actions:
        a.label = a.label_ar if lang == "ar" else a.label_en
        a.message = a.message  # Messages stay in English (agents handle both)

    return QuickActionsResponse(actions=actions)
```

#### Frontend Changes

Replace the hardcoded `quickActions` div with dynamic rendering:

```javascript
async function loadQuickActions() {
    try {
        const resp = await fetch('/api/v1/quick-actions', {
            headers: {'Authorization': `Bearer ${authToken}`},
        });
        if (!resp.ok) return;
        const data = await resp.json();

        const container = document.getElementById('quickActions');
        container.innerHTML = '';

        data.actions.forEach(action => {
            const btn = document.createElement('button');
            btn.className = 'quick-btn';
            btn.onclick = () => sendQuickMessage(action.message);

            const icon = document.createElement('span');
            icon.className = 'qb-icon';
            icon.textContent = action.icon;

            const label = selectedLanguage === 'ar' ? action.label_ar : action.label_en;
            btn.appendChild(icon);
            btn.appendChild(document.createTextNode(' ' + label));
            container.appendChild(btn);
        });

        container.classList.remove('hidden');
    } catch (e) {
        // Fall back to showing hardcoded buttons
        document.getElementById('quickActions').classList.remove('hidden');
    }
}

// Call after login/employee selection
loadQuickActions();
```

---

## Database Migration Notes

### Track 1 (Ahmad A2): NO MIGRATION NEEDED

Ahmad A2 tools are pure readers of existing tables. All required tables, columns, and relationships already exist:

| Table | Fields Used | Status |
|-------|-------------|--------|
| `job_postings` | id, tenant_id, department_id, status, created_at | Exists |
| `candidates` | id, job_posting_id, stage, ai_match_score, created_at | Exists |
| `leave_requests` | id, employee_id, leave_type, business_days, status, start_date, created_at | Exists |
| `leave_balances` | id, employee_id, leave_type, year, total_days, used_days | Exists |
| `attendance_records` | id, tenant_id, employee_id, date, status, overtime_hours | Exists |
| `onboarding_assignments` | id, tenant_id, employee_id, status, started_at, completed_at | Exists |
| `onboarding_step_assignments` | id, assignment_id, template_step_id, status, due_date, order | Exists |
| `onboarding_template_steps` | id, name, name_ar, order | Exists |
| `payslips` | id, tenant_id, employee_id, year, month, all salary/deduction fields | Exists |

### Track 2 (CUX): NO MIGRATION NEEDED

All three CUX features query existing tables. No new tables or columns required.

### Recommended Index Additions (Performance)

These are **optional** indexes for query performance as data grows. Not blocking for Sprint 7 delivery:

```sql
-- A2-02: Leave analytics frequently filters by status + date
CREATE INDEX IF NOT EXISTS ix_leave_requests_status_start
ON leave_requests (status, start_date);

-- A2-03: Attendance analytics frequently filters by tenant + date range
-- Already exists: ix_attendance_tenant_date (tenant_id, date)

-- A2-05: Payroll queries by year/month range
CREATE INDEX IF NOT EXISTS ix_payslips_tenant_year_month
ON payslips (tenant_id, year, month);
```

---

## Integration Matrix

### Which agents/services each feature touches

| Feature | Reads From | Writes To | Agent Impact | API Impact |
|---------|-----------|-----------|-------------|------------|
| A2-01 | JobPosting, Candidate | None | Ahmad only | None |
| A2-02 | LeaveRequest, LeaveBalance, Employee, Department | None | Ahmad only | None |
| A2-03 | AttendanceRecord, Employee, Department | None | Ahmad only | None |
| A2-04 | OnboardingAssignment, OnboardingStepAssignment, OnboardingTemplateStep, Employee, Department | None | Ahmad only | None |
| A2-05 | Payslip, Employee, Department | None | Ahmad only | None |
| CUX-01 | LeaveRequest, OnboardingAssignment, OnboardingStepAssignment, Conversation, Employee | None | None | New endpoint |
| CUX-02 | None (uses tool results in memory) | None | All agents (BaseAgent change) | ChatResponse schema change |
| CUX-03 | Employee (manager check) | None | None | New endpoint |

### Data Flow

```
Track 1 — Ahmad A2 Tool Call Flow:
┌──────────┐     ┌──────────────┐     ┌──────────┐     ┌──────────┐
│ Employee  │────>│ Orchestrator │────>│  Ahmad   │────>│ Database │
│ (Chat UI) │     │  (routing)   │     │ (agent)  │     │ (SELECT) │
└──────────┘     └──────────────┘     └──────────┘     └──────────┘
                                            │
                                            ▼
                                      ┌──────────┐
                                      │  Claude  │ (formats response)
                                      │  (LLM)   │
                                      └──────────┘

Track 2 — CUX Suggestions Flow:
┌──────────┐     ┌──────────────────┐     ┌──────────┐
│ Frontend  │────>│ GET /suggestions │────>│ Database │
│ (on load) │     │ (rule engine)    │     │ (3 queries)
└──────────┘     └──────────────────┘     └──────────┘
      │
      ▼
┌──────────────────┐     ┌──────────┐
│ POST /chat       │────>│ Agent    │─���── suggestions in ChatResponse
│ (with selected   │     │ respond()│
│  suggestion)     │     └──────────┘
└──────────────────┘
```

---

## Open Questions

### For the CTO:

1. **CUX-02 return type change**: Should `BaseAgent.respond()` return a tuple `(str, list[str])` (cleaner but breaking change to all callers), or store suggestions as an instance attribute `self._last_suggestions` (non-breaking but slightly less clean)? **My recommendation: instance attribute** — less risk, same functionality.

2. **CUX-01 caching**: Should suggestions be cached in Redis (TTL 5 minutes) to avoid DB queries on every page load, or is direct DB query acceptable given the low volume (max 3 parallel queries, all indexed)?

3. **A2-05 GOSI employer share**: The Payslip model only stores the employee's GOSI contribution. The employer's 12% share is estimated from `basic_salary * 0.12`. Should we add a `gosi_employer` column to the Payslip model for exact tracking, or is the estimate sufficient for analytics? **My recommendation: estimate is fine for now** — adding the column is a migration we can do in a future sprint when payroll integration is built.

4. **Performance index migration**: Should the two recommended indexes (leave_requests, payslips) be added in Sprint 7 or deferred until we observe actual query performance? **My recommendation: add them** — they are additive-only and low risk.

5. **Quick actions extensibility**: The current design uses a Python dict for role-based quick actions. Should we move this to a database table (`quick_action_configs`) for tenant-level customization in a future sprint, or is the hardcoded approach acceptable for now?

---

## Files to Create/Modify

### New Files
| File | Purpose |
|------|---------|
| `backend/app/api/suggestions.py` | CUX-01 and CUX-03 endpoints |

### Modified Files
| File | Changes |
|------|---------|
| `backend/app/agents/ahmad.py` | Add 5 tool definitions, 5 handler methods, new imports, updated scope rules |
| `backend/app/agents/base.py` | Add `_generate_suggestions()` method and `_last_suggestions` attribute |
| `backend/app/api/chat.py` | Add `suggestions` field to `ChatResponse`, populate from agent |
| `backend/app/api/__init__.py` or router registration | Register new suggestions router |
| `backend/app/agents/orchestrator.py` | Expose `last_agent` reference; add A2 keywords |
| `backend/static/chat.html` | Dynamic quick actions loading, structured suggestions rendering |

### No Changes Needed
| File | Reason |
|------|--------|
| All model files | No new tables or columns |
| Migration files | No schema changes |
| Other agent files | A2 tools are Ahmad-only; CUX-02 BaseAgent change is backward-compatible (default returns []) |
