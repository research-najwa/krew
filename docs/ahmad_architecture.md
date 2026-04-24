# Technical Architecture: Ahmad -- CHRO Agent

**Author:** Faisal (System Architect)
**Date:** 2026-03-26
**Status:** Ready for Implementation
**Input:** Tariq's plan (`docs/norah_plan.md`)
**Supersedes:** `norah.py` (NorahAgent), `sarah.py` (SarahAgent)

---

## 1. Agent Identity & Registration

### Class Definition

```python
# File: backend/app/agents/ahmad.py (NEW)
class AhmadAgent(BaseAgent):
    name = "Ahmad"
    name_ar = "أحمد"
    role = "CHRO"
    division = "Analytics, Finance & Compliance"
    personality = (
        "Strategic, data-driven, authoritative but approachable. You speak in executive summaries. "
        "You always lead with the headline number, then supporting breakdown, then recommendations. "
        "You back every claim with data and frame compliance as a business enabler, not a burden. "
        "You connect the dots between metrics and business impact."
    )
```

### Orchestrator Registration

**Key:** `"ahmad"`

**INTENT_KEYWORDS for ahmad** (merges norah + sarah keywords, expanded):
```python
"ahmad": [
    # Analytics (from norah)
    "budget", "cost", "analytics", "forecast", "turnover",
    "ميزانية", "تكلفة", "تحليل",
    # Compliance (from sarah)
    "compliance", "regulation", "labor law", "audit", "policy update",
    "امتثال", "نظام", "قانون",
    # New CHRO keywords
    "headcount", "saudization", "nitaqat", "gosi", "attrition",
    "salary distribution", "pay equity", "workforce overview",
    "payroll", "attendance analytics", "onboarding analytics",
    "recruitment analytics", "leave analytics", "hr report",
    "executive summary", "board report", "kpi",
    "توطين", "نطاقات", "تأمينات", "إحصائيات", "تقرير",
    "معدل دوران", "رواتب", "ملخص تنفيذي",
],
```

**SWITCH_PHRASES for ahmad:**
```python
"ahmad": ["أحمد", "ahmad", "حول لأحمد", "كلم أحمد", "switch to ahmad", "talk to ahmad"],
```

### Handling "norah" and "sarah" Keys

**Decision: Remove both keys entirely. Add backward-compatibility aliases in SWITCH_PHRASES only.**

- Remove `"norah"` and `"sarah"` from `AGENTS`, `INTENT_KEYWORDS`, and `SWITCH_PHRASES`.
- Add legacy aliases inside Ahmad's SWITCH_PHRASES so existing users who type "norah" or "sarah" get routed to Ahmad:

```python
"ahmad": [
    "أحمد", "ahmad", "حول لأحمد", "كلم أحمد", "switch to ahmad", "talk to ahmad",
    # Legacy aliases for backward compatibility
    "norah", "نورة", "حول لنورة", "كلم نورة", "switch to norah", "talk to norah",
    "sarah", "سارة", "حول لسارة", "كلم سارة", "switch to sarah", "talk to sarah",
],
```

- The `"headcount"` keyword currently belongs to waleed. It must **stay with waleed** since Waleed's `get_team_headcount` is manager-specific team headcount. Ahmad's `get_headcount_summary` is org-wide analytics headcount. The routing difference is:
  - A manager asking "headcount" in a Waleed conversation stays with Waleed (sticky routing).
  - An executive starting a fresh conversation saying "headcount analytics" or "عدد الموظفين بالتفصيل" routes to Ahmad via the expanded keyword list.
  - To avoid conflict, Ahmad uses `"headcount breakdown"`, `"headcount dashboard"`, `"headcount summary"` as keywords, NOT bare `"headcount"`.

**Updated Ahmad keywords (conflict-free):**
```python
"ahmad": [
    # Analytics (from norah)
    "budget", "cost", "analytics", "forecast", "turnover",
    "ميزانية", "تكلفة", "تحليل",
    # Compliance (from sarah)
    "compliance", "regulation", "labor law", "audit", "policy update",
    "امتثال", "نظام", "قانون",
    # New CHRO keywords (no conflicts with other agents)
    "saudization", "nitaqat", "gosi", "attrition",
    "salary distribution", "pay equity", "workforce overview",
    "payroll summary", "attendance analytics", "onboarding analytics",
    "recruitment analytics", "leave analytics", "hr report",
    "executive summary", "board report", "kpi",
    "headcount breakdown", "headcount dashboard", "headcount summary",
    "توطين", "نطاقات", "تأمينات", "إحصائيات", "تقرير",
    "معدل دوران", "ملخص تنفيذي",
    "compliance status", "gosi compliance", "policy acknowledgment",
    "budget forecast", "attrition risk", "custom report",
    "وضع الامتثال", "تقرير مخصص", "توقعات الميزانية",
],
```

---

## 2. Data Model Inventory

Ahmad creates NO new tables. He is a pure reader of existing models. Below is every tool mapped to exact query patterns.

### Tool 1: `get_headcount_summary` (A1-01)

**Tables:** `Employee`, `Department`

**Query Pattern:**
```python
from sqlalchemy import select, func, case

# Base query: active employees for this tenant
base = select(Employee).where(
    Employee.tenant_id == self.tenant_id,
    Employee.status != EmployeeStatus.terminated,
)

# Total active count
total_q = select(func.count(Employee.id)).where(
    Employee.tenant_id == self.tenant_id,
    Employee.status != EmployeeStatus.terminated,
)

# Group by department
dept_q = (
    select(
        Department.name,
        Department.id,
        func.count(Employee.id).label("count"),
    )
    .join(Department, Employee.department_id == Department.id)
    .where(
        Employee.tenant_id == self.tenant_id,
        Employee.status != EmployeeStatus.terminated,
    )
    .group_by(Department.name, Department.id)
)

# Group by gender
gender_q = (
    select(
        Employee.gender,
        func.count(Employee.id).label("count"),
    )
    .where(
        Employee.tenant_id == self.tenant_id,
        Employee.status != EmployeeStatus.terminated,
    )
    .group_by(Employee.gender)
)

# Group by nationality (is_saudi)
nationality_q = (
    select(
        Employee.is_saudi,
        func.count(Employee.id).label("count"),
    )
    .where(
        Employee.tenant_id == self.tenant_id,
        Employee.status != EmployeeStatus.terminated,
    )
    .group_by(Employee.is_saudi)
)

# Group by contract_type, work_mode, status -- same pattern

# 30-day comparison: count employees who were active 30 days ago
# (hire_date <= 30_days_ago AND (end_date IS NULL OR end_date > 30_days_ago))
thirty_days_ago = date.today() - timedelta(days=30)
prev_q = select(func.count(Employee.id)).where(
    Employee.tenant_id == self.tenant_id,
    Employee.hire_date <= thirty_days_ago,
    (Employee.end_date.is_(None)) | (Employee.end_date > thirty_days_ago),
    Employee.status != EmployeeStatus.terminated,
)

# Terminated count (separate)
terminated_q = select(func.count(Employee.id)).where(
    Employee.tenant_id == self.tenant_id,
    Employee.status == EmployeeStatus.terminated,
)
```

**Fields used:** `Employee.id`, `Employee.tenant_id`, `Employee.status`, `Employee.department_id`, `Employee.gender`, `Employee.is_saudi`, `Employee.contract_type`, `Employee.work_mode`, `Employee.hire_date`, `Employee.end_date`; `Department.id`, `Department.name`

**Tenant isolation:** `Employee.tenant_id == self.tenant_id` on every query.

**Privacy:** Aggregated counts only. No names, IDs, or individual records returned.

---

### Tool 2: `get_saudization_status` (A1-02)

**Tables:** `Employee`, `NitaqatConfig`

**Query Pattern:**
```python
# Saudi/non-Saudi counts
saudi_q = (
    select(
        Employee.is_saudi,
        func.count(Employee.id).label("count"),
    )
    .where(
        Employee.tenant_id == self.tenant_id,
        Employee.status.in_([EmployeeStatus.active, EmployeeStatus.on_leave]),
    )
    .group_by(Employee.is_saudi)
)
# Optional department filter: .where(Employee.department_id == dept_id)

# NitaqatConfig lookup
config_q = select(NitaqatConfig).where(NitaqatConfig.tenant_id == self.tenant_id)

# Band determination (in Python after fetching config):
# if pct >= config.platinum_threshold: band = "platinum"
# elif pct >= config.green_high_threshold: band = "green_high"
# elif pct >= config.green_low_threshold: band = "green_low"
# elif pct >= config.yellow_threshold: band = "yellow"
# else: band = "red"

# Trend (if include_trend=True): monthly snapshots using hire_date/end_date window
# For each of last 6 months, count employees active as of that month-end
```

**Fields used:** `Employee.id`, `Employee.tenant_id`, `Employee.is_saudi`, `Employee.status`, `Employee.hire_date`, `Employee.end_date`, `Employee.department_id`; `NitaqatConfig.tenant_id`, `NitaqatConfig.platinum_threshold`, `NitaqatConfig.green_high_threshold`, `NitaqatConfig.green_low_threshold`, `NitaqatConfig.yellow_threshold`, `NitaqatConfig.target_saudization_pct`, `NitaqatConfig.alert_buffer_pct`, `NitaqatConfig.industry`, `NitaqatConfig.size_category`

**Tenant isolation:** Both Employee and NitaqatConfig filtered by `tenant_id`.

**Privacy:** Only aggregate counts. No individual employee data.

---

### Tool 3: `get_turnover_metrics` (A1-03)

**Tables:** `Employee`, `Department`

**Query Pattern:**
```python
# Terminated employees in the date range
terminated_q = (
    select(
        func.count(Employee.id).label("terminations"),
        Employee.department_id,
    )
    .where(
        Employee.tenant_id == self.tenant_id,
        Employee.status == EmployeeStatus.terminated,
        Employee.end_date >= start_date,
        Employee.end_date <= end_date,
    )
    .group_by(Employee.department_id)
)

# Average headcount for the period (start + end / 2 per sub-period)
# Start headcount: active as of start_date
start_hc_q = select(func.count(Employee.id)).where(
    Employee.tenant_id == self.tenant_id,
    Employee.hire_date <= start_date,
    (Employee.end_date.is_(None)) | (Employee.end_date > start_date),
)

# Probation-period terminations (hire_date to end_date < 90 days)
probation_terms_q = (
    select(func.count(Employee.id))
    .where(
        Employee.tenant_id == self.tenant_id,
        Employee.status == EmployeeStatus.terminated,
        Employee.end_date >= start_date,
        Employee.end_date <= end_date,
        func.datediff(Employee.end_date, Employee.hire_date) < 90,
    )
)

# Tenure-at-exit buckets: computed in Python from (end_date - hire_date).days
```

**Fields used:** `Employee.id`, `Employee.tenant_id`, `Employee.status`, `Employee.end_date`, `Employee.hire_date`, `Employee.department_id`; `Department.name`

**Tenant isolation:** `Employee.tenant_id == self.tenant_id`

**Privacy:** Department-level aggregates. No individual records.

---

### Tool 4: `get_department_budget` (A1-04)

**Tables:** `Department`, `Payslip`, `Employee`

**Query Pattern:**
```python
# Department budget
dept_q = select(Department).where(
    Department.id == department_id,
    Department.tenant_id == self.tenant_id,
)

# Actual spend = SUM(gross_salary) from Payslip for employees in this department
spend_q = (
    select(
        func.coalesce(func.sum(Payslip.gross_salary), 0).label("total_spend"),
        func.coalesce(func.sum(Payslip.basic_salary), 0).label("basic_total"),
        func.coalesce(func.sum(Payslip.housing_allowance), 0).label("housing_total"),
        func.coalesce(func.sum(Payslip.transport_allowance), 0).label("transport_total"),
        func.coalesce(func.sum(Payslip.gosi_employee), 0).label("gosi_total"),
        func.count(func.distinct(Payslip.month)).label("months_with_data"),
    )
    .join(Employee, Payslip.employee_id == Employee.id)
    .where(
        Payslip.tenant_id == self.tenant_id,
        Employee.department_id == department_id,
        Payslip.year == fiscal_year,
    )
)

# Monthly burn rate = total_spend / months_with_data
# Projected year-end = burn_rate * 12
# over_budget_risk = projected > department.cost_budget_sar
```

**Fields used:** `Department.id`, `Department.tenant_id`, `Department.cost_budget_sar`, `Department.name`; `Payslip.tenant_id`, `Payslip.employee_id`, `Payslip.year`, `Payslip.gross_salary`, `Payslip.basic_salary`, `Payslip.housing_allowance`, `Payslip.transport_allowance`, `Payslip.gosi_employee`; `Employee.id`, `Employee.department_id`

**Tenant isolation:** `Payslip.tenant_id` AND `Department.tenant_id`

**Privacy:** Aggregated sums only.

---

### Tool 5: `get_salary_distribution` (A1-05)

**Tables:** `Employee`, `Department`

**Query Pattern:**
```python
# Load salary values for statistical computation
# (SQL percentile functions vary by DB -- use Python-side statistics for portability)
salary_q = (
    select(
        Employee.salary_sar,
        Employee.department_id,
        Employee.gender,
        Employee.is_saudi,
        Employee.job_title,
    )
    .where(
        Employee.tenant_id == self.tenant_id,
        Employee.status != EmployeeStatus.terminated,
        Employee.salary_sar.isnot(None),
    )
)
# Optional department filter

# Compute in Python: min, max, median, mean, p25, p75, stddev per group
# Outlier count: salary > mean + 2*stddev OR salary < mean - 2*stddev per department
# Gender pay gap: (median_female / median_male - 1) * 100

# Unmapped count
unmapped_q = select(func.count(Employee.id)).where(
    Employee.tenant_id == self.tenant_id,
    Employee.status != EmployeeStatus.terminated,
    Employee.salary_sar.is_(None),
)
```

**Fields used:** `Employee.salary_sar`, `Employee.department_id`, `Employee.gender`, `Employee.is_saudi`, `Employee.job_title`, `Employee.tenant_id`, `Employee.status`

**Tenant isolation:** `Employee.tenant_id == self.tenant_id`

**Privacy:** Only statistical aggregates (min, max, median, mean, percentiles). No names or IDs. Outlier flagging is count-only.

---

### Tool 6: `get_workforce_overview` (A1-06)

**Tables:** `Employee`, `Department`, `NitaqatConfig`

**Query Pattern:**
```python
# Single comprehensive query set -- reuses patterns from tools 1 and 2
# Headcount: func.count grouped by status
# Saudization: func.count grouped by is_saudi
# Gender: func.count grouped by gender
# Tenure distribution: computed in Python from hire_date
#   buckets: <1yr, 1-2yr, 2-5yr, 5-10yr, 10+yr
# Contract types: func.count grouped by contract_type
# Work modes: func.count grouped by work_mode
# Probation stats:
probation_q = select(func.count(Employee.id)).where(
    Employee.tenant_id == self.tenant_id,
    Employee.status != EmployeeStatus.terminated,
    Employee.probation_completed == False,
    Employee.probation_end_date > date.today(),
)
# Probation completing in 30 days:
probation_soon_q = select(func.count(Employee.id)).where(
    Employee.tenant_id == self.tenant_id,
    Employee.probation_completed == False,
    Employee.probation_end_date.between(date.today(), date.today() + timedelta(days=30)),
)
# New hires last 30 days:
new_hires_q = select(func.count(Employee.id)).where(
    Employee.tenant_id == self.tenant_id,
    Employee.hire_date >= date.today() - timedelta(days=30),
)
```

**Fields used:** Most Employee fields (status, is_saudi, gender, contract_type, work_mode, hire_date, probation_end_date, probation_completed, department_id)

**Tenant isolation:** All queries use `Employee.tenant_id == self.tenant_id`

**Privacy:** All aggregated.

---

### Tool 7: `get_compliance_status` (A1-07)

**Tables:** `ComplianceRecord`, `ComplianceAlert`

**Query Pattern:**
```python
# All compliance records for tenant
records_q = select(ComplianceRecord).where(
    ComplianceRecord.tenant_id == self.tenant_id,
)
# Optional category filter: .where(ComplianceRecord.category == category)

# Compliance score: compliant / total * 100
score_q = (
    select(
        func.count(ComplianceRecord.id).label("total"),
        func.sum(case((ComplianceRecord.is_compliant == True, 1), else_=0)).label("compliant"),
    )
    .where(ComplianceRecord.tenant_id == self.tenant_id)
)

# Overdue items: next_deadline < today AND is_compliant = false
overdue_q = select(ComplianceRecord).where(
    ComplianceRecord.tenant_id == self.tenant_id,
    ComplianceRecord.is_compliant == False,
    ComplianceRecord.next_deadline < date.today(),
)

# Upcoming deadlines: next_deadline within 30 days
upcoming_q = select(ComplianceRecord).where(
    ComplianceRecord.tenant_id == self.tenant_id,
    ComplianceRecord.next_deadline.between(date.today(), date.today() + timedelta(days=30)),
)

# Active alerts
alerts_q = (
    select(ComplianceAlert)
    .where(
        ComplianceAlert.tenant_id == self.tenant_id,
        ComplianceAlert.is_resolved == False,
    )
    .order_by(
        case(
            (ComplianceAlert.severity == ComplianceSeverity.critical, 0),
            (ComplianceAlert.severity == ComplianceSeverity.warning, 1),
            else_=2,
        )
    )
)
```

**Fields used:** `ComplianceRecord.*`; `ComplianceAlert.*`

**Tenant isolation:** Both models filtered by `tenant_id`.

**Privacy:** These are organizational records, not individual employee data.

---

### Tool 8: `get_recruitment_analytics` (A2-01)

**Tables:** `JobPosting`, `Candidate`, `Interview`

**Query Pattern:**
```python
# Open positions
open_q = select(func.count(JobPosting.id)).where(
    JobPosting.tenant_id == self.tenant_id,
    JobPosting.status == PostingStatus.open,
)
# Optional: .where(JobPosting.department_id == dept_id)

# Funnel: count candidates at each stage
funnel_q = (
    select(
        Candidate.stage,
        func.count(Candidate.id).label("count"),
    )
    .join(JobPosting, Candidate.job_posting_id == JobPosting.id)
    .where(
        JobPosting.tenant_id == self.tenant_id,
        Candidate.created_at >= start_date,
        Candidate.created_at <= end_date,
        Candidate.stage.notin_([CandidateStage.rejected, CandidateStage.withdrawn]),
    )
    .group_by(Candidate.stage)
)

# Time to fill: avg days from JobPosting.created_at to earliest hired candidate
# Requires subquery or Python-side computation
# Average AI match score
avg_score_q = (
    select(func.avg(Candidate.ai_match_score))
    .join(JobPosting, Candidate.job_posting_id == JobPosting.id)
    .where(
        JobPosting.tenant_id == self.tenant_id,
        Candidate.ai_match_score.isnot(None),
    )
)
```

**Fields used:** `JobPosting.id`, `JobPosting.tenant_id`, `JobPosting.status`, `JobPosting.department_id`, `JobPosting.created_at`; `Candidate.id`, `Candidate.stage`, `Candidate.ai_match_score`, `Candidate.created_at`, `Candidate.job_posting_id`; `Interview.status`, `Interview.overall_score`, `Interview.completed_at`

**Tenant isolation:** Via `JobPosting.tenant_id == self.tenant_id` (Candidate does not have its own tenant_id; isolation is enforced through the JobPosting join).

**Privacy:** Aggregated funnel counts and averages only. No candidate names.

---

### Tool 9: `get_leave_analytics` (A2-02)

**Tables:** `LeaveRequest`, `LeaveBalance`, `Employee`, `Department`

**Query Pattern:**
```python
# Total leave days by type (approved only)
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
        func.extract("year", LeaveRequest.start_date) == year,
    )
    .group_by(LeaveRequest.leave_type)
)

# Monthly pattern
monthly_q = (
    select(
        func.extract("month", LeaveRequest.start_date).label("month"),
        func.coalesce(func.sum(LeaveRequest.business_days), 0).label("days"),
    )
    .join(Employee, LeaveRequest.employee_id == Employee.id)
    .where(
        Employee.tenant_id == self.tenant_id,
        LeaveRequest.status == LeaveStatus.approved,
        func.extract("year", LeaveRequest.start_date) == year,
    )
    .group_by(func.extract("month", LeaveRequest.start_date))
)

# Utilization rate from LeaveBalance
util_q = (
    select(
        func.coalesce(func.sum(LeaveBalance.used_days), 0).label("used"),
        func.coalesce(func.sum(LeaveBalance.total_days), 0).label("total"),
    )
    .join(Employee, LeaveBalance.employee_id == Employee.id)
    .where(
        Employee.tenant_id == self.tenant_id,
        LeaveBalance.year == year,
    )
)

# Pending requests count
pending_q = (
    select(func.count(LeaveRequest.id))
    .join(Employee, LeaveRequest.employee_id == Employee.id)
    .where(
        Employee.tenant_id == self.tenant_id,
        LeaveRequest.status == LeaveStatus.pending,
    )
)
```

**Fields used:** `LeaveRequest.leave_type`, `LeaveRequest.business_days`, `LeaveRequest.status`, `LeaveRequest.start_date`, `LeaveRequest.employee_id`; `LeaveBalance.used_days`, `LeaveBalance.total_days`, `LeaveBalance.year`, `LeaveBalance.employee_id`; `Employee.id`, `Employee.tenant_id`, `Employee.department_id`

**Tenant isolation:** Through `Employee.tenant_id` join (LeaveRequest/LeaveBalance do not have tenant_id directly).

**Privacy:** Aggregated by type, department, month. No individual leave records exposed.

---

### Tool 10: `get_attendance_analytics` (A2-03)

**Tables:** `AttendanceRecord`, `WorkSchedule`, `Employee`, `Department`

**Query Pattern:**
```python
# Attendance rate, late rate, absent rate
status_q = (
    select(
        AttendanceRecord.status,
        func.count(AttendanceRecord.id).label("count"),
    )
    .join(Employee, AttendanceRecord.employee_id == Employee.id)
    .where(
        AttendanceRecord.tenant_id == self.tenant_id,
        AttendanceRecord.date >= start_date,
        AttendanceRecord.date <= end_date,
        AttendanceRecord.status.notin_([
            AttendanceStatus.weekend, AttendanceStatus.holiday,
        ]),
    )
    .group_by(AttendanceRecord.status)
)

# Overtime totals
ot_q = (
    select(
        func.coalesce(func.sum(AttendanceRecord.overtime_hours), 0.0).label("total_ot"),
        func.count(func.distinct(AttendanceRecord.employee_id)).label("emp_count"),
    )
    .where(
        AttendanceRecord.tenant_id == self.tenant_id,
        AttendanceRecord.date >= start_date,
        AttendanceRecord.date <= end_date,
    )
)

# Day-of-week pattern (uses EXTRACT(DOW))
dow_q = (
    select(
        func.extract("dow", AttendanceRecord.date).label("day_of_week"),
        func.count(
            case((AttendanceRecord.status.in_([AttendanceStatus.present, AttendanceStatus.late]), 1))
        ).label("present_count"),
        func.count(AttendanceRecord.id).label("total_count"),
    )
    .where(
        AttendanceRecord.tenant_id == self.tenant_id,
        AttendanceRecord.date >= start_date,
        AttendanceRecord.date <= end_date,
        AttendanceRecord.status.notin_([AttendanceStatus.weekend, AttendanceStatus.holiday]),
    )
    .group_by(func.extract("dow", AttendanceRecord.date))
)
```

**Fields used:** `AttendanceRecord.tenant_id`, `AttendanceRecord.employee_id`, `AttendanceRecord.date`, `AttendanceRecord.status`, `AttendanceRecord.overtime_hours`; `Employee.department_id`

**Tenant isolation:** `AttendanceRecord.tenant_id == self.tenant_id`

**Privacy:** Aggregated rates and totals. No individual attendance records.

---

### Tool 11: `get_onboarding_analytics` (A2-04)

**Tables:** `OnboardingAssignment`, `OnboardingStepAssignment`

**Query Pattern:**
```python
# Overall completion stats
stats_q = (
    select(
        func.count(OnboardingAssignment.id).label("total"),
        func.sum(case((OnboardingAssignment.status == OnboardingAssignmentStatus.completed, 1), else_=0)).label("completed"),
        func.sum(case((OnboardingAssignment.status == OnboardingAssignmentStatus.in_progress, 1), else_=0)).label("in_progress"),
    )
    .where(
        OnboardingAssignment.tenant_id == self.tenant_id,
        OnboardingAssignment.started_at >= start_date,
        OnboardingAssignment.started_at <= end_date,
    )
)

# Avg days to complete
avg_days_q = (
    select(
        func.avg(
            func.extract("epoch", OnboardingAssignment.completed_at - OnboardingAssignment.started_at) / 86400
        ).label("avg_days")
    )
    .where(
        OnboardingAssignment.tenant_id == self.tenant_id,
        OnboardingAssignment.status == OnboardingAssignmentStatus.completed,
        OnboardingAssignment.started_at >= start_date,
    )
)

# Bottleneck steps: steps with lowest completion rate
bottleneck_q = (
    select(
        OnboardingStepAssignment.template_step_id,
        func.count(OnboardingStepAssignment.id).label("total"),
        func.sum(case((OnboardingStepAssignment.status == OnboardingStepStatus.completed, 1), else_=0)).label("completed"),
    )
    .join(OnboardingAssignment, OnboardingStepAssignment.assignment_id == OnboardingAssignment.id)
    .where(OnboardingAssignment.tenant_id == self.tenant_id)
    .group_by(OnboardingStepAssignment.template_step_id)
)

# Overdue steps: status=pending AND due_date < now()
overdue_q = (
    select(func.count(OnboardingStepAssignment.id))
    .join(OnboardingAssignment, OnboardingStepAssignment.assignment_id == OnboardingAssignment.id)
    .where(
        OnboardingAssignment.tenant_id == self.tenant_id,
        OnboardingStepAssignment.status == OnboardingStepStatus.pending,
        OnboardingStepAssignment.due_date < datetime.now(timezone.utc),
    )
)
```

**Fields used:** `OnboardingAssignment.tenant_id`, `OnboardingAssignment.status`, `OnboardingAssignment.started_at`, `OnboardingAssignment.completed_at`; `OnboardingStepAssignment.assignment_id`, `OnboardingStepAssignment.template_step_id`, `OnboardingStepAssignment.status`, `OnboardingStepAssignment.due_date`

**Tenant isolation:** `OnboardingAssignment.tenant_id == self.tenant_id`

**Privacy:** Aggregated completion rates. No individual names.

---

### Tool 12: `get_payroll_summary` (A2-05)

**Tables:** `Payslip`, `Employee`, `Department`

**Query Pattern:**
```python
# Parse start_month and end_month into (year, month) tuples
# Total aggregates
total_q = (
    select(
        func.coalesce(func.sum(Payslip.gross_salary), 0).label("total_gross"),
        func.coalesce(func.sum(Payslip.total_deductions), 0).label("total_deductions"),
        func.coalesce(func.sum(Payslip.net_salary), 0).label("total_net"),
        func.coalesce(func.sum(Payslip.basic_salary), 0).label("basic"),
        func.coalesce(func.sum(Payslip.housing_allowance), 0).label("housing"),
        func.coalesce(func.sum(Payslip.transport_allowance), 0).label("transport"),
        func.coalesce(func.sum(Payslip.gosi_employee), 0).label("gosi"),
        func.coalesce(func.sum(Payslip.other_allowances), 0).label("other_allow"),
        func.count(func.distinct(Payslip.employee_id)).label("headcount"),
    )
    .where(
        Payslip.tenant_id == self.tenant_id,
        # year/month range filter
    )
)
# Optional department filter via join to Employee

# Monthly trend
monthly_q = (
    select(
        Payslip.year, Payslip.month,
        func.sum(Payslip.gross_salary).label("gross"),
        func.sum(Payslip.total_deductions).label("deductions"),
        func.sum(Payslip.net_salary).label("net"),
    )
    .where(Payslip.tenant_id == self.tenant_id)
    .group_by(Payslip.year, Payslip.month)
    .order_by(Payslip.year, Payslip.month)
)

# Department breakdown
dept_q = (
    select(
        Department.name,
        func.sum(Payslip.gross_salary).label("gross"),
        func.count(func.distinct(Payslip.employee_id)).label("headcount"),
    )
    .join(Employee, Payslip.employee_id == Employee.id)
    .join(Department, Employee.department_id == Department.id)
    .where(Payslip.tenant_id == self.tenant_id)
    .group_by(Department.name)
)
```

**Fields used:** All Payslip numeric columns; `Employee.id`, `Employee.department_id`, `Employee.tenant_id`; `Department.name`

**Tenant isolation:** `Payslip.tenant_id == self.tenant_id`

**Privacy:** Aggregated sums by department. No individual salaries.

---

### Tool 13: `get_attrition_risk` (A3-01)

**Tables:** `Employee`, `Payslip`, `AttendanceRecord`, `LeaveBalance`

**Query Pattern:**
```python
# Department-level scoring -- compute per department, aggregate risk factors
# For each department:

# Factor 1: Short tenure employees (tenure < 1yr, probation complete)
short_tenure_q = (
    select(func.count(Employee.id))
    .where(
        Employee.tenant_id == self.tenant_id,
        Employee.department_id == dept_id,
        Employee.status != EmployeeStatus.terminated,
        Employee.hire_date > date.today() - timedelta(days=365),
        Employee.probation_completed == True,
    )
)

# Factor 2: Salary stagnation -- compare earliest and latest basic_salary in Payslip
# over last 18 months. If no change, flag.
salary_stag_q = (
    select(
        func.count(func.distinct(Payslip.employee_id))
    )
    .join(Employee, Payslip.employee_id == Employee.id)
    .where(
        Payslip.tenant_id == self.tenant_id,
        Employee.department_id == dept_id,
        # subquery: max(basic_salary) == min(basic_salary) over 18 months
    )
)

# Factor 3: Department historical turnover rate (reuse turnover logic)
# Factor 4: High overtime (avg overtime_hours > 20/month per employee)
high_ot_q = (
    select(func.count(func.distinct(AttendanceRecord.employee_id)))
    .join(Employee, AttendanceRecord.employee_id == Employee.id)
    .where(
        AttendanceRecord.tenant_id == self.tenant_id,
        Employee.department_id == dept_id,
    )
    .group_by(AttendanceRecord.employee_id)
    .having(func.avg(AttendanceRecord.overtime_hours) > 20)
)

# Factor 5: Unused leave > 80% past mid-year
unused_leave_q = (
    select(func.count(LeaveBalance.id))
    .join(Employee, LeaveBalance.employee_id == Employee.id)
    .where(
        Employee.tenant_id == self.tenant_id,
        Employee.department_id == dept_id,
        LeaveBalance.year == date.today().year,
        (LeaveBalance.used_days * 100.0 / func.nullif(LeaveBalance.total_days, 0)) < 20,
    )
)

# Score = weighted sum of (factor_count / dept_headcount * factor_weight)
```

**Fields used:** `Employee.hire_date`, `Employee.probation_completed`, `Employee.department_id`, `Employee.status`, `Employee.is_saudi`; `Payslip.basic_salary`, `Payslip.employee_id`; `AttendanceRecord.overtime_hours`, `AttendanceRecord.employee_id`; `LeaveBalance.used_days`, `LeaveBalance.total_days`, `LeaveBalance.year`

**Tenant isolation:** All queries filter by `tenant_id`.

**Privacy:** Department-level risk scores only. No individual names. Factor descriptions are generic (e.g., "3 employees with high overtime").

---

### Tool 14: `get_budget_forecast` (A3-02)

**Tables:** `Payslip`, `Department`, `JobPosting`

**Query Pattern:**
```python
# YTD spend
ytd_q = (
    select(
        func.coalesce(func.sum(Payslip.gross_salary), 0).label("ytd_spend"),
        func.count(func.distinct(Payslip.month)).label("months_elapsed"),
    )
    .where(
        Payslip.tenant_id == self.tenant_id,
        Payslip.year == fiscal_year,
    )
)
# Optional department filter

# Budget from Department.cost_budget_sar (sum across all depts or single dept)
budget_q = select(func.coalesce(func.sum(Department.cost_budget_sar), 0)).where(
    Department.tenant_id == self.tenant_id,
)

# For "with_open_positions" scenario:
open_positions_q = (
    select(
        func.count(JobPosting.id).label("open_count"),
        func.avg((JobPosting.salary_min_sar + JobPosting.salary_max_sar) / 2).label("avg_salary"),
    )
    .where(
        JobPosting.tenant_id == self.tenant_id,
        JobPosting.status == PostingStatus.open,
        JobPosting.salary_min_sar.isnot(None),
        JobPosting.salary_max_sar.isnot(None),
    )
)

# Projection logic (in Python):
# current_trend: burn_rate = ytd / months_elapsed; projected = burn_rate * 12
# with_open_positions: projected += open_count * avg_salary * remaining_months
# conservative: highest_month = max(monthly_gross); projected = highest_month * 12
```

**Fields used:** `Payslip.gross_salary`, `Payslip.year`, `Payslip.month`, `Payslip.tenant_id`; `Department.cost_budget_sar`, `Department.tenant_id`; `JobPosting.tenant_id`, `JobPosting.status`, `JobPosting.salary_min_sar`, `JobPosting.salary_max_sar`

**Tenant isolation:** All three tables filtered by `tenant_id`.

**Privacy:** Budget-level aggregates. No individual data.

---

### Tool 15: `get_gosi_compliance` (A3-03)

**Tables:** `Employee`, `Department`, `Payslip`

**Query Pattern:**
```python
# GOSI registration status
gosi_q = (
    select(
        Employee.gosi_registered,
        Employee.is_saudi,
        func.count(Employee.id).label("count"),
    )
    .where(
        Employee.tenant_id == self.tenant_id,
        Employee.status.in_([EmployeeStatus.active, EmployeeStatus.on_leave]),
    )
    .group_by(Employee.gosi_registered, Employee.is_saudi)
)

# Overdue registrations: not registered AND hired > 15 days ago
overdue_q = (
    select(
        Department.name,
        func.count(Employee.id).label("overdue_count"),
    )
    .join(Department, Employee.department_id == Department.id)
    .where(
        Employee.tenant_id == self.tenant_id,
        Employee.gosi_registered == False,
        Employee.status.in_([EmployeeStatus.active, EmployeeStatus.on_leave]),
        Employee.hire_date <= date.today() - timedelta(days=15),
    )
    .group_by(Department.name)
)

# Estimated monthly GOSI liability
# Saudi: 9.75% employer on (basic_salary + housing_allowance)
# Non-Saudi: 2% employer on (basic_salary + housing_allowance)
liability_q = (
    select(
        func.sum(
            case(
                (Employee.is_saudi == True,
                 (Employee.salary_sar * 0.0975).cast(Integer)),
                else_=(Employee.salary_sar * 0.02).cast(Integer),
            )
        ).label("estimated_monthly_gosi")
    )
    .where(
        Employee.tenant_id == self.tenant_id,
        Employee.status.in_([EmployeeStatus.active, EmployeeStatus.on_leave]),
        Employee.salary_sar.isnot(None),
    )
)
```

**Fields used:** `Employee.gosi_registered`, `Employee.is_saudi`, `Employee.hire_date`, `Employee.salary_sar`, `Employee.status`, `Employee.department_id`, `Employee.tenant_id`; `Department.name`

**Tenant isolation:** `Employee.tenant_id == self.tenant_id`

**Privacy:** Counts by department. No employee names. Liability is a single org-wide number.

---

### Tool 16: `get_policy_acknowledgment_status` (A3-04)

**Tables:** `HRPolicy`, `PolicyAcknowledgment`, `Employee`

**Query Pattern:**
```python
# Published policies
policies_q = select(HRPolicy).where(
    HRPolicy.tenant_id == self.tenant_id,
    HRPolicy.status == PolicyStatus.published,
)
# Optional: .where(HRPolicy.id == policy_id)

# Total active employees (for acknowledgment rate denominator)
emp_count_q = select(func.count(Employee.id)).where(
    Employee.tenant_id == self.tenant_id,
    Employee.status != EmployeeStatus.terminated,
)
# Optional department filter

# Acknowledgment count per policy
ack_q = (
    select(
        PolicyAcknowledgment.policy_id,
        func.count(PolicyAcknowledgment.id).label("ack_count"),
    )
    .where(PolicyAcknowledgment.tenant_id == self.tenant_id)
    .group_by(PolicyAcknowledgment.policy_id)
)
# If department filter: join to Employee and filter by department_id

# For each policy: ack_rate = ack_count / total_employees * 100
# Policies below 80% threshold are flagged
```

**Fields used:** `HRPolicy.id`, `HRPolicy.tenant_id`, `HRPolicy.title`, `HRPolicy.title_ar`, `HRPolicy.category`, `HRPolicy.status`, `HRPolicy.effective_date`; `PolicyAcknowledgment.policy_id`, `PolicyAcknowledgment.tenant_id`, `PolicyAcknowledgment.employee_id`; `Employee.id`, `Employee.tenant_id`, `Employee.status`, `Employee.department_id`

**Tenant isolation:** All three tables filtered by `tenant_id`.

**Privacy:** Counts and percentages only. No employee identifiers.

---

### Tool 17: `generate_custom_report` (A3-05)

**Tables:** All (delegates to other tools)

**Query Pattern:** No direct SQL. This is a meta-tool that calls the other 16 tools' internal methods by metric name and assembles results into a unified report.

```python
METRIC_TO_METHOD = {
    "headcount": self._get_headcount_summary,
    "saudization": self._get_saudization_status,
    "turnover": self._get_turnover_metrics,
    "budget": self._get_department_budget,
    "salary": self._get_salary_distribution,
    "leave": self._get_leave_analytics,
    "recruitment": self._get_recruitment_analytics,
    "attendance": self._get_attendance_analytics,
    "payroll": self._get_payroll_summary,
    "compliance": self._get_compliance_status,
    "gosi": self._get_gosi_compliance,
    "policy_acknowledgment": self._get_policy_acknowledgment_status,
}
# Cap at 5 metrics per request
# Each section independently handles errors (returns {"no_data": True} on exception)
# Report gets a UUID report_id and timestamps (Gregorian + Hijri)
```

**Tenant isolation:** Inherited from delegated tool calls.

**Privacy:** Inherited from delegated tool calls.

---

## 3. Tool Definitions (Complete JSON Schemas)

### 3.1 get_headcount_summary
```json
{
    "name": "get_headcount_summary",
    "description": "Get current headcount broken down by department, status, gender, nationality, contract type, or work mode. Includes 30-day period comparison.",
    "input_schema": {
        "type": "object",
        "properties": {
            "department_id": {
                "type": "string",
                "description": "Department UUID to filter (omit for org-wide)"
            },
            "group_by": {
                "type": "string",
                "enum": ["department", "status", "gender", "nationality", "contract_type", "work_mode"],
                "description": "Grouping dimension (default: department)"
            }
        },
        "required": []
    }
}
```

### 3.2 get_saudization_status
```json
{
    "name": "get_saudization_status",
    "description": "Get the current Saudization ratio, Nitaqat band, gap to target, and risk buffer. Optionally includes 6-month trend.",
    "input_schema": {
        "type": "object",
        "properties": {
            "department_id": {
                "type": "string",
                "description": "Department UUID to filter (omit for org-wide)"
            },
            "include_trend": {
                "type": "boolean",
                "description": "Include monthly trend for the last 6 months (default: false)"
            }
        },
        "required": []
    }
}
```

### 3.3 get_turnover_metrics
```json
{
    "name": "get_turnover_metrics",
    "description": "Compute turnover rate for a period with department breakdown, tenure-at-exit distribution, and probation-period terminations. Flags departments above 15% annualized.",
    "input_schema": {
        "type": "object",
        "properties": {
            "department_id": {
                "type": "string",
                "description": "Department UUID to filter (omit for org-wide)"
            },
            "period": {
                "type": "string",
                "enum": ["monthly", "quarterly", "yearly"],
                "description": "Time granularity for trend breakdown (default: quarterly)"
            },
            "start_date": {
                "type": "string",
                "description": "Analysis start date in YYYY-MM-DD format (default: 12 months ago)"
            },
            "end_date": {
                "type": "string",
                "description": "Analysis end date in YYYY-MM-DD format (default: today)"
            }
        },
        "required": []
    }
}
```

### 3.4 get_department_budget
```json
{
    "name": "get_department_budget",
    "description": "Get budget utilization for a department: allocated vs spent from payroll, monthly burn rate, projected year-end spend, and over-budget risk assessment.",
    "input_schema": {
        "type": "object",
        "properties": {
            "department_id": {
                "type": "string",
                "description": "Department UUID"
            },
            "fiscal_year": {
                "type": "integer",
                "description": "Fiscal year to query (default: current year)"
            }
        },
        "required": ["department_id"]
    }
}
```

### 3.5 get_salary_distribution
```json
{
    "name": "get_salary_distribution",
    "description": "Get salary statistics (min, max, median, mean, percentiles) grouped by department, gender, nationality, or job title. Flags outliers and gender pay gap. No individual data exposed.",
    "input_schema": {
        "type": "object",
        "properties": {
            "department_id": {
                "type": "string",
                "description": "Department UUID to filter (omit for org-wide)"
            },
            "group_by": {
                "type": "string",
                "enum": ["department", "gender", "nationality", "job_title"],
                "description": "Grouping dimension (default: department)"
            }
        },
        "required": []
    }
}
```

### 3.6 get_workforce_overview
```json
{
    "name": "get_workforce_overview",
    "description": "Comprehensive workforce composition: headcount, Saudization, gender, tenure distribution, contract types, work modes, probation stats, and recent hires. One call for a full 'state of the workforce' summary.",
    "input_schema": {
        "type": "object",
        "properties": {
            "department_id": {
                "type": "string",
                "description": "Department UUID to filter (omit for org-wide)"
            }
        },
        "required": []
    }
}
```

### 3.7 get_compliance_status
```json
{
    "name": "get_compliance_status",
    "description": "Get compliance dashboard: overall compliance score, items by category (GOSI, Nitaqat, WPS, labor law, data privacy, health/safety, financial), overdue items, upcoming deadlines, and active unresolved alerts sorted by severity.",
    "input_schema": {
        "type": "object",
        "properties": {
            "department_id": {
                "type": "string",
                "description": "Filter by department (omit for org-wide)"
            },
            "category": {
                "type": "string",
                "enum": ["gosi", "nitaqat", "wps", "labor_law", "data_privacy", "health_safety", "financial", "all"],
                "description": "Compliance category to check (default: all)"
            }
        },
        "required": []
    }
}
```

### 3.8 get_recruitment_analytics
```json
{
    "name": "get_recruitment_analytics",
    "description": "Get recruitment pipeline metrics: funnel conversion rates per stage, time to fill, average AI match score, and department breakdown.",
    "input_schema": {
        "type": "object",
        "properties": {
            "department_id": {
                "type": "string",
                "description": "Department UUID to filter (omit for org-wide)"
            },
            "start_date": {
                "type": "string",
                "description": "Start of analysis window in YYYY-MM-DD format (default: 6 months ago)"
            },
            "end_date": {
                "type": "string",
                "description": "End of analysis window in YYYY-MM-DD format (default: today)"
            }
        },
        "required": []
    }
}
```

### 3.9 get_leave_analytics
```json
{
    "name": "get_leave_analytics",
    "description": "Get leave usage patterns: total days by type, department breakdown with avg per employee, monthly pattern for seasonality, utilization rate, and pending request count. Highlights Hajj leave separately.",
    "input_schema": {
        "type": "object",
        "properties": {
            "department_id": {
                "type": "string",
                "description": "Department UUID to filter (omit for org-wide)"
            },
            "year": {
                "type": "integer",
                "description": "Year to analyze (default: current year)"
            },
            "leave_type": {
                "type": "string",
                "enum": ["annual", "sick", "emergency", "maternity", "paternity", "hajj", "bereavement", "unpaid"],
                "description": "Filter to one leave type (omit for all)"
            }
        },
        "required": []
    }
}
```

### 3.10 get_attendance_analytics
```json
{
    "name": "get_attendance_analytics",
    "description": "Get attendance and overtime analytics: attendance rate, late rate, absence rate, overtime totals, day-of-week patterns, and department ranking. Excludes Fri-Sat weekends.",
    "input_schema": {
        "type": "object",
        "properties": {
            "department_id": {
                "type": "string",
                "description": "Department UUID to filter (omit for org-wide)"
            },
            "start_date": {
                "type": "string",
                "description": "Start date in YYYY-MM-DD format (default: current month start)"
            },
            "end_date": {
                "type": "string",
                "description": "End date in YYYY-MM-DD format (default: today)"
            }
        },
        "required": []
    }
}
```

### 3.11 get_onboarding_analytics
```json
{
    "name": "get_onboarding_analytics",
    "description": "Get onboarding metrics: completion rate, average days to complete, bottleneck steps, and overdue count.",
    "input_schema": {
        "type": "object",
        "properties": {
            "start_date": {
                "type": "string",
                "description": "Start date for filtering assignments in YYYY-MM-DD format (default: 6 months ago)"
            },
            "end_date": {
                "type": "string",
                "description": "End date in YYYY-MM-DD format (default: today)"
            }
        },
        "required": []
    }
}
```

### 3.12 get_payroll_summary
```json
{
    "name": "get_payroll_summary",
    "description": "Get payroll cost summary: total gross/deductions/net, monthly trend, category breakdown (basic, housing, transport, GOSI), department breakdown, and average cost per employee.",
    "input_schema": {
        "type": "object",
        "properties": {
            "department_id": {
                "type": "string",
                "description": "Department UUID to filter (omit for org-wide)"
            },
            "start_month": {
                "type": "string",
                "description": "Start month in YYYY-MM format"
            },
            "end_month": {
                "type": "string",
                "description": "End month in YYYY-MM format"
            }
        },
        "required": ["start_month", "end_month"]
    }
}
```

### 3.13 get_attrition_risk
```json
{
    "name": "get_attrition_risk",
    "description": "Compute rule-based attrition risk scores per department using weighted factors: short tenure, salary stagnation, high overtime, low leave usage, and department turnover history. Returns department-level aggregates only.",
    "input_schema": {
        "type": "object",
        "properties": {
            "department_id": {
                "type": "string",
                "description": "Department UUID (omit for all departments)"
            },
            "risk_threshold": {
                "type": "string",
                "enum": ["high", "medium", "all"],
                "description": "Filter by risk level (default: all)"
            }
        },
        "required": []
    }
}
```

### 3.14 get_budget_forecast
```json
{
    "name": "get_budget_forecast",
    "description": "Project workforce costs for the rest of the fiscal year under three scenarios: current trend, with open positions filled, and conservative. Compares against department budgets.",
    "input_schema": {
        "type": "object",
        "properties": {
            "department_id": {
                "type": "string",
                "description": "Department UUID (omit for org-wide)"
            },
            "fiscal_year": {
                "type": "integer",
                "description": "Fiscal year to forecast (default: current year)"
            },
            "scenario": {
                "type": "string",
                "enum": ["current_trend", "with_open_positions", "conservative"],
                "description": "Forecasting scenario (default: current_trend)"
            }
        },
        "required": []
    }
}
```

### 3.15 get_gosi_compliance
```json
{
    "name": "get_gosi_compliance",
    "description": "Audit GOSI registration: registered/unregistered counts, compliance rate, overdue registrations (hired >15 days and not registered), Saudi vs non-Saudi breakdown, and estimated monthly GOSI liability in SAR.",
    "input_schema": {
        "type": "object",
        "properties": {
            "department_id": {
                "type": "string",
                "description": "Department UUID (omit for org-wide)"
            }
        },
        "required": []
    }
}
```

### 3.16 get_policy_acknowledgment_status
```json
{
    "name": "get_policy_acknowledgment_status",
    "description": "Track which published policies have been acknowledged by employees. Shows acknowledgment rate per policy, flags policies below 80% threshold, and gives department-level compliance.",
    "input_schema": {
        "type": "object",
        "properties": {
            "policy_id": {
                "type": "string",
                "description": "Specific policy UUID (omit for all published policies)"
            },
            "department_id": {
                "type": "string",
                "description": "Department UUID to filter acknowledgment scope"
            }
        },
        "required": []
    }
}
```

### 3.17 generate_custom_report
```json
{
    "name": "generate_custom_report",
    "description": "Generate a custom report combining multiple metric sections into one unified output. Maximum 5 metrics per report. Includes Hijri date.",
    "input_schema": {
        "type": "object",
        "properties": {
            "metrics": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["headcount", "saudization", "turnover", "budget", "salary", "leave", "recruitment", "attendance", "payroll", "compliance", "gosi", "policy_acknowledgment"]
                },
                "description": "Which metrics to include (max 5)",
                "maxItems": 5,
                "minItems": 1
            },
            "department_id": {
                "type": "string",
                "description": "Department UUID (omit for org-wide)"
            },
            "start_date": {
                "type": "string",
                "description": "Start date in YYYY-MM-DD format (default: start of current year)"
            },
            "end_date": {
                "type": "string",
                "description": "End date in YYYY-MM-DD format (default: today)"
            }
        },
        "required": ["metrics"]
    }
}
```

---

## 4. Scope Rules

### What Ahmad Handles
- Workforce analytics: headcount, composition, tenure, contract types
- Saudization and Nitaqat band tracking
- Turnover rate analysis and attrition risk scoring
- Budget utilization and financial forecasting
- Salary distribution and pay equity analysis
- Compliance status dashboards (GOSI, Nitaqat, WPS, labor law, data privacy)
- Recruitment funnel analytics (read-only view of Mohammad's pipeline)
- Leave usage patterns and seasonality
- Attendance and overtime analytics
- Onboarding completion metrics
- Payroll cost summaries
- Policy acknowledgment tracking
- Custom multi-metric reports

### What Ahmad Does NOT Handle (with redirects)

| Request Type | Redirect Target | Example Redirect Phrase |
|---|---|---|
| Individual leave requests, balances, payslips | Deema | "For leave requests, please talk to Deema (كلم ديمة)" |
| Recruitment actions (post job, screen candidate, schedule interview) | Mohammad | "For recruitment actions, talk to Mohammad (كلم محمد)" |
| Onboarding task management, team management, leave approvals | Waleed | "For onboarding and team management, talk to Waleed (كلم وليد)" |
| AI agent design, deployment, workforce planning, automation | Yara | "For AI agent design and deployment, talk to Yara (كلم يارا)" |
| Creating compliance alerts or modifying compliance records | Admin API / future agent | "Compliance alerts must be created through the admin panel" |
| Policy creation, editing, or publishing | Admin API / future agent | "Policy management is available through the admin panel" |

### Negative Boundaries for Other Agents

These agents' scope rules must be updated to redirect analytics/compliance questions to Ahmad:

- **Yara `_get_scope_rules()`:** Change `"Budget, analytics, or financial reports → redirect to Norah"` and `"Compliance, labor law, or regulation questions → redirect to Sarah"` to `"→ redirect to Ahmad"`.
- **Waleed agent_display dict (line 280):** Replace `"norah": "نورة"` and `"sarah": "سارة"` with `"ahmad": "أحمد"`.
- **Mohammad agent_display dict (line 668-669):** Same replacement.

---

## 5. System Prompt Design

### `_get_scope_rules()` Full Text

```python
def _get_scope_rules(self) -> str:
    return (
        "You are Ahmad (أحمد), the CHRO — Chief Human Resources Officer of this organization.\n"
        "You are the strategic brain: the single conversational interface for C-suite and HR leadership.\n"
        "\n"
        "YOUR RESPONSIBILITIES:\n"
        "1. Workforce analytics — headcount, composition, tenure, turnover, attrition risk\n"
        "2. Saudization & Nitaqat compliance — Saudi/non-Saudi ratios, band tracking, gap analysis\n"
        "3. Financial analytics — budget utilization, payroll costs, forecasting, salary distribution\n"
        "4. Compliance monitoring — GOSI registration, labor law compliance, regulatory deadlines\n"
        "5. Cross-domain analytics — recruitment funnel, leave patterns, attendance, onboarding\n"
        "6. Policy governance — acknowledgment tracking, compliance rates\n"
        "7. Custom reporting — combine any metrics into unified executive reports\n"
        "\n"
        "EXECUTIVE COMMUNICATION STYLE:\n"
        "- Lead with the HEADLINE NUMBER — the single most important metric that answers the question\n"
        "- Follow with supporting breakdown — departments, trends, comparisons\n"
        "- End with recommendations — actionable steps tied to business impact\n"
        "- Use directional indicators: 'up 3.2% from last quarter', risk labels (green/yellow/red)\n"
        "- Format currency in SAR with context (e.g., 'SAR 2.5M / SAR 3.0M budget — 83% utilized')\n"
        "- When compliance and analytics intersect, always surface the compliance angle\n"
        "  (e.g., 'Headcount is 100, Saudization at 28% — 2% above green_low, buffer is thin')\n"
        "\n"
        "SAUDI-SPECIFIC KNOWLEDGE:\n"
        "- Weekend: Friday-Saturday. Work week: Sunday-Thursday.\n"
        "- Nitaqat bands: Platinum > Green High > Green Low > Yellow > Red\n"
        "- GOSI rates: Saudi = 9.75% employee + 9.75% employer (on basic + housing); "
        "Non-Saudi = 2% employer only (occupational hazard)\n"
        "- GOSI registration deadline: within 15 days of employment start\n"
        "- Saudi Labor Law Article 53: probation period terminations (90 days)\n"
        "- Hajj leave: 10-15 days one-time entitlement (Article 47)\n"
        "- WPS (Wage Protection System): mandatory salary payment through approved banks\n"
        "\n"
        "YOU ARE READ-ONLY:\n"
        "- You NEVER create, update, or delete records\n"
        "- You query and analyze existing data only\n"
        "- If asked to create an alert, policy, or modify data, explain this requires the admin panel\n"
        "\n"
        "YOU DO NOT HANDLE:\n"
        "- Individual leave requests, personal balances, or payslip lookups → redirect to Deema (ديمة)\n"
        "- Recruitment actions (post jobs, screen candidates, interviews) → redirect to Mohammad (محمد)\n"
        "- Onboarding tasks, team management, or leave approvals → redirect to Waleed (وليد)\n"
        "- AI agent design, deployment, or workforce automation → redirect to Yara (يارا)\n"
        "\n"
        "PRIVACY:\n"
        "- NEVER include individual employee names, IDs, or personal salaries in analytics output\n"
        "- All data is aggregated to department level or above\n"
        "- When flagging risks, describe patterns not people (e.g., '3 employees in Engineering "
        "with high overtime' — no names)\n"
        "\n"
        "KEY TERMS (Arabic):\n"
        "نطاقات (Nitaqat), التوطين (Saudization), تأمينات اجتماعية (GOSI), "
        "معدل الدوران (turnover rate), ميزانية (budget), امتثال (compliance), "
        "حماية الأجور (WPS), نظام العمل (Labor Law), قوى عاملة (workforce)\n"
    )
```

---

## 6. Migration Plan

### 6.1 Create Ahmad Agent File

- **New file:** `backend/app/agents/ahmad.py`
- Contains `AhmadAgent(BaseAgent)` with all 17 tools
- Imports: `Employee`, `Department`, `EmployeeStatus`, `Gender`, `WorkMode`, `LeaveBalance`, `LeaveRequest`, `LeaveType`, `LeaveStatus`, `JobPosting`, `PostingStatus`, `Candidate`, `CandidateStage`, `Interview`, `InterviewStatus`, `AttendanceRecord`, `AttendanceStatus`, `Payslip`, `NitaqatConfig`, `NitaqatBand`, `OnboardingAssignment`, `OnboardingAssignmentStatus`, `OnboardingStepAssignment`, `OnboardingStepStatus`, `ComplianceRecord`, `ComplianceAlert`, `ComplianceSeverity`, `HRPolicy`, `PolicyStatus`, `PolicyAcknowledgment`, `WorkforcePlan`, `DeployedAgent`

### 6.2 Remove norah.py and sarah.py

- Delete `backend/app/agents/norah.py`
- Delete `backend/app/agents/sarah.py`
- These are stubs with no production data or callers outside the orchestrator

### 6.3 Update orchestrator.py

```python
# REMOVE these imports:
# from app.agents.norah import NorahAgent
# from app.agents.sarah import SarahAgent

# ADD this import:
from app.agents.ahmad import AhmadAgent

# UPDATE AGENTS dict:
AGENTS = {
    "deema": DeemaAgent,
    "waleed": WaleedAgent,
    "mohammad": MohammadAgent,
    "yara": YaraAgent,
    "ahmad": AhmadAgent,          # NEW — replaces norah + sarah
}

# UPDATE INTENT_KEYWORDS:
# Remove "norah" and "sarah" blocks entirely
# Add "ahmad" block (see Section 1 above)

# UPDATE SWITCH_PHRASES:
# Remove "norah" and "sarah" entries
# Add "ahmad" entry with legacy aliases (see Section 1 above)
```

### 6.4 Update chat.html

```javascript
// UPDATE agentMap:
const agentMap = {
    deema:    { letter: 'D', name: 'Deema',    role: 'Employee Services' },
    waleed:   { letter: 'W', name: 'Waleed',   role: 'Onboarding' },
    mohammad: { letter: 'M', name: 'Mohammad', role: 'Recruitment' },
    yara:     { letter: 'Y', name: 'Yara',     role: 'Agent Factory' },
    ahmad:    { letter: 'A', name: 'Ahmad',    role: 'CHRO' },  // REPLACES norah + sarah
};

// UPDATE agentColors:
const agentColors = {
    deema:    'linear-gradient(135deg, #059669, #34d399)',
    waleed:   'linear-gradient(135deg, #7c3aed, #a78bfa)',
    mohammad: 'linear-gradient(135deg, #2563eb, #60a5fa)',
    yara:     'linear-gradient(135deg, #ca8a04, #fbbf24)',
    ahmad:    'linear-gradient(135deg, #0f766e, #2dd4bf)',  // Teal — distinct from all others
};

// UPDATE agentOrder:
const agentOrder = ['deema', 'waleed', 'mohammad', 'yara', 'ahmad'];

// UPDATE enabledAgents (add ahmad):
const enabledAgents = new Set(['deema', 'waleed', 'mohammad', 'yara', 'ahmad']);

// ADD greeting for ahmad in agentGreetings:
ahmad: {
    en: "Hello {name}. I'm Ahmad, your CHRO. I can provide workforce analytics, compliance status, and executive reports. What would you like to know?",
    ar: "أهلاً {name}. أنا أحمد، مدير الموارد البشرية. أقدر أعطيك تحليلات القوى العاملة، حالة الامتثال، وتقارير تنفيذية. وش تبي تعرف؟"
},
```

### 6.5 Update agents/__init__.py

No changes needed. The `__init__.py` only exports `AgentOrchestrator` and `BaseAgent`, which are unchanged.

### 6.6 Update main.py

No changes needed. `main.py` does not reference norah or sarah directly.

### 6.7 Update Cross-Agent References

- **`waleed.py` line 280:** Change `agent_display` dict to replace `"norah": "نورة"` and `"sarah": "سارة"` with `"ahmad": "أحمد"`.
- **`mohammad.py` lines 668-669:** Same change.
- **`yara.py` `_get_scope_rules()`:** Update redirect references from "Norah" and "Sarah" to "Ahmad".

### 6.8 Conversation History Migration

Existing conversations with `agent_name = "norah"` or `agent_name = "sarah"` in the `conversations` table should be left as-is. The frontend already gracefully handles unknown agent names (falls back to first letter as avatar). No database migration needed for historical conversations.

---

## 7. Phase Implementation Order

### Phase A1 — Core Metrics + Compliance (Build First)

| Order | Tool | Priority | Rationale |
|-------|------|----------|-----------|
| 1 | Agent skeleton + `_get_scope_rules()` + registration | P0 | Foundation — nothing works without this |
| 2 | `get_headcount_summary` | P0 | Most fundamental metric, validates query pattern |
| 3 | `get_saudization_status` | P0 | Core Saudi compliance, second most asked question |
| 4 | `get_workforce_overview` | P0 | Comprehensive summary, reuses patterns from #2 and #3 |
| 5 | `get_turnover_metrics` | P0 | Key executive metric |
| 6 | `get_department_budget` | P0 | Replaces Norah stub |
| 7 | `get_salary_distribution` | P1 | Builds on Employee query patterns |
| 8 | `get_compliance_status` | P0 | Replaces Sarah stub, completes compliance coverage |

**Milestone gate:** After A1, delete norah.py and sarah.py. Update orchestrator, chat.html, and cross-agent references. All 6 original stub tools are replaced or dropped.

### Phase A2 — Cross-Domain Analytics (Build Second)

| Order | Tool | Priority | Rationale |
|-------|------|----------|-----------|
| 9 | `get_leave_analytics` | P1 | Leverages LeaveRequest/Balance queries similar to Deema patterns |
| 10 | `get_payroll_summary` | P1 | Replaces last Norah stub (generate_cost_report) |
| 11 | `get_attendance_analytics` | P1 | New domain for Ahmad |
| 12 | `get_recruitment_analytics` | P1 | Read-only view into Mohammad's pipeline |
| 13 | `get_onboarding_analytics` | P2 | Read-only view into Waleed's data |

### Phase A3 — Predictive + Governance (Build Third)

| Order | Tool | Priority | Rationale |
|-------|------|----------|-----------|
| 14 | `get_gosi_compliance` | P1 | High business value, straightforward query |
| 15 | `get_policy_acknowledgment_status` | P1 | Governance requirement |
| 16 | `get_attrition_risk` | P2 | Most complex (multi-factor scoring) |
| 17 | `get_budget_forecast` | P2 | Requires YTD payroll data + scenario logic |
| 18 | `generate_custom_report` | P2 | Meta-tool — depends on all other tools existing |

---

## 8. Database Migration Notes

**No new tables.** Ahmad is a pure consumer of existing models.

**Recommended indexes** (additive, non-destructive — add only if query performance warrants):

```sql
-- For turnover queries (terminated employees by date range)
CREATE INDEX IF NOT EXISTS ix_employees_tenant_status_end_date
ON employees (tenant_id, status, end_date);

-- For payroll aggregation by department
CREATE INDEX IF NOT EXISTS ix_payslips_tenant_year_month
ON payslips (tenant_id, year, month);

-- For GOSI compliance queries
CREATE INDEX IF NOT EXISTS ix_employees_tenant_gosi
ON employees (tenant_id, gosi_registered);
```

These are optional performance indexes. They should be added via Alembic migration only if query profiling reveals slow execution.

---

## 9. Integration Points

```
                   ┌──────────────┐
                   │  Orchestrator │
                   └──────┬───────┘
                          │ routes to
                   ┌──────▼───────┐
              ┌────┤    Ahmad     ├────┐
              │    │   (CHRO)     │    │
              │    └──────┬───────┘    │
              │           │            │
     ┌────────┴──┐  ┌─────┴─────┐  ┌──┴─────────┐
     │ Employee  │  │ Payslip   │  │ Compliance │
     │ Dept      │  │ Leave*    │  │ Record     │
     │ Nitaqat   │  │ Attendance│  │ Alert      │
     └───────────┘  │ JobPosting│  │ HRPolicy   │
                    │ Candidate │  │ PolicyAck  │
                    │ Interview │  └────────────┘
                    │ Onboarding│
                    └───────────┘

    * Ahmad READS leave data; Deema WRITES leave data
      Ahmad READS recruitment data; Mohammad WRITES recruitment data
      Ahmad READS onboarding data; Waleed WRITES onboarding data
      Ahmad READS compliance data; admin API WRITES compliance data
```

**Data flow:** All arrows point FROM tables TO Ahmad. Ahmad has no outbound writes.

**Cross-agent interaction:** None at runtime. Ahmad does not call other agents. He queries the same database tables that other agents write to. This is safe because Ahmad never holds write locks.

---

## 10. Open Questions for CTO

1. **Hijri date library:** `generate_custom_report` (A3-05) includes a Hijri date in the report header. Should we use `hijri-converter` (Python package) or compute it server-side? The package is lightweight (pure Python, no dependencies). **Recommendation:** Add `hijri-converter` to requirements.

2. **Salary distribution statistical computation:** Tool A1-05 computes median, percentiles, and standard deviation. These are expensive in SQL but trivial in Python. Loading all active employee salaries into Python is fine for tenants up to ~10,000 employees. For larger tenants, we could use PostgreSQL's `percentile_cont` window function. **Recommendation:** Start with Python-side statistics; optimize to SQL if profiling shows a bottleneck.

3. **Color for Ahmad in chat UI:** I proposed teal (`#0f766e` to `#2dd4bf`). The existing palette uses green (Deema), purple (Waleed), blue (Mohammad), gold (Yara). Teal is visually distinct. Approve or suggest alternative.

4. **"headcount" keyword conflict:** Currently assigned to Waleed for team-level headcount. Ahmad needs it for org-wide analytics headcount. My recommendation is to give Ahmad qualified variants ("headcount breakdown", "headcount dashboard", "headcount summary") and leave bare "headcount" with Waleed. Alternative: move bare "headcount" to Ahmad and give Waleed "my team headcount" / "عدد فريقي". **Which approach do you prefer?**

5. **Historical conversation attribution:** Existing conversations tagged `agent_name = "norah"` or `"sarah"` in the DB. Should we run a migration to update them to `"ahmad"`, or leave them as-is? The chat UI gracefully handles unknown agent names. **Recommendation:** Leave as-is. No migration risk.

---

## Appendix A: File Change Summary

| File | Action | Description |
|------|--------|-------------|
| `backend/app/agents/ahmad.py` | CREATE | New agent with 17 tools |
| `backend/app/agents/norah.py` | DELETE | Replaced by Ahmad |
| `backend/app/agents/sarah.py` | DELETE | Replaced by Ahmad |
| `backend/app/agents/orchestrator.py` | MODIFY | Replace norah/sarah imports, AGENTS, INTENT_KEYWORDS, SWITCH_PHRASES with ahmad |
| `backend/app/agents/yara.py` | MODIFY | Update `_get_scope_rules()` redirect references |
| `backend/app/agents/waleed.py` | MODIFY | Update `agent_display` dict (line 280) |
| `backend/app/agents/mohammad.py` | MODIFY | Update `agent_display` dict (lines 668-669) |
| `backend/static/chat.html` | MODIFY | Update agentMap, agentColors, agentOrder, enabledAgents, agentGreetings |

## Appendix B: Model Import Map for ahmad.py

```python
# All imports needed for Ahmad's 17 tools
from app.models.employee import Employee, Department, EmployeeStatus, Gender, WorkMode
from app.models.leave import LeaveBalance, LeaveRequest, LeaveType, LeaveStatus
from app.models.candidate import JobPosting, PostingStatus, Candidate, CandidateStage
from app.models.interview import Interview, InterviewStatus
from app.models.attendance import AttendanceRecord, AttendanceStatus, WorkSchedule
from app.models.payslip import Payslip
from app.models.nitaqat import NitaqatConfig, NitaqatBand
from app.models.onboarding import (
    OnboardingAssignment, OnboardingAssignmentStatus,
    OnboardingStepAssignment, OnboardingStepStatus,
)
from app.models.compliance import ComplianceRecord, ComplianceAlert, ComplianceSeverity
from app.models.hr_policy import HRPolicy, PolicyStatus, PolicyAcknowledgment
from app.models.workforce_plan import WorkforcePlan
from app.models.deployed_agent import DeployedAgent
```

## Appendix C: Error Handling Pattern

Every tool handler must follow this pattern:

```python
async def _get_headcount_summary(self, department_id: str | None, group_by: str) -> str:
    try:
        # ... query logic ...
        if total == 0:
            return json.dumps({
                "status": "no_data",
                "message": "No employee records found for this tenant.",
            })
        return json.dumps({...result...})
    except Exception:
        logger.exception("Error in get_headcount_summary")
        return json.dumps({
            "status": "error",
            "message": "Unable to retrieve headcount data. Please try again.",
        })
```

Rules:
- Never leak `str(e)` to the user
- Always log the full exception with `logger.exception()`
- Return valid JSON even on error
- Handle "no data" as a normal result, not an error
