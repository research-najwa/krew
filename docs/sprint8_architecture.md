# Sprint 8 Technical Architecture

**Author:** Faisal (System Architect)
**Date:** 2026-03-30
**Status:** Ready for Implementation
**Tracks:**
1. Ahmad A3 -- Predictive & Advanced Analytics (5 tools)
2. Dynamic Quick Actions (per-agent switching)
3. Knowledge Management Module (data model, ingestion, scoped RAG, admin API, UI)
4. Ahmad English-Only Responses

---

## Table of Contents

1. [Overview & Dependency Chain](#overview--dependency-chain)
2. [Track 1: Ahmad A3 -- Predictive Analytics](#track-1-ahmad-a3--predictive-analytics)
   - [A3-01: predict_attrition_risk](#a3-01-predict_attrition_risk)
   - [A3-02: forecast_budget](#a3-02-forecast_budget)
   - [A3-03: audit_gosi_compliance](#a3-03-audit_gosi_compliance)
   - [A3-04: get_policy_acknowledgments](#a3-04-get_policy_acknowledgments)
   - [A3-05: generate_custom_report](#a3-05-generate_custom_report)
3. [Track 2: Dynamic Quick Actions](#track-2-dynamic-quick-actions)
4. [Track 3: Knowledge Management Module](#track-3-knowledge-management-module)
5. [Track 4: Ahmad English-Only Responses](#track-4-ahmad-english-only-responses)
6. [Track 5: Unified Chat with @Mention Routing](#track-5-unified-chat-with-mention-routing)
7. [Database Migration Notes](#database-migration-notes)
8. [Build Order](#build-order)
9. [Testing Strategy](#testing-strategy)
10. [Open Questions](#open-questions)

---

## Overview & Dependency Chain

Sprint 8 has four parallel tracks with the following dependency graph:

```
Track 4 (Ahmad English-Only) ─── no deps, can ship first
       │
Track 1 (Ahmad A3) ─────────── depends on Track 4 (language rule in scope_rules)
       │
       ├── A3-01 predict_attrition_risk (independent)
       ├── A3-02 forecast_budget (independent)
       ├── A3-03 audit_gosi_compliance (independent, needs Payslip model audit)
       ├── A3-04 get_policy_acknowledgments (independent, needs HRPolicy + PolicyAcknowledgment)
       └── A3-05 generate_custom_report (depends on ALL A1+A2+A3 tools — build last)

Track 2 (Dynamic Quick Actions) ─── no deps on other tracks
       │
       ├── S8-CUX-04-01 Backend (independent)
       ├── S8-CUX-04-02 Frontend (depends on 04-01)
       └── S8-CUX-04-03 Suggestion chips (depends on 04-01)

Track 3 (Knowledge Management) ─── independent track, internal chain:
       │
       ├── S8-KM-01 Data model (first — all others depend on this)
       ├── S8-KM-02 Ingestion pipeline (depends on KM-01)
       ├── S8-KM-03 Scoped RAG retriever (depends on KM-01)
       ├── S8-KM-04 Admin API (depends on KM-01, KM-02, KM-03)
       ├── S8-KM-05 Knowledge UI (depends on KM-04)
       └── S8-KM-06 Policy migration (depends on KM-01, KM-02)
```

**Critical path:** Track 3 is the longest chain (6 stories). Track 1 A3-05 must be built last within its track since it orchestrates all other Ahmad tools.

---

## Track 1: Ahmad A3 -- Predictive Analytics

### Design Principles (inherited from A1/A2, extended for A3)

- **Read-only**: Ahmad never modifies data. All tools are SELECT-only.
- **Multi-tenant**: Every query filters by `tenant_id`. Models without `tenant_id` (LeaveRequest, LeaveBalance) use JOINs to Employee for isolation.
- **k-anonymity**: `MIN_GROUP_SIZE = 5`. Groups below threshold get metrics suppressed.
- **No PII in aggregated output**: Never return names, emails, phone numbers, or national IDs in department-level results. Individual-level data (A3-01, A3-03) requires HR/manager role validation.
- **Error pattern**: All tools return `json.dumps({"error": "..."})` on validation failure.
- **department_id validation**: UUID validation in `handle_tool_call` before dispatch (existing pattern).
- **English-only responses**: Ahmad always responds in English per Track 4. Suggestion chips remain bilingual.
- **GOSI constants** (used in A3-02 and A3-03):

```python
GOSI_EMPLOYER_SAUDI_PCT = 0.12    # 9.75% annuity + 1% SANED + 1.25% occupational
GOSI_EMPLOYEE_SAUDI_PCT = 0.10    # 9.75% annuity + 0.25% SANED
GOSI_EMPLOYER_NON_SAUDI_PCT = 0.02  # 2% occupational hazards only
GOSI_EMPLOYEE_NON_SAUDI_PCT = 0.0   # Non-Saudis pay nothing
GOSI_SALARY_CEILING_SAR = 45_000    # Monthly ceiling for GOSI contributions
```

### New Imports Required in `ahmad.py`

```python
# Add to existing imports
from app.models.hr_policy import HRPolicy, PolicyAcknowledgment, PolicyStatus, PolicyCategory
```

All other models (Employee, Department, LeaveRequest, AttendanceRecord, Payslip) are already imported from A1/A2.

---

### A3-01: predict_attrition_risk

#### Tool Definition

```json
{
    "name": "predict_attrition_risk",
    "description": "Score employees or departments on attrition (flight) risk using tenure, salary position relative to department median, leave patterns, attendance trends, and time-since-last-promotion. Returns risk tiers (high/medium/low) with contributing factors. PRIVACY: Individual-level results require manager/HR role; department-level is always aggregated.",
    "input_schema": {
        "type": "object",
        "properties": {
            "department_id": {
                "type": "string",
                "description": "Optional department UUID. If omitted, returns org-wide department risk ranking."
            },
            "include_individuals": {
                "type": "boolean",
                "description": "If true and requester has manager/HR role, include individual employee risk scores. Default false."
            },
            "risk_threshold": {
                "type": "string",
                "enum": ["high", "medium", "low"],
                "description": "Only return employees/departments at or above this risk level. Default: all."
            }
        },
        "required": []
    }
}
```

#### Method Signature & Query Plan

```python
async def _predict_attrition_risk(self, tool_input: dict) -> str:
```

**Tables:** `Employee`, `Department`, `LeaveRequest`, `AttendanceRecord`

**Risk Score Computation (weighted composite 0-100):**

| Factor | Weight | Source | High-Risk Signal |
|--------|--------|--------|-----------------|
| Tenure risk | 30% | `Employee.hire_date` | < 1 year or > 5 years tenure |
| Salary position | 25% | `Employee.salary_sar` vs dept median | Below 25th percentile in department |
| Leave pattern | 20% | `LeaveRequest` (sick, approved) | 2x+ spike in sick leave (last 3 months vs prior 9) |
| Attendance trend | 15% | `AttendanceRecord` (late/absent) | Increasing late arrivals over last 3 months |
| Stagnation | 10% | `Employee.updated_at` proxy | No change in 24+ months |

**Query 1 -- Active employees with department:**
```python
active_statuses = [EmployeeStatus.active, EmployeeStatus.onboarding, EmployeeStatus.on_leave]
emp_q = (
    select(
        Employee.id,
        Employee.department_id,
        Employee.hire_date,
        Employee.salary_sar,
        Employee.is_saudi,
        Employee.updated_at,
        Employee.manager_id,
        Employee.probation_end_date,
        Department.name.label("dept_name"),
    )
    .join(Department, Employee.department_id == Department.id)
    .where(
        Employee.tenant_id == self.tenant_id,
        Employee.status.in_(active_statuses),
    )
)
# Optional: .where(Employee.department_id == department_id)
```

**Query 2 -- Sick leave counts per employee (last 12 months, approved only):**
```python
twelve_months_ago = date.today() - timedelta(days=365)
three_months_ago = date.today() - timedelta(days=90)

sick_leave_q = (
    select(
        LeaveRequest.employee_id,
        func.sum(
            case(
                (LeaveRequest.start_date >= three_months_ago, LeaveRequest.business_days),
                else_=0,
            )
        ).label("recent_sick_days"),
        func.sum(
            case(
                (LeaveRequest.start_date < three_months_ago, LeaveRequest.business_days),
                else_=0,
            )
        ).label("prior_sick_days"),
    )
    .join(Employee, LeaveRequest.employee_id == Employee.id)
    .where(
        Employee.tenant_id == self.tenant_id,
        LeaveRequest.leave_type == LeaveType.sick,
        LeaveRequest.status == LeaveStatus.approved,
        LeaveRequest.start_date >= twelve_months_ago,
    )
    .group_by(LeaveRequest.employee_id)
)
```

**Query 3 -- Attendance trend per employee (last 12 months, late + absent):**
```python
attendance_q = (
    select(
        AttendanceRecord.employee_id,
        func.sum(
            case(
                (
                    (AttendanceRecord.date >= three_months_ago) &
                    (AttendanceRecord.status.in_([AttendanceStatus.late, AttendanceStatus.absent])),
                    1,
                ),
                else_=0,
            )
        ).label("recent_issues"),
        func.sum(
            case(
                (
                    (AttendanceRecord.date < three_months_ago) &
                    (AttendanceRecord.date >= twelve_months_ago) &
                    (AttendanceRecord.status.in_([AttendanceStatus.late, AttendanceStatus.absent])),
                    1,
                ),
                else_=0,
            )
        ).label("prior_issues"),
    )
    .where(
        AttendanceRecord.tenant_id == self.tenant_id,
        AttendanceRecord.date >= twelve_months_ago,
    )
    .group_by(AttendanceRecord.employee_id)
)
```

**Risk Scoring Algorithm (in Python after queries):**

```python
def _compute_risk_score(
    self,
    hire_date: date,
    salary_sar: int | None,
    dept_median_salary: float,
    dept_p25_salary: float,
    recent_sick_days: int,
    prior_sick_days: int,
    recent_attendance_issues: int,
    prior_attendance_issues: int,
    last_updated: datetime,
    probation_end_date: date | None,
) -> tuple[float, list[str]]:
    """Returns (score 0-100, list of contributing factor names)."""
    factors = {}
    today = date.today()

    # 1. Tenure risk (30%)
    tenure_days = (today - hire_date).days
    if tenure_days < 365:
        factors["short_tenure"] = 75.0  # New hire flight risk
    elif tenure_days > 5 * 365:
        factors["long_tenure_stagnation"] = 60.0
    else:
        factors["tenure"] = max(0, 50 - (tenure_days / 365) * 5)  # Decreasing risk 1-5 years
    tenure_score = list(factors.values())[-1]

    # 2. Salary position (25%)
    if salary_sar and dept_median_salary > 0:
        if salary_sar <= dept_p25_salary:
            salary_score = 80.0
            factors["below_25pct_salary"] = salary_score
        elif salary_sar < dept_median_salary:
            salary_score = 50.0
            factors["below_median_salary"] = salary_score
        else:
            salary_score = 20.0
    else:
        salary_score = 50.0  # Neutral when data missing

    # 3. Leave pattern (20%) -- 2x spike detection
    prior_monthly_avg = prior_sick_days / 9.0 if prior_sick_days > 0 else 0
    recent_monthly_avg = recent_sick_days / 3.0
    if prior_monthly_avg > 0 and recent_monthly_avg >= 2 * prior_monthly_avg:
        leave_score = 80.0
        factors["sick_leave_spike"] = leave_score
    elif recent_sick_days > 5:
        leave_score = 50.0
    else:
        leave_score = 20.0  # Healthy pattern

    # 4. Attendance trend (15%)
    prior_monthly_att = prior_attendance_issues / 9.0 if prior_attendance_issues > 0 else 0
    recent_monthly_att = recent_attendance_issues / 3.0
    if prior_monthly_att > 0 and recent_monthly_att >= 1.5 * prior_monthly_att:
        attend_score = 75.0
        factors["attendance_deterioration"] = attend_score
    elif recent_attendance_issues > 6:
        attend_score = 50.0
    else:
        attend_score = 20.0

    # 5. Stagnation (10%)
    months_since_update = (today - last_updated.date()).days / 30
    if months_since_update >= 24:
        stag_score = 80.0
        factors["no_change_24m"] = stag_score
    elif months_since_update >= 12:
        stag_score = 50.0
    else:
        stag_score = 20.0

    # Weighted composite
    score = (
        tenure_score * 0.30
        + salary_score * 0.25
        + leave_score * 0.20
        + attend_score * 0.15
        + stag_score * 0.10
    )

    top_factors = sorted(factors.keys(), key=lambda k: factors[k], reverse=True)[:2]
    return round(score, 1), top_factors
```

**Risk tier mapping:**
```python
def _risk_tier(score: float) -> str:
    if score >= 70:
        return "high"
    elif score >= 40:
        return "medium"
    return "low"
```

**Threshold-to-int mapping for filter:**
```python
RISK_THRESHOLD_MIN = {"high": 70, "medium": 40, "low": 0}
```

#### Response Schema

```json
{
    "departments": [
        {
            "department_name": "Engineering",
            "department_id": "uuid",
            "headcount": 25,
            "avg_risk_score": 52.3,
            "risk_tier": "medium",
            "high_risk_count": 4,
            "medium_risk_count": 12,
            "low_risk_count": 9,
            "top_risk_factors": ["below_median_salary", "sick_leave_spike"]
        }
    ],
    "too_small_to_report": ["uuid-of-dept-with-less-than-5"],
    "individuals": [
        {
            "employee_id": "uuid",
            "department_name": "Engineering",
            "risk_score": 78.5,
            "risk_tier": "high",
            "factors": {
                "below_25pct_salary": 80.0,
                "sick_leave_spike": 80.0
            },
            "is_probation": false
        }
    ],
    "summary": {
        "org_avg_risk_score": 45.2,
        "org_risk_tier": "medium",
        "total_high_risk": 12,
        "total_medium_risk": 35,
        "total_low_risk": 53,
        "departments_analyzed": 5,
        "departments_excluded_privacy": 2
    },
    "saudi_context": {
        "probation_employees_flagged": 3,
        "note": "Employees in probation period (first 90 days per Saudi Labor Law Article 53) have different termination dynamics and are flagged separately."
    }
}
```

**When `include_individuals == false` (default):** The `individuals` array is omitted entirely.

**When `include_individuals == true`:** Employee names are NOT included. Only `employee_id` and `department_name`. The requesting employee can cross-reference IDs if they have appropriate access.

#### Privacy & Security

- Department-level: k-anonymity enforced. Departments with fewer than `MIN_GROUP_SIZE` employees listed under `too_small_to_report` (UUIDs only, no metrics).
- Individual-level: Requires `include_individuals == true`. No employee names in output. Employee ID only.
- Salary data never exposed directly -- only the relative position (factor name, not actual salary).
- Tenant isolation via `Employee.tenant_id == self.tenant_id` on all queries.

#### Edge Cases

- **New employee (< 30 days):** Skip leave/attendance signals. Score based on salary position and department baseline only. Flag with `"new_hire": true`.
- **Department with all employees below median salary:** Normalize within department (use department-internal percentiles, not org-wide).
- **Employee with zero leave or attendance records:** Score those factors as neutral (score = 50, equivalent to 50th percentile).
- **Ramadan period:** Exclude Ramadan months from attendance trend analysis. Use `app.saudi_holidays._EID_DATES` to identify approximate Ramadan window.

#### Follow-Up Suggestions

```python
"predict_attrition_risk": [
    "معدل الدوران" if ar else "Turnover metrics",
    "توزيع الرواتب" if ar else "Salary distribution",
    "نظرة عامة على القوى العاملة" if ar else "Workforce overview",
],
```

---

### A3-02: forecast_budget

#### Tool Definition

```json
{
    "name": "forecast_budget",
    "description": "Project payroll costs forward 3/6/12 months. Includes base payroll from current headcount, GOSI contributions (12% employer for Saudis, 2% for non-Saudis), and growth scenarios (flat, moderate +5%, aggressive +10% headcount growth). Optionally filter by department.",
    "input_schema": {
        "type": "object",
        "properties": {
            "department_id": {
                "type": "string",
                "description": "Optional department UUID. If omitted, forecasts org-wide."
            },
            "horizon_months": {
                "type": "integer",
                "description": "Forecast horizon: 3, 6, or 12 months. Default 6.",
                "enum": [3, 6, 12]
            },
            "growth_scenario": {
                "type": "string",
                "enum": ["flat", "moderate", "aggressive", "custom"],
                "description": "Headcount growth scenario. 'flat' = 0% growth, 'moderate' = 5% annual, 'aggressive' = 10% annual. Default: returns all three."
            },
            "custom_growth_pct": {
                "type": "number",
                "description": "Annual headcount growth percentage when growth_scenario is 'custom'. e.g. 7.5 for 7.5%."
            }
        },
        "required": []
    }
}
```

#### Method Signature & Query Plan

```python
async def _forecast_budget(self, tool_input: dict) -> str:
```

**Tables:** `Employee`, `Department`

**Query 1 -- Current payroll baseline (active employees):**
```python
active_statuses = [EmployeeStatus.active, EmployeeStatus.onboarding, EmployeeStatus.on_leave]
baseline_q = (
    select(
        func.count(Employee.id).label("headcount"),
        func.coalesce(func.sum(Employee.salary_sar), 0).label("total_monthly_salary"),
        func.coalesce(
            func.sum(case((Employee.is_saudi == True, Employee.salary_sar), else_=0)), 0
        ).label("saudi_salary_total"),
        func.coalesce(
            func.sum(case((Employee.is_saudi == False, Employee.salary_sar), else_=0)), 0
        ).label("non_saudi_salary_total"),
        func.coalesce(
            func.sum(case((Employee.is_saudi == True, 1), else_=0)), 0
        ).label("saudi_count"),
        func.coalesce(
            func.sum(case((Employee.is_saudi == False, 1), else_=0)), 0
        ).label("non_saudi_count"),
    )
    .where(
        Employee.tenant_id == self.tenant_id,
        Employee.status.in_(active_statuses),
        Employee.salary_sar.isnot(None),
    )
)
# Optional: .where(Employee.department_id == department_id)
```

**GOSI calculation (in Python):**
```python
# Cap each employee's GOSI-eligible salary at SAR 45,000
# For aggregate estimation, cap the average salary:
avg_salary_saudi = saudi_salary_total / saudi_count if saudi_count > 0 else 0
avg_salary_non_saudi = non_saudi_salary_total / non_saudi_count if non_saudi_count > 0 else 0

# GOSI employer contribution:
gosi_saudi = saudi_count * min(avg_salary_saudi, GOSI_SALARY_CEILING_SAR) * GOSI_EMPLOYER_SAUDI_PCT
gosi_non_saudi = non_saudi_count * min(avg_salary_non_saudi, GOSI_SALARY_CEILING_SAR) * GOSI_EMPLOYER_NON_SAUDI_PCT

baseline_monthly_cost = total_monthly_salary + gosi_saudi + gosi_non_saudi
```

**Forecast formula:**
```python
GROWTH_RATES = {
    "flat": 0.0,
    "moderate": 0.05,
    "aggressive": 0.10,
}

def _project_month(baseline: float, headcount: int, annual_rate: float, month: int):
    monthly_rate = annual_rate / 12
    factor = (1 + monthly_rate) ** month
    return {
        "month_number": month,
        "month_label": (date.today() + timedelta(days=month * 30)).strftime("%b %Y"),
        "projected_headcount": round(headcount * factor),
        "projected_monthly_payroll_sar": round(total_monthly_salary * factor),
        "projected_gosi_sar": round((gosi_saudi + gosi_non_saudi) * factor),
        "projected_total_sar": round(baseline * factor),
    }
```

#### Response Schema

```json
{
    "current_baseline": {
        "headcount": 100,
        "saudi_count": 35,
        "non_saudi_count": 65,
        "saudi_pct": 35.0,
        "monthly_payroll_sar": 1500000,
        "monthly_gosi_employer_sar": 95000,
        "monthly_total_cost_sar": 1595000
    },
    "scenarios": {
        "flat": {
            "growth_pct_annual": 0.0,
            "forecast": [
                {
                    "month_number": 1,
                    "month_label": "Apr 2026",
                    "projected_headcount": 100,
                    "projected_monthly_payroll_sar": 1500000,
                    "projected_gosi_sar": 95000,
                    "projected_total_sar": 1595000
                }
            ],
            "summary": {
                "end_monthly_cost_sar": 1595000,
                "total_period_cost_sar": 9570000,
                "cost_increase_pct": 0.0
            }
        },
        "moderate": { "...same structure..." },
        "aggressive": { "...same structure..." }
    },
    "nitaqat_note": "Current Saudization is 35.0%. If hiring under 'aggressive' scenario, maintaining this ratio requires 4 new Saudi hires out of 10 total."
}
```

When a specific `growth_scenario` is provided, only that scenario is returned under `scenarios`. When omitted, all three (flat, moderate, aggressive) are returned.

#### Privacy & Security

- k-anonymity: departments with fewer than `MIN_GROUP_SIZE` employees return `{"error": "department_too_small"}`.
- No individual salary data exposed. Only aggregate totals.
- Tenant isolation via `Employee.tenant_id == self.tenant_id`.

#### Edge Cases

- **Department with only non-Saudi employees:** GOSI uses 2% rate only. `saudi_pct = 0.0`.
- **`custom_growth_pct` without `growth_scenario == "custom"`:** Ignore `custom_growth_pct`.
- **Negative `custom_growth_pct`:** Return `{"error": "Negative growth rate is not supported. Use flat (0%) for no-growth projection."}`.
- **Employees with NULL `salary_sar`:** Excluded from payroll calculation but counted in headcount with a warning: `"employees_missing_salary": N`.

#### Follow-Up Suggestions

```python
"forecast_budget": [
    "ميزانية القسم" if ar else "Department budget",
    "ملخص عدد الموظفين" if ar else "Headcount summary",
    "توزيع الرواتب" if ar else "Salary distribution",
],
```

---

### A3-03: audit_gosi_compliance

#### Tool Definition

```json
{
    "name": "audit_gosi_compliance",
    "description": "Cross-check GOSI contributions in payslips against employee salary records. Flags discrepancies where the recorded GOSI employer/employee deduction does not match the expected rate (12%/10% for Saudis, 2%/0% for non-Saudis). Returns flagged employees with discrepancy details.",
    "input_schema": {
        "type": "object",
        "properties": {
            "department_id": {
                "type": "string",
                "description": "Optional department UUID to scope the audit."
            },
            "month": {
                "type": "string",
                "description": "Month to audit in YYYY-MM format. Default: most recent payslip month."
            },
            "tolerance_pct": {
                "type": "number",
                "description": "Acceptable deviation percentage (default 1.0). Discrepancies within tolerance are marked as 'minor'."
            }
        },
        "required": []
    }
}
```

#### Method Signature & Query Plan

```python
async def _audit_gosi_compliance(self, tool_input: dict) -> str:
```

**Tables:** `Payslip`, `Employee`, `Department`

**Payslip model field mapping (from `/backend/app/models/payslip.py`):**
- `Payslip.basic_salary` -- base salary recorded in payslip (source of truth for GOSI calculation)
- `Payslip.gosi_employee` -- employee GOSI deduction as recorded
- No `gosi_employer` column exists -- employer share must be derived

**Query 1 -- Resolve target month (default: most recent payslip month):**
```python
if not month_str:
    latest_q = (
        select(Payslip.year, Payslip.month)
        .where(Payslip.tenant_id == self.tenant_id)
        .order_by(Payslip.year.desc(), Payslip.month.desc())
        .limit(1)
    )
    # Extract year, month from result
```

**Query 2 -- All payslips for the target month with employee data:**
```python
audit_q = (
    select(
        Payslip.id,
        Payslip.employee_id,
        Payslip.basic_salary,
        Payslip.gosi_employee,
        Employee.is_saudi,
        Employee.salary_sar,
        Employee.department_id,
        Department.name.label("dept_name"),
    )
    .join(Employee, Payslip.employee_id == Employee.id)
    .join(Department, Employee.department_id == Department.id)
    .where(
        Payslip.tenant_id == self.tenant_id,
        Payslip.year == target_year,
        Payslip.month == target_month,
    )
)
# Optional: .where(Employee.department_id == department_id)
```

**GOSI compliance check (in Python per payslip row):**
```python
tolerance_pct = tool_input.get("tolerance_pct", 1.0)

for row in payslip_rows:
    # Use payslip basic_salary as source of truth (handles mid-month changes)
    gosi_eligible_salary = min(row.basic_salary, GOSI_SALARY_CEILING_SAR)

    if row.is_saudi:
        expected_employee_gosi = round(gosi_eligible_salary * GOSI_EMPLOYEE_SAUDI_PCT)
        expected_employer_gosi = round(gosi_eligible_salary * GOSI_EMPLOYER_SAUDI_PCT)
    else:
        expected_employee_gosi = 0
        expected_employer_gosi = round(gosi_eligible_salary * GOSI_EMPLOYER_NON_SAUDI_PCT)

    actual_employee_gosi = row.gosi_employee

    # Check employee GOSI
    if expected_employee_gosi > 0:
        variance = abs(actual_employee_gosi - expected_employee_gosi)
        variance_pct = (variance / expected_employee_gosi) * 100
    elif actual_employee_gosi > 0:
        # Non-Saudi with unexpected deduction
        variance_pct = 100.0
    else:
        variance_pct = 0.0

    if row.gosi_employee is None:
        severity = "missing_gosi_data"
    elif variance_pct > tolerance_pct * 2:
        severity = "major"
    elif variance_pct > tolerance_pct:
        severity = "minor"
    else:
        severity = "compliant"
```

#### Response Schema

```json
{
    "audit_month": "2026-03",
    "summary": {
        "total_employees_audited": 100,
        "compliant_count": 92,
        "minor_discrepancy_count": 5,
        "major_discrepancy_count": 2,
        "missing_gosi_data_count": 1,
        "total_expected_employer_gosi_sar": 95000,
        "total_actual_employee_gosi_sar": 78000,
        "total_expected_employee_gosi_sar": 79000,
        "total_variance_sar": 1200
    },
    "discrepancies": [
        {
            "employee_id": "uuid",
            "department_name": "Engineering",
            "nationality_type": "saudi",
            "payslip_basic_salary_sar": 15000,
            "gosi_eligible_salary_sar": 15000,
            "expected_employee_gosi_sar": 1500,
            "actual_employee_gosi_sar": 1200,
            "variance_sar": 300,
            "variance_pct": 20.0,
            "severity": "major"
        }
    ],
    "gosi_rates_applied": {
        "saudi_employer_pct": 12.0,
        "saudi_employee_pct": 10.0,
        "non_saudi_employer_pct": 2.0,
        "non_saudi_employee_pct": 0.0,
        "salary_ceiling_sar": 45000
    },
    "notes": [
        "Employer GOSI share is estimated (no gosi_employer column in payslips). Actual billing may vary.",
        "GOSI salary ceiling of SAR 45,000 applied to contributions above this threshold."
    ]
}
```

#### Privacy & Security

- **Audit tool exception:** Individual employee IDs are included in discrepancy results since this is an audit tool restricted to HR/CHRO role. No employee names in output.
- Tenant isolation via `Payslip.tenant_id == self.tenant_id`.
- k-anonymity does NOT apply to this audit tool (it is per-employee by design).

#### Edge Cases

- **Employee salary changed mid-month:** Use `Payslip.basic_salary` as source of truth, not `Employee.salary_sar`.
- **Employee terminated mid-month:** Include in audit if payslip exists.
- **Payslip with NULL `gosi_employee`:** Flag as `"missing_gosi_data"` severity.
- **No payslips for target month:** Return `{"message": "No payslip data found for 2026-03. Ensure payroll has been processed."}`.
- **Salary above GOSI ceiling:** Expected GOSI capped at ceiling rate. Discrepancy only flagged if actual deduction differs from capped amount.

#### Follow-Up Suggestions

```python
"audit_gosi_compliance": [
    "ملخص الرواتب" if ar else "Payroll summary",
    "وضع الامتثال" if ar else "Compliance status",
    "نظرة عامة على القوى العاملة" if ar else "Workforce overview",
],
```

---

### A3-04: get_policy_acknowledgments

#### Tool Definition

```json
{
    "name": "get_policy_acknowledgments",
    "description": "Track policy acknowledgment compliance. Shows which published policies employees have/haven't acknowledged, compliance rates by department, and overdue acknowledgments. Uses the hr_policies and policy_acknowledgments tables.",
    "input_schema": {
        "type": "object",
        "properties": {
            "policy_id": {
                "type": "string",
                "description": "Optional specific policy UUID to check acknowledgments for."
            },
            "department_id": {
                "type": "string",
                "description": "Optional department UUID to filter employees."
            },
            "category": {
                "type": "string",
                "description": "Optional policy category filter (leave, attendance, conduct, compensation, benefits, safety, general)."
            }
        },
        "required": []
    }
}
```

#### Method Signature & Query Plan

```python
async def _get_policy_acknowledgments(self, tool_input: dict) -> str:
```

**Tables:** `HRPolicy`, `PolicyAcknowledgment`, `Employee`, `Department`

**Query 1 -- Published policies in scope:**
```python
policy_q = (
    select(HRPolicy)
    .where(
        HRPolicy.tenant_id == self.tenant_id,
        HRPolicy.status == PolicyStatus.published,
        HRPolicy.effective_date <= date.today(),  # Only in-effect policies
    )
)
if policy_id:
    policy_q = policy_q.where(HRPolicy.id == policy_id)
if category:
    policy_q = policy_q.where(HRPolicy.category == category)
```

**Query 2 -- Active employee count (total and by department):**
```python
active_statuses = [EmployeeStatus.active, EmployeeStatus.onboarding, EmployeeStatus.on_leave]
emp_count_q = (
    select(
        Employee.department_id,
        func.count(Employee.id).label("active_count"),
    )
    .where(
        Employee.tenant_id == self.tenant_id,
        Employee.status.in_(active_statuses),
    )
    .group_by(Employee.department_id)
)
# Optional: .where(Employee.department_id == department_id)
```

**Query 3 -- Acknowledgment counts per policy and department:**
```python
ack_q = (
    select(
        PolicyAcknowledgment.policy_id,
        Employee.department_id,
        func.count(PolicyAcknowledgment.id).label("ack_count"),
    )
    .join(Employee, PolicyAcknowledgment.employee_id == Employee.id)
    .where(
        PolicyAcknowledgment.tenant_id == self.tenant_id,
        Employee.status.in_(active_statuses),
    )
    .group_by(PolicyAcknowledgment.policy_id, Employee.department_id)
)
# Optional: .where(Employee.department_id == department_id)
```

**Query 4 -- Non-compliant employees (only when `policy_id` specified):**
```python
if policy_id:
    # Subquery: employees who HAVE acknowledged
    acked_subq = (
        select(PolicyAcknowledgment.employee_id)
        .where(PolicyAcknowledgment.policy_id == policy_id)
    ).subquery()

    non_compliant_q = (
        select(Employee.id, Department.name.label("dept_name"))
        .join(Department, Employee.department_id == Department.id)
        .where(
            Employee.tenant_id == self.tenant_id,
            Employee.status.in_(active_statuses),
            Employee.id.notin_(select(acked_subq.c.employee_id)),
        )
    )
    # Optional: .where(Employee.department_id == department_id)
```

#### Response Schema

```json
{
    "policies": [
        {
            "policy_id": "uuid",
            "title": "Annual Leave Policy",
            "title_ar": "سياسة الإجازة السنوية",
            "category": "leave",
            "effective_date": "2026-01-01",
            "compliance_rate_pct": 85.0,
            "acknowledged_count": 85,
            "not_acknowledged_count": 15,
            "mandatory": false
        }
    ],
    "by_department": [
        {
            "department_name": "Engineering",
            "department_id": "uuid",
            "total_policies": 5,
            "avg_compliance_rate_pct": 78.5,
            "lowest_compliance_policy": {
                "title": "Workplace Safety",
                "compliance_rate_pct": 45.0
            }
        }
    ],
    "summary": {
        "total_published_policies": 8,
        "org_wide_compliance_rate_pct": 82.3,
        "fully_compliant_policies_count": 3,
        "critical_gaps": [
            {
                "title": "Workplace Safety",
                "compliance_rate_pct": 45.0,
                "category": "safety",
                "mandatory": true
            }
        ]
    },
    "non_compliant_employees": [
        {
            "employee_id": "uuid",
            "department_name": "Engineering"
        }
    ],
    "saudi_context": {
        "mandatory_policy_categories": ["safety", "conduct"],
        "note": "Policies in 'safety' and 'conduct' categories are flagged as mandatory per Saudi Labor Law Articles 121 and 98."
    }
}
```

**`non_compliant_employees` is only included when `policy_id` is specified.**

#### Privacy & Security

- k-anonymity: departments with fewer than `MIN_GROUP_SIZE` employees grouped under "Other" in `by_department`.
- `non_compliant_employees` returns `employee_id` only (no names) in default mode.
- Tenant isolation via `HRPolicy.tenant_id` and `Employee.tenant_id`.

#### Edge Cases

- **New policy (published today):** 0% compliance expected, NOT flagged as critical gap.
- **Employee with no PolicyAcknowledgment records:** Counts as not acknowledged for all policies.
- **Archived policy:** Excluded from tracking (`HRPolicy.status == published` filter).
- **Policy with future `effective_date`:** Excluded (not yet in effect).

#### Follow-Up Suggestions

```python
"get_policy_acknowledgments": [
    "وضع الامتثال" if ar else "Compliance status",
    "نظرة عامة على القوى العاملة" if ar else "Workforce overview",
    "ملخص عدد الموظفين" if ar else "Headcount summary",
],
```

---

### A3-05: generate_custom_report

#### Tool Definition

```json
{
    "name": "generate_custom_report",
    "description": "Generate a custom HR report from a natural language query. Ahmad interprets the request, determines which data sources and existing tools to combine, executes the queries, and returns a formatted result. Supports cross-referencing headcount, saudization, turnover, salary, leave, attendance, onboarding, recruitment, payroll, and compliance data. PRIVACY: k-anonymity enforced, no individual data unless requester has HR role.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural language report request. e.g. 'Departments with high turnover and low Saudization', 'Monthly headcount trend for Engineering', 'Compare leave usage across departments this quarter'."
            },
            "format": {
                "type": "string",
                "enum": ["summary", "table", "detailed"],
                "description": "Output format preference. 'summary' = narrative with key numbers, 'table' = structured rows/columns, 'detailed' = full breakdown. Default: summary."
            },
            "export": {
                "type": "boolean",
                "description": "If true, format output as CSV-compatible text. Default false."
            }
        },
        "required": ["query"]
    }
}
```

#### Architecture: Internal Tool Orchestration

This tool does NOT execute raw SQL. It maps the natural language query to existing Ahmad tools and combines results.

**Domain-to-tool mapping:**
```python
DOMAIN_TOOL_MAP = {
    # English keywords
    "headcount": "get_headcount_summary",
    "employees": "get_headcount_summary",
    "saudization": "get_saudization_status",
    "nitaqat": "get_saudization_status",
    "turnover": "get_turnover_metrics",
    "attrition": "predict_attrition_risk",
    "salary": "get_salary_distribution",
    "budget": "get_department_budget",
    "workforce": "get_workforce_overview",
    "compliance": "get_compliance_status",
    "recruitment": "get_recruitment_analytics",
    "hiring": "get_recruitment_analytics",
    "leave": "get_leave_analytics",
    "attendance": "get_attendance_analytics",
    "onboarding": "get_onboarding_analytics",
    "payroll": "get_payroll_summary",
    "gosi": "audit_gosi_compliance",
    "policy": "get_policy_acknowledgments",
    # Arabic keywords
    "موظفين": "get_headcount_summary",
    "سعودة": "get_saudization_status",
    "نطاقات": "get_saudization_status",
    "دوران": "get_turnover_metrics",
    "تسرب": "predict_attrition_risk",
    "رواتب": "get_salary_distribution",
    "ميزانية": "get_department_budget",
    "إجازات": "get_leave_analytics",
    "حضور": "get_attendance_analytics",
    "تأهيل": "get_onboarding_analytics",
    "توظيف": "get_recruitment_analytics",
    "امتثال": "get_compliance_status",
    "تأمينات": "audit_gosi_compliance",
}
```

**Method flow:**
```python
async def _generate_custom_report(self, tool_input: dict) -> str:
    query = tool_input["query"]
    fmt = tool_input.get("format", "summary")
    export = tool_input.get("export", False)

    # Step 1: Identify domains referenced in the query
    query_lower = query.lower()
    matched_tools = set()
    for keyword, tool_name in DOMAIN_TOOL_MAP.items():
        if keyword in query_lower:
            matched_tools.add(tool_name)

    # Fallback: ambiguous query -> workforce overview
    if not matched_tools:
        matched_tools = {"get_workforce_overview"}

    # Cap at 4 tools to prevent excessive queries
    if len(matched_tools) > 4:
        matched_tools = set(list(matched_tools)[:4])

    # Step 2: Execute each matched tool sequentially (no asyncio.gather on single session)
    results = {}
    for tool_name in matched_tools:
        # Build minimal tool_input for each tool (department_id passthrough)
        sub_input = {}
        dept_id = tool_input.get("department_id")
        if dept_id:
            sub_input["department_id"] = dept_id
        result_str = await self.handle_tool_call(tool_name, sub_input)
        results[tool_name] = json.loads(result_str)

    # Step 3: Format output based on requested format
    report = {
        "title": f"Custom Report: {query[:100]}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_sources_used": list(matched_tools),
        "data": results,
    }

    if fmt == "table":
        report["columns"], report["rows"] = self._results_to_table(results)
    elif fmt == "summary":
        report["narrative"] = self._results_to_narrative(results, query)

    if export:
        report["csv_text"] = self._results_to_csv(results)

    return json.dumps(report)
```

**Important:** The `_results_to_narrative()` and `_results_to_table()` methods are lightweight formatters. The actual narrative quality comes from Claude's natural language generation in the tool-use loop -- Claude reads the tool result and formulates a response. These methods provide structural scaffolding.

#### Response Schema

**Format: `summary` (default)**
```json
{
    "title": "Custom Report: Departments with high turnover and low Saudization",
    "generated_at": "2026-03-30T12:00:00Z",
    "data_sources_used": ["get_turnover_metrics", "get_saudization_status"],
    "data": {
        "get_turnover_metrics": { "...tool result..." },
        "get_saudization_status": { "...tool result..." }
    },
    "narrative": "Based on turnover and Saudization data..."
}
```

**Format: `table`**
```json
{
    "title": "Custom Report: Compare leave usage across departments",
    "generated_at": "2026-03-30T12:00:00Z",
    "data_sources_used": ["get_leave_analytics"],
    "data": { "...tool results..." },
    "columns": ["Department", "Total Leave Days", "Unique Employees", "Avg Days/Employee"],
    "rows": [
        ["Engineering", 180, 15, 12.0],
        ["Sales", 90, 10, 9.0]
    ]
}
```

**Format: `export == true`**
```json
{
    "...standard fields...",
    "csv_text": "Department,Total Leave Days,Unique Employees,Avg Days/Employee\nEngineering,180,15,12.0\nSales,90,10,9.0\n"
}
```

#### Privacy & Security

- All privacy rules are enforced by the underlying tools. `generate_custom_report` never bypasses k-anonymity since it delegates to `handle_tool_call`.
- Queries asking for individual employee data: refuse via check for keywords like "employee", "person", "name" combined with absence of aggregation keywords.

#### Edge Cases

- **Ambiguous query ("show me everything"):** Default to `get_workforce_overview`.
- **Query references non-existent department:** Underlying tools return "Department not found".
- **Query asks for data Ahmad does not own:** Return `{"message": "I cannot generate a report on [topic]. This is handled by [agent name]."}`. Out-of-scope detection keywords: "leave request" -> Deema, "interview" -> Mohammad, "onboarding checklist" -> Waleed.
- **Query combines 4+ domains:** Execute all matched tools but add `"note": "Complex report spanning multiple domains. Results may be large."`.

#### Follow-Up Suggestions

```python
"generate_custom_report": [
    # Dynamic: based on data_sources_used, suggest related tools
    # Example: if report used turnover + saudization, suggest "Salary distribution"
],
```

---

### Updated `handle_tool_call()` Additions

Five new `elif` branches following the existing pattern in `ahmad.py`:

```python
elif tool_name == "predict_attrition_risk":
    return await self._predict_attrition_risk(tool_input)
elif tool_name == "forecast_budget":
    return await self._forecast_budget(tool_input)
elif tool_name == "audit_gosi_compliance":
    return await self._audit_gosi_compliance(tool_input)
elif tool_name == "get_policy_acknowledgments":
    return await self._get_policy_acknowledgments(tool_input)
elif tool_name == "generate_custom_report":
    return await self._generate_custom_report(tool_input)
```

### Updated `_generate_suggestions()` Additions

Add to the `suggestions_map` dict in `AhmadAgent._generate_suggestions()`:

```python
"predict_attrition_risk": [
    "معدل الدوران" if ar else "Turnover metrics",
    "توزيع الرواتب" if ar else "Salary distribution",
    "نظرة عامة على القوى العاملة" if ar else "Workforce overview",
],
"forecast_budget": [
    "ميزانية القسم" if ar else "Department budget",
    "ملخص عدد الموظفين" if ar else "Headcount summary",
    "توزيع الرواتب" if ar else "Salary distribution",
],
"audit_gosi_compliance": [
    "ملخص الرواتب" if ar else "Payroll summary",
    "وضع الامتثال" if ar else "Compliance status",
    "نظرة عامة على القوى العاملة" if ar else "Workforce overview",
],
"get_policy_acknowledgments": [
    "وضع الامتثال" if ar else "Compliance status",
    "نظرة عامة على القوى العاملة" if ar else "Workforce overview",
    "ملخص عدد الموظفين" if ar else "Headcount summary",
],
"generate_custom_report": [
    "نظرة عامة على القوى العاملة" if ar else "Workforce overview",
    "وضع السعودة" if ar else "Saudization status",
    "تحليل الحضور" if ar else "Attendance analytics",
],
```

### Updated Orchestrator Keywords

Add to Ahmad's `INTENT_KEYWORDS` in the orchestrator:

```python
# A3 keywords
"attrition", "flight risk", "retention", "predict turnover",
"budget forecast", "payroll forecast", "cost projection",
"gosi audit", "gosi compliance", "contribution check",
"policy acknowledgment", "policy compliance", "policy tracking",
"custom report", "generate report", "report on",
"مخاطر التسرب", "توقعات الميزانية", "تدقيق التأمينات",
"إقرار السياسات", "تقرير مخصص",
```

---

## Track 2: Dynamic Quick Actions

### S8-CUX-04-01: Backend -- Agent-Scoped Quick Actions

#### Endpoint Change

The existing endpoint `GET /api/v1/suggestions/quick-actions` gains a new optional query parameter:

```python
@router.get("/quick-actions", response_model=QuickActionsResponse)
async def get_quick_actions(
    db: AsyncSession = Depends(get_db),
    chat_emp: ChatEmployee = Depends(get_chat_employee),
    agent: str | None = Query(default=None, description="Agent name filter"),
) -> QuickActionsResponse:
```

#### Agent-Specific Action Definitions

New constants added to `suggestions.py` alongside the existing role-based constants:

```python
_AGENT_ACTIONS: dict[str, list[dict]] = {
    "deema": [
        dict(label_en="Leave Balance", label_ar="رصيد الإجازات",
             message="What is my leave balance?", agent="deema", icon="📅", category="self_service"),
        dict(label_en="Request Leave", label_ar="طلب إجازة",
             message="I want to request a vacation", agent="deema", icon="🏖️", category="self_service"),
        dict(label_en="My Info", label_ar="معلوماتي",
             message="Show me my employee information", agent="deema", icon="👤", category="self_service"),
        dict(label_en="Company Policy", label_ar="سياسة الشركة",
             message="What is the company leave policy?", agent="deema", icon="📋", category="self_service"),
        dict(label_en="My Payslip", label_ar="كشف الراتب",
             message="Show my latest payslip", agent="deema", icon="💰", category="self_service"),
    ],
    "ahmad": [
        dict(label_en="Workforce Overview", label_ar="نظرة عامة",
             message="Give me a workforce overview", agent="ahmad", icon="📊", category="analytics"),
        dict(label_en="Saudization Status", label_ar="وضع السعودة",
             message="Show Saudization status", agent="ahmad", icon="🇸🇦", category="analytics"),
        dict(label_en="Turnover Report", label_ar="تقرير الدوران",
             message="Show turnover metrics", agent="ahmad", icon="📈", category="analytics"),
        dict(label_en="Budget Forecast", label_ar="توقعات الميزانية",
             message="Forecast payroll budget for next 6 months", agent="ahmad", icon="💰", category="analytics"),
        dict(label_en="Attrition Risk", label_ar="مخاطر التسرب",
             message="Show attrition risk analysis", agent="ahmad", icon="⚠️", category="analytics"),
    ],
    "mohammad": [
        dict(label_en="Open Positions", label_ar="الشواغر المفتوحة",
             message="Show open positions", agent="mohammad", icon="💼", category="recruitment"),
        dict(label_en="Candidate Pipeline", label_ar="خط المرشحين",
             message="Show recruitment pipeline", agent="mohammad", icon="🔄", category="recruitment"),
        dict(label_en="Schedule Interview", label_ar="جدولة مقابلة",
             message="Schedule an interview", agent="mohammad", icon="📅", category="recruitment"),
        dict(label_en="Post New Job", label_ar="نشر وظيفة",
             message="Create a new job posting", agent="mohammad", icon="➕", category="recruitment"),
        dict(label_en="Recruitment Analytics", label_ar="تحليلات التوظيف",
             message="Show recruitment analytics", agent="mohammad", icon="📊", category="analytics"),
    ],
    "waleed": [
        dict(label_en="Onboarding Status", label_ar="حالة التأهيل",
             message="Show my onboarding progress", agent="waleed", icon="🚀", category="self_service"),
        dict(label_en="Team Overview", label_ar="نظرة على الفريق",
             message="Show my team overview", agent="waleed", icon="👥", category="team"),
        dict(label_en="Pending Approvals", label_ar="الموافقات المعلقة",
             message="Show pending leave requests for my team", agent="waleed", icon="✅", category="team"),
        dict(label_en="New Hire Checklist", label_ar="قائمة الموظف الجديد",
             message="Show onboarding checklist", agent="waleed", icon="📝", category="onboarding"),
        dict(label_en="Team Attendance", label_ar="حضور الفريق",
             message="Show team attendance", agent="waleed", icon="🕐", category="team"),
    ],
    "yara": [
        dict(label_en="Create Agent", label_ar="إنشاء وكيل",
             message="I want to create a new AI agent", agent="yara", icon="➕", category="factory"),
        dict(label_en="List Agents", label_ar="عرض الوكلاء",
             message="List all deployed agents", agent="yara", icon="📝", category="factory"),
        dict(label_en="Design Agent", label_ar="تصميم وكيل",
             message="Design an agent for my department", agent="yara", icon="🎨", category="factory"),
        dict(label_en="Agent Analytics", label_ar="تحليلات الوكلاء",
             message="Show agent usage analytics", agent="yara", icon="📊", category="analytics"),
        dict(label_en="Workforce Plan", label_ar="خطة القوى العاملة",
             message="Create a workforce plan", agent="yara", icon="📋", category="factory"),
    ],
}

# Actions restricted by role (excluded for regular employees)
_ROLE_RESTRICTED_ACTIONS = {
    "employee": {
        "mohammad": {"Post New Job", "Schedule Interview"},
        "ahmad": {"Budget Forecast", "Attrition Risk"},
        "waleed": {"Pending Approvals", "Team Overview", "Team Attendance"},
        "yara": {"Create Agent", "Design Agent", "Agent Analytics", "Workforce Plan"},
    }
}
```

#### Endpoint Logic

```python
@router.get("/quick-actions", response_model=QuickActionsResponse)
async def get_quick_actions(
    db: AsyncSession = Depends(get_db),
    chat_emp: ChatEmployee = Depends(get_chat_employee),
    agent: str | None = Query(default=None),
) -> QuickActionsResponse:
    # ... existing employee fetch and role detection ...

    if agent and agent.lower() in _AGENT_ACTIONS:
        # Agent-scoped mode
        raw_actions = _AGENT_ACTIONS[agent.lower()]
        role = _determine_role(employee, is_manager)

        # Filter out restricted actions for this role
        restricted = _ROLE_RESTRICTED_ACTIONS.get(role, {}).get(agent.lower(), set())
        actions = [a for a in raw_actions if a["label_en"] not in restricted]
    else:
        # Existing role-based behavior (no agent param)
        # ... existing logic unchanged ...

    # Cap at 6 actions
    actions = actions[:6]

    # Set display label based on language
    result_actions = []
    lang = employee.preferred_language
    for a in actions:
        result_actions.append(QuickAction(
            label=a["label_ar"] if lang == "ar" else a["label_en"],
            label_ar=a["label_ar"],
            label_en=a["label_en"],
            message=a["message"],
            agent=a["agent"],
            icon=a["icon"],
            category=a["category"],
        ))

    return QuickActionsResponse(actions=result_actions)
```

### S8-CUX-04-02: Frontend -- Pass Selected Agent

Changes to `/backend/static/chat.html`:

1. **Update `loadQuickActions()`** to pass agent parameter:
```javascript
async function loadQuickActions() {
    let url = '/api/v1/suggestions/quick-actions';
    if (selectedAgent) {
        url += '?agent=' + encodeURIComponent(selectedAgent);
    }
    // ... existing fetch logic with updated URL ...
}
```

2. **Call `loadQuickActions()` on agent switch:**
   - Inside `startNewConversation(agentName)` after `selectedAgent = agentName`
   - Inside `resumeConversation(conversationId, agentName)` after `selectedAgent` is updated

3. **Smooth transition animation:**
```css
#quickActions {
    transition: opacity 200ms ease-in-out;
}
#quickActions.switching {
    opacity: 0;
}
```

```javascript
async function loadQuickActions() {
    const container = document.getElementById('quickActions');
    container.classList.add('switching');

    // Wait for fade out
    await new Promise(r => setTimeout(r, 200));

    // ... fetch and render new actions ...

    container.classList.remove('switching');
}
```

### S8-CUX-04-03: Suggestion Chips Agent-Aware

Changes to `GET /api/v1/suggestions`:

```python
@router.get("", response_model=SuggestionsResponse)
async def get_suggestions(
    db: AsyncSession = Depends(get_db),
    chat_emp: ChatEmployee = Depends(get_chat_employee),
    language: str = Query(default=""),
    agent: str | None = Query(default=None),
) -> SuggestionsResponse:
    # ... existing logic ...

    # NEW: Agent boost (post-processing, not filtering)
    if agent:
        for s in all_suggestions:
            if s.agent_target == agent.lower():
                s.priority = max(1, s.priority - 1)  # Boost by 1 level

    # ... existing dedup + sort + cap at 6 ...
```

This is a non-breaking additive change. Existing behavior preserved when `agent` is omitted.

---

## Track 3: Knowledge Management Module

### S8-KM-01: Data Models

#### New File: `/backend/app/models/knowledge_source.py`

```python
"""Knowledge sources and chunks — flexible document storage with pgvector embeddings."""
import uuid
import enum
from datetime import datetime, timezone

from sqlalchemy import (
    String, DateTime, Integer, Text, Boolean, ForeignKey,
    Index, UniqueConstraint, Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector
from app.database import Base


class SourceType(str, enum.Enum):
    policy = "policy"
    document = "document"
    markdown = "markdown"
    custom_text = "custom_text"
    url = "url"


class EmbeddingStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    complete = "complete"
    failed = "failed"


class KnowledgeSource(Base):
    """A knowledge document that can be chunked, embedded, and assigned to agents."""
    __tablename__ = "knowledge_sources"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    title_ar: Mapped[str | None] = mapped_column(String(500), nullable=True)

    source_type: Mapped[SourceType] = mapped_column(SAEnum(SourceType), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)

    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    url: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    source_policy_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("hr_policies.id"), nullable=True
    )

    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    embedding_status: Mapped[EmbeddingStatus] = mapped_column(
        SAEnum(EmbeddingStatus), default=EmbeddingStatus.pending
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    chunks: Mapped[list["KnowledgeChunk"]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )
    assignments: Mapped[list["AgentKnowledgeAssignment"]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_knowledge_sources_tenant_type", "tenant_id", "source_type"),
        Index("ix_knowledge_sources_tenant_active", "tenant_id", "is_active"),
    )


class KnowledgeChunk(Base):
    """Chunked and embedded text from a knowledge source."""
    __tablename__ = "knowledge_chunks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_sources.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id"), nullable=False
    )  # Denormalized for query performance

    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    embedding = mapped_column(Vector(1536), nullable=True)  # OpenAI text-embedding-3-small

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    source: Mapped["KnowledgeSource"] = relationship(back_populates="chunks")

    __table_args__ = (
        Index("ix_knowledge_chunks_source", "source_id"),
        Index("ix_knowledge_chunks_tenant", "tenant_id"),
    )


class AgentKnowledgeAssignment(Base):
    """Many-to-many: which knowledge sources are assigned to which deployed agents."""
    __tablename__ = "agent_knowledge_assignments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("deployed_agents.id"), nullable=False
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_sources.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id"), nullable=False
    )

    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True
    )

    # Relationships
    source: Mapped["KnowledgeSource"] = relationship(back_populates="assignments")

    __table_args__ = (
        UniqueConstraint("agent_id", "source_id", name="uq_agent_knowledge_agent_source"),
        Index("ix_agent_knowledge_tenant_agent", "tenant_id", "agent_id"),
    )
```

#### Registration in `__init__.py`

Add to `/backend/app/models/__init__.py`:

```python
from app.models.knowledge_source import (
    KnowledgeSource, KnowledgeChunk, AgentKnowledgeAssignment,
    SourceType, EmbeddingStatus,
)
```

And add to `__all__`:
```python
"KnowledgeSource", "KnowledgeChunk", "AgentKnowledgeAssignment",
"SourceType", "EmbeddingStatus",
```

---

### S8-KM-02: Markdown Ingestion Pipeline

#### New File: `/backend/app/services/knowledge_ingestion.py`

**Interface:**
```python
async def ingest_markdown(
    db: AsyncSession,
    tenant_id: UUID,
    source_id: UUID,
    content: str,
    chunk_size: int = 800,    # tokens per chunk
    chunk_overlap: int = 100,  # overlap tokens between chunks
) -> int:
    """Ingest markdown content: chunk, embed, store. Returns chunk count."""
```

**Architecture:**

```
Raw Markdown Content
       │
       ▼
┌──────────────────┐
│ 1. Parse headings │  Extract heading hierarchy for context
│    (regex-based)  │
└──────────────────┘
       │
       ▼
┌──────────────────┐
│ 2. Split chunks   │  Token-aware splitting (tiktoken cl100k_base)
│    (respect ¶/h)  │  800 tokens target, 100 token overlap
└──────────────────┘
       │
       ▼
┌──────────────────┐
│ 3. Prepend context│  Each chunk gets heading breadcrumb prefix
│    (heading path)  │  "## Leave Policy > ### Annual Leave > [chunk]"
└──────────────────┘
       │
       ▼
┌──────────────────────┐
│ 4. Embed (batches of │  OpenAI text-embedding-3-small
│    50, same httpx    │  Reuse _get_httpx_client() from retriever.py
│    client pattern)   │
└──────────────────────┘
       │
       ▼
┌──────────────────┐
│ 5. Batch insert   │  KnowledgeChunk records with embeddings
│    chunks         │
└──────────────────┘
       │
       ▼
┌──────────────────┐
│ 6. Update source  │  chunk_count, embedding_status = 'complete'
│    metadata       │
└──────────────────┘
```

**Key design decisions:**

1. **Token counting:** Use `tiktoken` with `cl100k_base` encoding (same tokenizer as OpenAI embeddings). This is more accurate than the character-based estimation in the existing `PolicyIngestor`.

2. **Heading context:** When splitting, track the current heading hierarchy. Prepend to each chunk as breadcrumb. This improves retrieval relevance because a chunk about "Annual Leave entitlement" under "## Leave Policy" now carries that context.

3. **Chunking strategy (improved over existing PolicyIngestor):**
   - Split on heading boundaries (`#`, `##`, `###`, etc.) first
   - Within a section, split on paragraph boundaries (`\n\n`)
   - Within a paragraph, split on sentence boundaries if still over `chunk_size`
   - Overlap: last `chunk_overlap` tokens of chunk N are prepended to chunk N+1

4. **Atomicity:** Wrap the entire operation in the caller's transaction. If embedding fails, set `embedding_status = 'failed'`, delete any partial chunks (cascade), and log the error. The caller decides whether to commit or rollback.

5. **Batch embedding:** Process in batches of 50 chunks to avoid OpenAI API limits and memory issues.

6. **Bilingual chunking:** Arabic and English text in the same document are chunked together. No language splitting.

**Convenience function:**
```python
async def ingest_file(
    db: AsyncSession,
    tenant_id: UUID,
    source_id: UUID,
    file_path: str,
) -> int:
    """Read a .md file from disk and ingest."""
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    return await ingest_markdown(db, tenant_id, source_id, content)
```

---

### S8-KM-03: Scoped RAG Retriever

#### New File: `/backend/app/rag/scoped_retriever.py`

```python
class ScopedKnowledgeRetriever:
    """Retrieves relevant knowledge chunks scoped to a specific agent's assignments."""

    def __init__(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        agent_id: uuid.UUID | None = None,
    ):
        self.db = db
        self.tenant_id = tenant_id
        self.agent_id = agent_id

    async def _get_embedding(self, text_input: str) -> list[float]:
        """Get embedding vector from OpenAI API.
        Reuses the same httpx client pattern as PolicyRetriever."""
        # Identical to PolicyRetriever._get_embedding()

    async def search(self, query: str, top_k: int = 5) -> list[dict]:
        """Search knowledge chunks, scoped to agent's assigned sources.

        Returns list of:
        {
            "content": str,
            "source_title": str,
            "source_id": str,
            "source_type": str,
            "chunk_index": int,
            "similarity_score": float,
        }
        """
```

**Query plan -- agent-scoped search:**
```sql
SELECT
    kc.content,
    kc.chunk_index,
    ks.id AS source_id,
    ks.title AS source_title,
    ks.source_type,
    1 - (kc.embedding <=> :query_embedding) AS similarity_score
FROM knowledge_chunks kc
JOIN knowledge_sources ks ON kc.source_id = ks.id
JOIN agent_knowledge_assignments aka ON kc.source_id = aka.source_id
WHERE
    aka.agent_id = :agent_id
    AND kc.tenant_id = :tenant_id
    AND ks.is_active = true
ORDER BY kc.embedding <=> :query_embedding
LIMIT :top_k
```

**Query plan -- global fallback (agent_id is None or no assignments):**
```sql
SELECT
    kc.content,
    kc.chunk_index,
    ks.id AS source_id,
    ks.title AS source_title,
    ks.source_type,
    1 - (kc.embedding <=> :query_embedding) AS similarity_score
FROM knowledge_chunks kc
JOIN knowledge_sources ks ON kc.source_id = ks.id
WHERE
    kc.tenant_id = :tenant_id
    AND ks.is_active = true
ORDER BY kc.embedding <=> :query_embedding
LIMIT :top_k
```

**Fallback logic:**
```python
async def search(self, query: str, top_k: int = 5) -> list[dict]:
    query_embedding = await self._get_embedding(query)

    if self.agent_id:
        # Check if agent has any assignments
        assignment_count = await self.db.scalar(
            select(func.count(AgentKnowledgeAssignment.id))
            .where(
                AgentKnowledgeAssignment.agent_id == self.agent_id,
                AgentKnowledgeAssignment.tenant_id == self.tenant_id,
            )
        )
        if assignment_count and assignment_count > 0:
            # Use scoped query
            return await self._scoped_search(query_embedding, top_k)

    # Fall back to global search
    return await self._global_search(query_embedding, top_k)
```

**Important:** The existing `PolicyRetriever` in `/backend/app/rag/retriever.py` is NOT modified. It continues to operate on the legacy `policies`/`policy_chunks` tables. `ScopedKnowledgeRetriever` operates on the new `knowledge_sources`/`knowledge_chunks` tables. After migration (KM-06), agents can transition to using `ScopedKnowledgeRetriever`.

---

### S8-KM-04: Admin API Endpoints

#### New File: `/backend/app/api/knowledge.py`

**Router registration:** `/api/v1/knowledge`

#### Pydantic Schemas

```python
class KnowledgeSourceCreate(BaseModel):
    title: str
    title_ar: str | None = None
    source_type: SourceType
    category: str | None = None
    content_text: str | None = None  # Required for custom_text
    url: str | None = None           # Required for url type
    source_policy_id: str | None = None  # Required for policy type
    metadata_json: dict | None = None

class KnowledgeSourceUpdate(BaseModel):
    title: str | None = None
    title_ar: str | None = None
    category: str | None = None
    is_active: bool | None = None
    metadata_json: dict | None = None

class KnowledgeSourceResponse(BaseModel):
    id: str
    tenant_id: str
    title: str
    title_ar: str | None
    source_type: str
    category: str | None
    chunk_count: int
    embedding_status: str
    is_active: bool
    assignment_count: int  # Computed from AgentKnowledgeAssignment
    created_at: str
    updated_at: str

class KnowledgeSourceListResponse(BaseModel):
    items: list[KnowledgeSourceResponse]
    total: int
    page: int
    page_size: int

class AgentAssignRequest(BaseModel):
    agent_id: str

class CaptureRequest(BaseModel):
    content: str
    language: str = "en"

class CaptureResponse(BaseModel):
    suggested_title: str
    suggested_category: str
    suggested_agents: list[str]
    structured_content: str
    confidence: float
```

#### Endpoint Specifications

| Method | Path | Auth | Request | Response | Description |
|--------|------|------|---------|----------|-------------|
| POST | `/knowledge/sources` | JWT (admin) | `KnowledgeSourceCreate` | `KnowledgeSourceResponse` | Create knowledge source |
| GET | `/knowledge/sources` | JWT (admin) | `?source_type=&category=&status=&page=&page_size=` | `KnowledgeSourceListResponse` | List sources with filters |
| GET | `/knowledge/sources/{source_id}` | JWT (admin) | -- | `KnowledgeSourceResponse` | Get single source |
| PATCH | `/knowledge/sources/{source_id}` | JWT (admin) | `KnowledgeSourceUpdate` | `KnowledgeSourceResponse` | Update source metadata |
| DELETE | `/knowledge/sources/{source_id}` | JWT (admin) | -- | `{"status": "deactivated"}` | Soft delete (is_active=False) |
| POST | `/knowledge/sources/{source_id}/upload` | JWT (admin) | `multipart/form-data` (file) | `{"status": "processing", "source_id": "..."}` | Upload .md file, trigger ingestion |
| POST | `/knowledge/sources/{source_id}/ingest-text` | JWT (admin) | `{"content": "..."}` | `{"status": "processing", "source_id": "..."}` | Ingest raw text |
| POST | `/knowledge/sources/{source_id}/assign` | JWT (admin) | `AgentAssignRequest` | `{"status": "assigned"}` | Assign source to agent |
| DELETE | `/knowledge/sources/{source_id}/assign/{agent_id}` | JWT (admin) | -- | `{"status": "unassigned"}` | Remove assignment |
| GET | `/knowledge/agents/{agent_id}/sources` | JWT (admin) | `?page=&page_size=` | `KnowledgeSourceListResponse` | List sources for agent |
| POST | `/knowledge/capture` | JWT (admin) | `CaptureRequest` | `CaptureResponse` | AI-assisted knowledge structuring |

**Upload endpoint details:**
- Validates file extension: `.md` only (future: `.txt`, `.pdf`, `.docx`)
- Max file size: 5 MB
- Returns 202 Accepted immediately
- Triggers `ingest_markdown()` in the background (using `asyncio.create_task` or a simple background task pattern)
- Client polls `GET /knowledge/sources/{source_id}` to check `embedding_status`

**AI Capture endpoint (`POST /knowledge/capture`):**

Uses Claude to structure raw input into a knowledge entry:

```python
CAPTURE_SYSTEM_PROMPT = """You are a knowledge structuring assistant for an HR platform.
Given raw text input (possibly from voice transcription), extract and structure it into:
1. A clear, concise title (English)
2. A category (one of: leave, attendance, conduct, compensation, benefits, safety, general, onboarding, recruitment, compliance)
3. Suggested agents who should have access (from: deema, waleed, mohammad, ahmad, yara)
4. A clean, structured version of the content

Respond in JSON format:
{
    "suggested_title": "...",
    "suggested_category": "...",
    "suggested_agents": ["..."],
    "structured_content": "...",
    "confidence": 0.0-1.0
}

Rules:
- If the content is about leave/absence/vacation -> suggest deema
- If about recruitment/hiring/candidates -> suggest mohammad
- If about onboarding/team/approvals -> suggest waleed
- If about analytics/compliance/budgets -> suggest ahmad
- If about agents/automation -> suggest yara
- Default to deema for general HR content
- Confidence is your certainty about the categorization (0.5 = unsure, 0.9 = very confident)
"""
```

**Tenant isolation:** All endpoints extract `tenant_id` from the JWT via `get_chat_employee` (or admin auth dependency). All queries filter by `tenant_id`.

---

### S8-KM-05: Knowledge Management UI

#### New File: `/backend/static/knowledge.html`

**Page structure:**

```
┌─────────────────────────────────────────────────────────────────┐
│  Krew Platform  │  💬 Chat  │  👥 Teams  │  📚 Knowledge       │
├─────────────┬───┴───────────────────────────────────────────────┤
│             │  ┌─────────────────────────────────────────────┐  │
│  Sidebar    │  │  AI-Assisted Knowledge Capture              │  │
│             │  │  ┌─────────────────────────────────────┐    │  │
│  Recent     │  │  │  Type or speak to add knowledge...  │    │  │
│  ─────      │  │  │                              🎙️ 📎  │    │  │
│  entry 1    │  │  └─────────────────────────────────────┘    │  │
│  entry 2    │  │                              [Submit]       │  │
│  entry 3    │  └─────────────────────────────────────────────┘  │
│             │                                                    │
│  Categories │  ┌─────────────────────────────────────────────┐  │
│  ─────      │  │  Structured Preview (after AI processing)   │  │
│  leave      │  │  📋 Engineering Probation Period             │  │
│  conduct    │  │  ├ Category: HR Policy                       │  │
│  safety     │  │  ├ Scope: Engineering dept, new hires        │  │
│             │  │  ├ Assign to: [Deema] [Waleed]               │  │
│  Agents     │  │  └ Content: [editable text]                  │  │
│  ─────      │  │                    [Confirm] [Edit] [Cancel] │  │
│  deema      │  └─────────────────────────────────────────────┘  │
│  ahmad      │                                                    │
│  mohammad   │  ┌─────────────────────────────────────────────┐  │
│  waleed     │  │  Knowledge Library                           │  │
│  yara       │  │  🔍 Search...  [Category ▼] [Agent ▼]       │  │
│             │  │  ┌───────────────────────────────────────┐   │  │
│             │  │  │ 📄 Annual Leave Policy  [leave]       │   │  │
│             │  │  │    Assigned: Deema, Waleed  │ 3/15/26 │   │  │
│             │  │  ├───────────────────────────────────────┤   │  │
│             │  │  │ 🎙️ Eng Probation  [hr_policy]         │   │  │
│             │  │  │    Assigned: Deema, Waleed  │ 3/30/26 │   │  │
│             │  │  └───────────────────────────────────────┘   │  │
│             │  └─────────────────────────────────────────────┘  │
└─────────────┴────────────────────────────────────────────────────┘
```

**Voice Input Architecture (MVP):**
```javascript
// Browser-native Web Speech API (Chrome/Edge only for MVP)
function startVoiceCapture() {
    const recognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
    recognition.lang = selectedLanguage === 'ar' ? 'ar-SA' : 'en-US';
    recognition.continuous = false;
    recognition.interimResults = true;

    recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        document.getElementById('knowledgeInput').value = transcript;
    };

    recognition.onerror = (event) => {
        showError('Voice recognition failed. Please type your input.');
    };

    recognition.start();
    // Show pulsing mic icon, timer
}
```

**Design system:** Uses the same CSS variables, Inter font, light/dark mode, and RTL support as `chat.html`. Authentication uses the same `authToken` pattern.

**Navigation integration:** The main sidebar in `chat.html` gains a navigation link:
```html
<a href="/knowledge.html" class="nav-link">📚 Knowledge</a>
```

---

### S8-KM-06: Policy Migration Script

#### New File: `/backend/scripts/migrate_policies_to_knowledge.py`

**Architecture:**
```python
async def migrate_policies():
    """One-time migration: copy policies + policy_chunks -> knowledge_sources + knowledge_chunks."""
    async with async_session() as db:
        # For each active Policy:
        policies = await db.execute(
            select(Policy).where(Policy.is_active == True)
        )
        for policy in policies.scalars():
            # Idempotency check: skip if KnowledgeSource already exists
            existing = await db.execute(
                select(KnowledgeSource).where(
                    KnowledgeSource.tenant_id == policy.tenant_id,
                    KnowledgeSource.title == policy.title,
                    KnowledgeSource.source_type == SourceType.policy,
                )
            )
            if existing.scalar_one_or_none():
                logger.info(f"Skipping already migrated: {policy.title}")
                continue

            # Create KnowledgeSource
            ks = KnowledgeSource(
                tenant_id=policy.tenant_id,
                title=policy.title,
                source_type=SourceType.policy,
                category=policy.category,
                embedding_status=EmbeddingStatus.complete,
            )
            db.add(ks)
            await db.flush()  # Get ks.id

            # Copy chunks
            chunks = await db.execute(
                select(PolicyChunk).where(PolicyChunk.policy_id == policy.id)
            )
            chunk_count = 0
            for chunk in chunks.scalars():
                kc = KnowledgeChunk(
                    source_id=ks.id,
                    tenant_id=policy.tenant_id,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    token_count=chunk.token_count,
                    embedding=chunk.embedding,
                )
                db.add(kc)
                chunk_count += 1

            ks.chunk_count = chunk_count
            logger.info(f"Migrated policy '{policy.title}' with {chunk_count} chunks")

        await db.commit()
```

**Idempotency:** Checks for existing KnowledgeSource by `(tenant_id, title, source_type)`. Running twice is safe.

**Original tables:** NOT modified or deleted. They continue to work for the existing `PolicyRetriever`.

---

## Track 4: Ahmad English-Only Responses

### S8-AHM-LANG-01: System Prompt Changes

#### Changes to `ahmad.py`

**1. Update `personality` field:**

Current:
```python
personality = (
    "Strategic, data-driven, and executive-oriented. You lead with headline numbers "
    "and tie every metric to business impact. You present insights clearly, using "
    "structured summaries with key takeaways. You understand Saudi labor law, Nitaqat, "
    "and GOSI deeply. You are bilingual and switch naturally between Arabic and English."
)
```

Updated:
```python
personality = (
    "Strategic, data-driven, and executive-oriented. You lead with headline numbers "
    "and tie every metric to business impact. You present insights clearly, using "
    "structured summaries with key takeaways. You understand Saudi labor law, Nitaqat, "
    "and GOSI deeply. You always respond in English for consistency in executive reporting. "
    "You understand Arabic queries fluently."
)
```

**2. Update `_get_scope_rules()` -- add language instruction at the top:**

Add as the first line of the returned string:
```python
"LANGUAGE RULE: You MUST always respond in English, regardless of the language the user writes in. "
"If the user writes in Arabic, understand their request but respond entirely in English. "
"Do not mix Arabic and English in your responses. "
"Exception: When quoting Arabic terms of art (e.g., نطاقات for Nitaqat, التأمينات الاجتماعية for GOSI), "
"include the Arabic term in parentheses after the English term for clarity.\n\n"
```

**3. Update the Arabic glossary note:**

Add to the end of the Arabic glossary section in `_get_scope_rules()`:
```python
"\nNote: Use these Arabic terms to understand Arabic queries. Always respond in English.\n"
```

**4. `_generate_suggestions()` is NOT changed.** It continues to return both Arabic and English suggestion text based on the `language` parameter. The UI uses these strings, not Ahmad's response language. This is correct behavior -- suggestion chips should match the user's UI language preference.

#### Where Language Enforcement Happens

The enforcement is entirely in the system prompt, which is the correct approach for an LLM-based agent. There is no code-level language detection or translation. The `_get_scope_rules()` output is injected into Claude's system prompt, and Claude follows the instruction.

This is a prompt-only change. No data model, API, or frontend changes required.

---

## Database Migration Notes

### Track 1 (Ahmad A3): NO MIGRATION NEEDED

Ahmad A3 tools are pure readers of existing tables. All required columns exist:

| Table | Fields Used by A3 | Status |
|-------|-------------------|--------|
| `employees` | id, tenant_id, department_id, hire_date, salary_sar, is_saudi, status, updated_at, manager_id, probation_end_date | All exist |
| `departments` | id, tenant_id, name, name_ar | All exist |
| `leave_requests` | id, employee_id, leave_type, business_days, status, start_date | All exist |
| `attendance_records` | id, tenant_id, employee_id, date, status | All exist |
| `payslips` | id, tenant_id, employee_id, year, month, basic_salary, gosi_employee | All exist |
| `hr_policies` | id, tenant_id, title, title_ar, category, status, effective_date | All exist |
| `policy_acknowledgments` | id, tenant_id, policy_id, employee_id, acknowledged_at | All exist |

**Note on Payslip model:** The stories reference `Payslip.gosi_deduction` but the actual column is `Payslip.gosi_employee`. There is no `gosi_employer` column. The A3-03 tool estimates employer GOSI from `basic_salary * rate`. No migration needed.

### Track 2 (Quick Actions): NO MIGRATION NEEDED

Pure configuration change in `suggestions.py` and frontend.

### Track 3 (Knowledge Management): NEW TABLES REQUIRED

**Alembic migration creates 3 new tables:**

```sql
-- Table 1: knowledge_sources
CREATE TABLE knowledge_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    title VARCHAR(500) NOT NULL,
    title_ar VARCHAR(500),
    source_type VARCHAR(20) NOT NULL,  -- policy, document, markdown, custom_text, url
    category VARCHAR(100),
    content_text TEXT,
    file_path VARCHAR(1000),
    url VARCHAR(2000),
    source_policy_id UUID REFERENCES hr_policies(id),
    chunk_count INTEGER DEFAULT 0,
    embedding_status VARCHAR(20) DEFAULT 'pending',  -- pending, processing, complete, failed
    is_active BOOLEAN DEFAULT TRUE,
    metadata_json JSONB,
    created_by UUID REFERENCES employees(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ix_knowledge_sources_tenant_type ON knowledge_sources(tenant_id, source_type);
CREATE INDEX ix_knowledge_sources_tenant_active ON knowledge_sources(tenant_id, is_active);

-- Table 2: knowledge_chunks
CREATE TABLE knowledge_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID NOT NULL REFERENCES knowledge_sources(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    token_count INTEGER DEFAULT 0,
    embedding vector(1536),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ix_knowledge_chunks_source ON knowledge_chunks(source_id);
CREATE INDEX ix_knowledge_chunks_tenant ON knowledge_chunks(tenant_id);

-- Table 3: agent_knowledge_assignments
CREATE TABLE agent_knowledge_assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID NOT NULL REFERENCES deployed_agents(id),
    source_id UUID NOT NULL REFERENCES knowledge_sources(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    assigned_at TIMESTAMPTZ DEFAULT NOW(),
    assigned_by UUID REFERENCES employees(id),
    CONSTRAINT uq_agent_knowledge_agent_source UNIQUE (agent_id, source_id)
);

CREATE INDEX ix_agent_knowledge_tenant_agent ON agent_knowledge_assignments(tenant_id, agent_id);
```

### Track 4 (Ahmad English-Only): NO MIGRATION NEEDED

Prompt-only change.

### Recommended Performance Indexes (Optional)

```sql
-- A3-01: Attrition risk queries sick leave by date range
CREATE INDEX IF NOT EXISTS ix_leave_requests_type_status_date
ON leave_requests (leave_type, status, start_date);

-- A3-03: GOSI audit queries payslips by tenant + year + month
-- Already covered by existing uq_payslip_employee_year_month
-- But add tenant-scoped index:
CREATE INDEX IF NOT EXISTS ix_payslips_tenant_year_month
ON payslips (tenant_id, year, month);

-- A3-04: Policy acknowledgment joins
CREATE INDEX IF NOT EXISTS ix_policy_acks_policy_id
ON policy_acknowledgments (policy_id);
```

---


## Track 5: Unified Chat with @Mention Routing

Replace the "one agent at a time" sidebar model with a **unified chat thread** where users @mention agents inline. Like Slack — one conversation, multiple AI participants. Each agent responds only when explicitly called (via @mention) or auto-routed (via keywords), and the user controls routing explicitly.

**Stories covered:** S8-UC-01 (parser), S8-UC-02 (orchestrator), S8-UC-03 (UI), S8-UC-04 (per-agent context), S8-UC-05 (access privileges)

---

### 5.1 @Mention Parser — Full Specification

**File:** `backend/app/utils/mention_parser.py` (NEW)

#### 5.1.1 Agent Name Registry

The registry maps every valid mention string (English, Arabic, aliases) to the canonical agent name used internally by the orchestrator (the keys in `orchestrator.py` line 26: `AGENTS = {"deema", "waleed", "mohammad", "yara", "ahmad"}`).

```python
"""@mention parser — extracts agent mentions from chat messages."""
import re
from typing import Optional

# Canonical agent name → all recognized mention strings
# Keys must match orchestrator.AGENTS keys exactly.
# Arabic names must match BaseAgent.name_ar for each agent.
AGENT_ALIASES: dict[str, list[str]] = {
    "deema":    ["deema", "ديمة", "dima", "ديما"],
    "waleed":   ["waleed", "وليد", "walid"],
    "mohammad": ["mohammad", "محمد", "mohammed", "mohamad"],
    "yara":     ["yara", "يارا", "sara", "sarah", "سارة"],
    "ahmad":    ["ahmad", "أحمد", "ahmed", "norah", "نورة", "نوره"],
}

# Inverted lookup: mention_string → canonical_name (built once at import time)
MENTION_TO_AGENT: dict[str, str] = {}
for _canonical, _aliases in AGENT_ALIASES.items():
    for _alias in _aliases:
        MENTION_TO_AGENT[_alias.lower()] = _canonical

# For dynamic/deployed agents, the format is @dept:{uuid} which is handled separately.
```

**Design rationale for aliases:**
- `sarah`/`سارة` maps to `yara` because Yara absorbed Sarah's role (per `project_sprint_backlog.md`).
- `norah`/`نورة` maps to `ahmad` because Ahmad absorbed Norah (see `orchestrator.py` lines 153-157 `SWITCH_PHRASES`).
- Transliteration variants (`walid`, `mohammed`, `mohamad`, `ahmed`, `dima`) catch common English spellings.
- Arabic variants without diacritics are handled by default since the registry stores undiacritized forms. Arabic diacritics (tashkeel) are stripped before lookup — see regex below.

#### 5.1.2 Regex Pattern

```python
# Unicode property ranges:
#   \w          — ASCII word chars (a-z, A-Z, 0-9, _)
#   \u0600-\u06FF — Arabic block (covers all Arabic letters + common diacritics)
#   \u0750-\u077F — Arabic Supplement
#   \u08A0-\u08FF — Arabic Extended-A
#   \uFE70-\uFEFF — Arabic Presentation Forms-B
#
# The colon and hyphen after @ allow matching dept:{uuid} format.
# The pattern requires @ preceded by start-of-string or whitespace to avoid matching
# email addresses (e.g., user@deema.com).

_MENTION_RE = re.compile(
    r'(?:^|(?<=\s))'           # Must be at start or after whitespace
    r'@'                        # The @ trigger
    r'('                        # Begin capture group
    r'[\w\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFE70-\uFEFF]+'  # Agent name
    r'(?::[\w-]+)?'             # Optional :suffix for dept:{uuid}
    r')',                        # End capture group
    re.UNICODE | re.IGNORECASE
)

# Arabic diacritics (tashkeel) to strip before lookup
_DIACRITICS_RE = re.compile(r'[\u064B-\u065F\u0670]')
```

#### 5.1.3 Core Function

```python
def parse_mention(message: str) -> tuple[str | None, str]:
    """
    Extract the first @agent mention from a chat message.

    Returns:
        (canonical_agent_name, cleaned_message) if a valid @mention is found.
        (None, original_message) if no @mention or unrecognized agent.

    The cleaned_message has the @mention stripped and whitespace normalized.
    For unrecognized @mentions, returns (None, original_message) — the caller
    (orchestrator) is responsible for producing the error message, since it
    has access to the employee's available agents list.

    Examples:
        >>> parse_mention("@deema check my leave")
        ("deema", "check my leave")
        >>> parse_mention("@ديمة كم رصيد إجازاتي؟")
        ("deema", "كم رصيد إجازاتي؟")
        >>> parse_mention("hey @mohammad schedule interview")
        ("mohammad", "hey schedule interview")
        >>> parse_mention("@AHMAD show analytics")
        ("ahmad", "show analytics")
        >>> parse_mention("no mention here")
        (None, "no mention here")
        >>> parse_mention("@unknown do something")
        (None, "@unknown do something")
        >>> parse_mention("@dept:550e8400-e29b-41d4-a716-446655440000 help")
        ("dept:550e8400-e29b-41d4-a716-446655440000", "help")
    """
    match = _MENTION_RE.search(message)
    if not match:
        return None, message

    raw_name = match.group(1)

    # Handle dept:{uuid} format — pass through as-is (validated by orchestrator)
    if raw_name.lower().startswith("dept:"):
        cleaned = (message[:match.start()] + message[match.end():]).strip()
        cleaned = re.sub(r'\s{2,}', ' ', cleaned)
        return raw_name.lower(), cleaned

    # Strip Arabic diacritics and lowercase for lookup
    normalized = _DIACRITICS_RE.sub('', raw_name).lower()

    agent_name = MENTION_TO_AGENT.get(normalized)
    if not agent_name:
        # Unrecognized mention — return None so orchestrator can produce error
        return None, message

    # Strip the @mention from the message
    cleaned = (message[:match.start()] + message[match.end():]).strip()
    cleaned = re.sub(r'\s{2,}', ' ', cleaned)  # Collapse double spaces

    return agent_name, cleaned


def get_mentioned_raw(message: str) -> str | None:
    """Return the raw @mention string (e.g., '@deema', '@أحمد') for error messages.

    Returns None if no @mention found.
    """
    match = _MENTION_RE.search(message)
    return f"@{match.group(1)}" if match else None
```

#### 5.1.4 Edge Cases

| Scenario | Input | Output | Notes |
|----------|-------|--------|-------|
| Start of message | `@deema my leave` | `("deema", "my leave")` | Common case |
| Middle of message | `hey @deema balance?` | `("deema", "hey balance?")` | Spaces collapsed |
| End of message | `check leave @deema` | `("deema", "check leave")` | Trailing stripped |
| Arabic mention | `@ديمة كم رصيدي` | `("deema", "كم رصيدي")` | Arabic lookup |
| Arabic with tashkeel | `@أَحْمَد analytics` | `("ahmad", "analytics")` | Diacritics stripped |
| Case insensitive | `@DEEMA @Ahmad both` | `("deema", "@Ahmad both")` | First wins, second left in message |
| Multiple mentions | `@deema then @ahmad` | `("deema", "then @ahmad")` | First mention wins |
| Unknown agent | `@bob help me` | `(None, "@bob help me")` | Unchanged, orchestrator handles |
| Email-like | `send to user@deema.com` | `(None, "send to user@deema.com")` | No match — requires preceding space/start |
| Deployed agent | `@dept:abc-123 help` | `("dept:abc-123", "help")` | Passed through for orchestrator to validate |
| Empty after @ | `@ hello` | `(None, "@ hello")` | Regex requires 1+ chars after @ |
| No message after mention | `@deema` | `("deema", "")` | Valid — agent gets empty message |
| Alias | `@ahmed report` | `("ahmad", "report")` | English alias lookup |

#### 5.1.5 Test Cases

```python
# File: backend/tests/test_mention_parser.py

import pytest
from app.utils.mention_parser import parse_mention, get_mentioned_raw

class TestParseMention:
    """UC-01: @mention parser unit tests."""

    # ── Happy path ──
    def test_english_start(self):
        assert parse_mention("@deema check leave") == ("deema", "check leave")

    def test_english_middle(self):
        assert parse_mention("hey @mohammad schedule interview") == ("mohammad", "hey schedule interview")

    def test_english_end(self):
        assert parse_mention("check leave @waleed") == ("waleed", "check leave")

    def test_case_insensitive(self):
        assert parse_mention("@DEEMA help")[0] == "deema"
        assert parse_mention("@Ahmad report")[0] == "ahmad"

    # ── Arabic ──
    def test_arabic_name(self):
        assert parse_mention("@ديمة كم رصيد إجازاتي؟") == ("deema", "كم رصيد إجازاتي؟")

    def test_arabic_with_diacritics(self):
        assert parse_mention("@أَحْمَد analytics") == ("ahmad", "analytics")

    # ── Aliases ──
    def test_alias_ahmed(self):
        assert parse_mention("@ahmed report")[0] == "ahmad"

    def test_alias_sarah(self):
        assert parse_mention("@sarah build agent")[0] == "yara"

    def test_alias_norah(self):
        assert parse_mention("@نورة تقرير")[0] == "ahmad"

    # ── Edge cases ──
    def test_no_mention(self):
        assert parse_mention("just a normal message") == (None, "just a normal message")

    def test_unknown_agent(self):
        assert parse_mention("@unknown help") == (None, "@unknown help")

    def test_email_not_matched(self):
        assert parse_mention("email user@deema.com")[0] is None

    def test_multiple_mentions_first_wins(self):
        name, cleaned = parse_mention("@deema then ask @ahmad")
        assert name == "deema"
        assert "@ahmad" in cleaned

    def test_empty_after_mention(self):
        assert parse_mention("@deema") == ("deema", "")

    def test_whitespace_collapse(self):
        _, cleaned = parse_mention("hello  @deema  world")
        assert "  " not in cleaned

    def test_dept_agent(self):
        name, cleaned = parse_mention("@dept:550e8400 help with IT")
        assert name == "dept:550e8400"
        assert cleaned == "help with IT"

    # ── get_mentioned_raw ──
    def test_raw_mention_found(self):
        assert get_mentioned_raw("@deema help") == "@deema"

    def test_raw_mention_arabic(self):
        assert get_mentioned_raw("@أحمد report") == "@أحمد"

    def test_raw_mention_none(self):
        assert get_mentioned_raw("no mention") is None
```

---

### 5.2 Orchestrator Changes — Detailed Routing Flow

**File:** `backend/app/agents/orchestrator.py` (MODIFY)

#### 5.2.1 Current Routing Logic (Reference)

The current `route()` method (lines 160-193) has this flow:
1. Check `SWITCH_PHRASES` for explicit agent switch requests (lines 169-173)
2. If `current_agent` is set and valid, stay sticky (lines 176-178)
3. No active agent: score `INTENT_KEYWORDS` (lines 184-190)
4. Default to `"deema"` (line 193)

The current `handle_message()` (lines 195-235) passes `current_agent` from the conversation's stored `agent_name`.

#### 5.2.2 New Routing Decision Tree

```
handle_message(message, ..., current_agent)
│
├─ 1. parse_mention(message) → (mentioned_agent, cleaned_message)
│   │
│   ├─ mentioned_agent is not None:
│   │   │
│   │   ├─ mentioned_agent is recognized super agent (in AGENTS dict)?
│   │   │   ├─ YES → check_agent_access(employee, mentioned_agent)
│   │   │   │   ├─ ALLOWED → route to mentioned_agent, use cleaned_message
│   │   │   │   │            Store mentioned_agent as conversation.last_mentioned_agent
│   │   │   │   └─ DENIED  → return access denied error message
│   │   │   │                "You don't have access to @{name}. Available: @deema, @waleed"
│   │   │   └─ NO (but starts with "dept:") → get_dynamic_agent()
│   │   │       ├─ FOUND + ACTIVE → check_agent_access() → route or deny
│   │   │       └─ NOT FOUND → return error: "Agent not found or inactive"
│   │   │
│   │   └─ mentioned_agent is None (unrecognized @mention detected by get_mentioned_raw):
│   │       └─ Return error message listing available agents
│   │           "I don't recognize @{raw}. Available agents: @deema, @waleed, ..."
│   │
│   └─ mentioned_agent is None AND no @mention in message:
│       │
│       ├─ 2. Check last_mentioned_agent on conversation (sticky @mention)
│       │   ├─ SET → route to last_mentioned_agent (sticky), use original message
│       │   └─ NOT SET → fall through to step 3
│       │
│       ├─ 3. Check SWITCH_PHRASES (existing, lines 148-158)
│       │   ├─ MATCH → check_agent_access() → route or fallback to deema
│       │   └─ NO MATCH → fall through
│       │
│       ├─ 4. current_agent is set and valid (existing sticky, lines 176-178)
│       │   └─ Route to current_agent
│       │
│       ├─ 5. Keyword scoring (existing, lines 184-190)
│       │   ├─ MATCH → check_agent_access()
│       │   │   ├─ ALLOWED → route to matched agent
│       │   │   └─ DENIED → route to deema with soft message
│       │   └─ NO MATCH → fall through
│       │
│       └─ 6. Default → "deema"
```

**Key principle:** @mention routing has the HIGHEST priority — it overrides sticky routing, keyword routing, and switch phrases. This gives the user explicit control.

#### 5.2.3 Code Changes to orchestrator.py

```python
# ── NEW IMPORTS (add at top of orchestrator.py, after line 7) ──
from app.utils.mention_parser import parse_mention, get_mentioned_raw
from app.utils.agent_access import check_agent_access, get_accessible_agents

# ── NEW: Add last_mentioned_agent tracking ──
# In AgentOrchestrator.__init__ (after line 118):
    self.last_mentioned_agent: str | None = None

# ── MODIFIED: route() method — replace lines 160-193 entirely ──

async def route(
    self,
    message: str,
    current_agent: str | None = None,
    employee_id: UUID | None = None,
    employee_role: str | None = None,
    employee_dept_id: UUID | None = None,
    last_mentioned_agent: str | None = None,
) -> tuple[str, str, str | None]:
    """Determine which agent should handle this message.

    Returns:
        (agent_name, cleaned_message, error_message)
        - error_message is None on success, or a user-facing string on failure.
        - When error_message is set, agent_name is "system" and the orchestrator
          should return the error directly instead of calling an agent.

    Priority:
        1. @mention (explicit) — highest priority
        2. last_mentioned_agent (sticky @mention per conversation)
        3. SWITCH_PHRASES (explicit agent switch, existing)
        4. current_agent (sticky conversation agent, existing)
        5. INTENT_KEYWORDS (keyword scoring, existing)
        6. Default to "deema"
    """
    message_lower = message.lower()

    # ── 1. @mention routing (NEW — highest priority) ──
    mentioned_agent, cleaned_message = parse_mention(message)

    if mentioned_agent is not None:
        # Valid recognized agent
        if mentioned_agent in AGENTS or mentioned_agent.startswith("dept:"):
            # Access check
            if employee_id and employee_role is not None:
                has_access = await check_agent_access(
                    self.db, self.tenant_id, employee_id,
                    employee_role, employee_dept_id, mentioned_agent,
                )
                if not has_access:
                    accessible = await get_accessible_agents(
                        self.db, self.tenant_id, employee_id,
                        employee_role, employee_dept_id,
                    )
                    agent_list = ", ".join(f"@{a}" for a in accessible)
                    raw = get_mentioned_raw(message) or f"@{mentioned_agent}"
                    error = (
                        f"You don't have access to {raw}. "
                        f"Available agents: {agent_list}\n\n"
                        f"ليس لديك صلاحية الوصول إلى {raw}. "
                        f"الوكلاء المتاحون: {agent_list}"
                    )
                    return "system", message, error
            return mentioned_agent, cleaned_message, None
        else:
            # Unrecognized — should not happen (parse_mention returns None for unknown)
            pass

    # Check if user typed an unrecognized @mention
    raw_mention = get_mentioned_raw(message)
    if raw_mention is not None and mentioned_agent is None:
        # Unrecognized @mention — return helpful error
        accessible = await get_accessible_agents(
            self.db, self.tenant_id, employee_id,
            employee_role, employee_dept_id,
        ) if employee_id else list(AGENTS.keys())
        agent_list = ", ".join(f"@{a}" for a in accessible)
        error = (
            f"I don't recognize {raw_mention}. "
            f"Available agents: {agent_list}\n\n"
            f"لا أعرف {raw_mention}. "
            f"الوكلاء المتاحون: {agent_list}"
        )
        return "system", message, error

    # ── 2. Sticky @mention routing (NEW) ──
    if last_mentioned_agent and (last_mentioned_agent in AGENTS or last_mentioned_agent.startswith("dept:")):
        return last_mentioned_agent, message, None

    # ── 3. Explicit switch phrases (EXISTING — lines 148-158) ──
    for agent_name, phrases in self.SWITCH_PHRASES.items():
        if any(phrase in message_lower for phrase in phrases):
            if agent_name != current_agent:
                # Access check for switch phrase
                if employee_id and employee_role is not None:
                    has_access = await check_agent_access(
                        self.db, self.tenant_id, employee_id,
                        employee_role, employee_dept_id, agent_name,
                    )
                    if not has_access:
                        return "deema", message, None  # Silent fallback
                return agent_name, message, None

    # ── 4. Sticky current agent (EXISTING — lines 176-178) ──
    if current_agent and (current_agent in AGENTS or current_agent.startswith("dept:")):
        return current_agent, message, None

    # ── 5. Keyword scoring (EXISTING — lines 184-193) ──
    scores: dict[str, int] = {}
    for agent_name, keywords in INTENT_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in message_lower)
        if score > 0:
            scores[agent_name] = score

    if scores:
        best = max(scores, key=scores.get)
        # Access check for keyword-routed agent
        if employee_id and employee_role is not None:
            has_access = await check_agent_access(
                self.db, self.tenant_id, employee_id,
                employee_role, employee_dept_id, best,
            )
            if not has_access:
                return "deema", message, None  # Silent fallback to Deema
        return best, message, None

    # ── 6. Default ──
    return "deema", message, None
```

#### 5.2.4 handle_message Changes

The `handle_message()` method (currently lines 195-235) needs these modifications:

```python
async def handle_message(
    self,
    message: str,
    employee_name: str,
    employee_id: str = "",
    conversation_history: list[dict] | None = None,
    current_agent: str | None = None,
    language: str = "ar",
    conversation_id: "UUID | None" = None,
    # ── NEW parameters ──
    last_mentioned_agent: str | None = None,
    employee_role: str | None = None,
    employee_dept_id: "UUID | None" = None,
) -> tuple[str, str, str | None]:
    """Route and handle a message.

    Returns:
        (agent_name, response, last_mentioned_agent)
        - last_mentioned_agent: updated value to store on conversation.
          Set when user uses @mention, preserved when sticky, cleared on explicit switch.
    """
    if conversation_history is None:
        conversation_history = []

    emp_uuid = UUID(employee_id) if employee_id else None

    agent_name, cleaned_message, error = await self.route(
        message,
        current_agent=current_agent,
        employee_id=emp_uuid,
        employee_role=employee_role,
        employee_dept_id=employee_dept_id,
        last_mentioned_agent=last_mentioned_agent,
    )

    # If routing produced an error (access denied / unknown agent), return it directly
    if error is not None:
        return "system", error, last_mentioned_agent

    # Track @mention stickiness
    mentioned_agent, _ = parse_mention(message)
    new_last_mentioned = last_mentioned_agent
    if mentioned_agent is not None:
        # User explicitly @mentioned — update sticky
        new_last_mentioned = agent_name
    # If user used a switch phrase, clear the @mention sticky
    for switch_agent, phrases in self.SWITCH_PHRASES.items():
        if any(phrase in message.lower() for phrase in phrases):
            new_last_mentioned = None
            break

    # Load agent — dynamic (dept:) or super agent
    dynamic = await self.get_dynamic_agent(agent_name)
    agent = dynamic if dynamic else self.get_agent(agent_name)

    # Handoff detection
    if current_agent and current_agent not in AGENTS and not current_agent.startswith("dept:"):
        current_agent = None
    is_handoff = current_agent is not None and current_agent != agent_name
    is_first_message = current_agent is None and not conversation_history
    agent._handoff_from = current_agent if is_handoff else None
    agent._is_first_message = is_first_message

    # Use cleaned message (without @mention) for the agent
    conversation_history.append({"role": "user", "content": cleaned_message})
    response = await agent.respond(
        conversation_history,
        employee_name,
        employee_id,
        language,
        conversation_id=conversation_id,
    )

    self.last_agent = agent

    return agent_name, response, new_last_mentioned
```

#### 5.2.5 Sticky @Mention: Storage and Reset Rules

**Storage:** Add `last_mentioned_agent` column to the `conversations` table (see section 5.7 Migration).

**Rules:**
| Event | Effect on `last_mentioned_agent` |
|-------|----------------------------------|
| User sends `@deema check leave` | Set to `"deema"` |
| User sends follow-up without @mention | Preserved (sticky to `"deema"`) |
| User sends `@ahmad analytics` | Updated to `"ahmad"` |
| User sends switch phrase `كلم وليد` | Cleared to `None` (switch phrases bypass @mention sticky) |
| New conversation started | `None` (fresh conversation has no sticky) |
| Conversation resolved and reopened | Preserved from last state |

**Why separate from `conversation.agent_name`:** The existing `agent_name` column (line 24 of `conversation.py`) tracks the LAST agent that responded. The new `last_mentioned_agent` specifically tracks the last *@mentioned* agent, which is a different concept. An auto-routed keyword match should not update the @mention sticky.

---

### 5.3 Agent Access Privileges — Complete Data Model

**File:** `backend/app/models/agent_access_rule.py` (NEW)

#### 5.3.1 SQLAlchemy Model

```python
"""Agent access rules — controls which employees can interact with which agents."""
import uuid
import enum
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Boolean, ForeignKey, Index
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AccessType(str, enum.Enum):
    """How access is determined for this agent."""
    all = "all"                     # Every employee in the tenant
    role_based = "role_based"       # Check employee's job role against allowed_roles
    department = "department"       # Check employee's department against allowed_departments
    specific_users = "specific_users"  # Whitelist of specific employee UUIDs


class AgentAccessRule(Base):
    """Defines who can access a specific agent within a tenant.

    One row per (tenant_id, agent_name) pair. If no row exists for an agent,
    access is PERMITTED by default (permissive default for new/unknown agents).
    """
    __tablename__ = "agent_access_rules"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    agent_name: Mapped[str] = mapped_column(String(100))
    # agent_name values: "deema", "ahmad", "mohammad", "waleed", "yara", "dept:{uuid}"

    access_type: Mapped[AccessType] = mapped_column(
        SAEnum(AccessType, name="accesstype", create_constraint=False),
        default=AccessType.all,
    )

    # JSONB arrays — only the relevant field is checked based on access_type.
    # Using JSONB instead of association tables for simplicity: the number of roles
    # and departments is small (< 50 per tenant), and JSONB supports gin indexing.
    allowed_roles: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # Values: "employee", "manager", "department_head", "hr_specialist",
    #         "hr_manager", "hr_admin", "it_admin", "c_suite", "hiring_manager"

    allowed_departments: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # Values: list of department UUID strings

    allowed_users: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # Values: list of employee UUID strings

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    tenant = relationship("Tenant")

    __table_args__ = (
        Index("ix_agent_access_tenant_agent", "tenant_id", "agent_name", unique=True),
    )
```

#### 5.3.2 Employee Role Derivation

The `Employee` model has no explicit `role` column. Employee role is derived from existing data:

```python
# File: backend/app/utils/employee_role.py (NEW)

from uuid import UUID
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.employee import Employee, Department


async def derive_employee_role(
    db: AsyncSession, tenant_id: UUID, employee_id: UUID
) -> str:
    """Derive an employee's access role from existing model data.

    Role hierarchy (highest wins):
    - "c_suite"          — job_title contains CEO/CFO/COO/CTO/CHRO/VP (EN or AR)
    - "department_head"  — employee is Department.manager_id for any department
    - "hr_admin"         — job_title contains 'HR Director' / 'HR Admin' / مدير الموارد البشرية
    - "hr_manager"       — job_title contains 'HR Manager' / مدير الموارد
    - "hiring_manager"   — employee is Department.manager_id AND has recruitment keyword in title
    - "manager"          — employee is manager_id for at least one other employee
    - "employee"         — default
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

    # C-suite check
    c_suite_keywords = ["ceo", "cfo", "coo", "cto", "chro", "chief", "vp ", "vice president"]
    c_suite_keywords_ar = ["رئيس تنفيذي", "نائب الرئيس"]
    if any(kw in title_lower for kw in c_suite_keywords) or any(kw in title_ar for kw in c_suite_keywords_ar):
        return "c_suite"

    # Department head check
    dept_result = await db.execute(
        select(func.count()).select_from(Department).where(
            Department.manager_id == employee_id,
            Department.tenant_id == tenant_id,
        )
    )
    is_dept_head = dept_result.scalar() > 0

    # HR role checks
    hr_admin_kw = ["hr director", "hr admin", "head of hr", "مدير الموارد البشرية"]
    if any(kw in title_lower or kw in title_ar for kw in hr_admin_kw):
        return "hr_admin"

    hr_mgr_kw = ["hr manager", "مدير الموارد", "hr lead"]
    if any(kw in title_lower or kw in title_ar for kw in hr_mgr_kw):
        return "hr_manager"

    if is_dept_head:
        return "department_head"

    # Hiring manager — department head with recruitment responsibility
    # (For now, all department heads are potential hiring managers)

    # Manager check — has direct reports
    report_result = await db.execute(
        select(func.count()).select_from(Employee).where(
            Employee.manager_id == employee_id,
            Employee.tenant_id == tenant_id,
        )
    )
    if report_result.scalar() > 0:
        return "manager"

    return "employee"
```

#### 5.3.3 Access Check Function

**File:** `backend/app/utils/agent_access.py` (NEW)

```python
"""Agent access control — checks if an employee can interact with an agent."""
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_access_rule import AgentAccessRule, AccessType

logger = logging.getLogger(__name__)

# In-process cache: (tenant_id, agent_name) → AgentAccessRule
# TTL managed by simple timestamp check. Invalidated on rule update via API.
_access_cache: dict[tuple[UUID, str], tuple[float, AgentAccessRule | None]] = {}
_CACHE_TTL_SECONDS = 300  # 5 minutes


async def check_agent_access(
    db: AsyncSession,
    tenant_id: UUID,
    employee_id: UUID,
    employee_role: str,
    employee_dept_id: UUID | None,
    agent_name: str,
) -> bool:
    """Check if an employee can access a specific agent.

    Logic:
    1. Query agent_access_rules for (tenant_id, agent_name, is_active=True)
    2. If no rule found → ALLOW (permissive default for new/dynamic agents)
    3. access_type = 'all' → ALLOW
    4. access_type = 'role_based' → employee_role in allowed_roles
    5. access_type = 'department' → str(employee_dept_id) in allowed_departments
    6. access_type = 'specific_users' → str(employee_id) in allowed_users

    For deployed agents (dept:{uuid}), first checks agent_access_rules, then falls
    back to DeployedAgent.scope_boundaries visibility settings if no explicit rule.
    """
    import time

    cache_key = (tenant_id, agent_name)
    now = time.time()

    # Check cache
    if cache_key in _access_cache:
        cached_time, cached_rule = _access_cache[cache_key]
        if now - cached_time < _CACHE_TTL_SECONDS:
            return _evaluate_rule(cached_rule, employee_id, employee_role, employee_dept_id)

    # Query DB
    result = await db.execute(
        select(AgentAccessRule).where(
            AgentAccessRule.tenant_id == tenant_id,
            AgentAccessRule.agent_name == agent_name,
            AgentAccessRule.is_active == True,
        )
    )
    rule = result.scalar_one_or_none()

    # Cache result (including None)
    _access_cache[cache_key] = (now, rule)

    return _evaluate_rule(rule, employee_id, employee_role, employee_dept_id)


def _evaluate_rule(
    rule: AgentAccessRule | None,
    employee_id: UUID,
    employee_role: str,
    employee_dept_id: UUID | None,
) -> bool:
    """Evaluate a single access rule. Returns True if access is allowed."""
    if rule is None:
        return True  # Permissive default: no rule = allow

    if rule.access_type == AccessType.all:
        return True

    if rule.access_type == AccessType.role_based:
        return employee_role in (rule.allowed_roles or [])

    if rule.access_type == AccessType.department:
        if employee_dept_id is None:
            return False
        return str(employee_dept_id) in (rule.allowed_departments or [])

    if rule.access_type == AccessType.specific_users:
        return str(employee_id) in (rule.allowed_users or [])

    return False  # Unknown access_type — deny


def invalidate_access_cache(tenant_id: UUID, agent_name: str | None = None) -> None:
    """Invalidate cached access rules. Called when admin updates rules via API.

    If agent_name is None, invalidates ALL rules for the tenant.
    """
    if agent_name:
        _access_cache.pop((tenant_id, agent_name), None)
    else:
        keys_to_remove = [k for k in _access_cache if k[0] == tenant_id]
        for k in keys_to_remove:
            del _access_cache[k]


async def get_accessible_agents(
    db: AsyncSession,
    tenant_id: UUID,
    employee_id: UUID | None,
    employee_role: str | None,
    employee_dept_id: UUID | None,
) -> list[str]:
    """Return list of agent names this employee can access.

    Used for: (a) @mention autocomplete filtering, (b) error messages listing available agents.
    """
    from app.agents.orchestrator import AGENTS

    if employee_id is None:
        return list(AGENTS.keys())

    role = employee_role or "employee"
    accessible = []
    for agent_name in AGENTS:
        if await check_agent_access(db, tenant_id, employee_id, role, employee_dept_id, agent_name):
            accessible.append(agent_name)

    # Also check deployed agents the employee can access
    from app.models.deployed_agent import DeployedAgent, AgentStatus
    dept_result = await db.execute(
        select(DeployedAgent).where(
            DeployedAgent.tenant_id == tenant_id,
            DeployedAgent.status == AgentStatus.active,
        )
    )
    for da in dept_result.scalars().all():
        da_name = f"dept:{da.id}"
        if await check_agent_access(db, tenant_id, employee_id, role, employee_dept_id, da_name):
            accessible.append(da_name)

    return accessible
```

#### 5.3.4 Default Seed Data

Seeded on tenant creation (add to tenant creation flow or migration):

```python
# File: backend/app/utils/seed_agent_access.py (NEW)

from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.agent_access_rule import AgentAccessRule, AccessType

DEFAULT_ACCESS_RULES = [
    {
        "agent_name": "deema",
        "access_type": AccessType.all,
        "allowed_roles": None,
    },
    {
        "agent_name": "waleed",
        "access_type": AccessType.all,
        "allowed_roles": None,
    },
    {
        "agent_name": "mohammad",
        "access_type": AccessType.role_based,
        "allowed_roles": ["hr_admin", "hr_manager", "hr_specialist", "hiring_manager", "department_head", "c_suite"],
    },
    {
        "agent_name": "ahmad",
        "access_type": AccessType.role_based,
        "allowed_roles": ["hr_admin", "hr_manager", "department_head", "c_suite"],
    },
    {
        "agent_name": "yara",
        "access_type": AccessType.role_based,
        "allowed_roles": ["hr_admin", "it_admin", "c_suite"],
    },
]


async def seed_agent_access_rules(db: AsyncSession, tenant_id: UUID) -> None:
    """Create default agent access rules for a new tenant.

    Idempotent — skips rules that already exist (checked by unique index
    on tenant_id + agent_name).
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    for rule_data in DEFAULT_ACCESS_RULES:
        stmt = pg_insert(AgentAccessRule).values(
            tenant_id=tenant_id,
            agent_name=rule_data["agent_name"],
            access_type=rule_data["access_type"],
            allowed_roles=rule_data["allowed_roles"],
        ).on_conflict_do_nothing(
            index_elements=["tenant_id", "agent_name"],
        )
        await db.execute(stmt)
    await db.flush()
```

#### 5.3.5 Deployed Agent Integration

For deployed agents (`dept:{uuid}`), access rules integrate with the existing `DeployedAgent.scope_boundaries` field (line 39 of `deployed_agent.py`):

1. **If `agent_access_rules` has a row for `dept:{uuid}`** — use that rule (explicit admin override).
2. **If no row exists** — fall back to `DeployedAgent.scope_boundaries.visibility`:
   - `"department_only"` → only employees in the same `department_id`
   - `"all"` → all employees in the tenant
   - `"custom"` → check `scope_boundaries.allowed_users`
3. **If no scope_boundaries** — allow all (permissive default).

This is handled in `check_agent_access()` by the "no rule found → allow" default, with a special path:

```python
# Add to check_agent_access() after the main logic, when agent_name starts with "dept:"
# and no explicit AgentAccessRule was found:

if agent_name.startswith("dept:") and rule is None:
    # Fall back to deployed agent's own visibility settings
    from app.models.deployed_agent import DeployedAgent
    try:
        agent_uuid = UUID(agent_name[5:])
    except ValueError:
        return False
    da_result = await db.execute(
        select(DeployedAgent).where(
            DeployedAgent.id == agent_uuid,
            DeployedAgent.tenant_id == tenant_id,
        )
    )
    da = da_result.scalar_one_or_none()
    if not da:
        return False
    scope = da.scope_boundaries or {}
    visibility = scope.get("visibility", "all")
    if visibility == "all":
        return True
    if visibility == "department_only":
        return employee_dept_id is not None and employee_dept_id == da.department_id
    if visibility == "custom":
        return str(employee_id) in scope.get("allowed_users", [])
    return True
```

#### 5.3.6 Admin API Endpoints

**File:** `backend/app/api/agent_access.py` (NEW)

| Method | Path | Auth | Request Body | Response | Description |
|--------|------|------|-------------|----------|-------------|
| GET | `/api/v1/agent-access` | Admin JWT | — | `list[AgentAccessRuleResponse]` | List all access rules for the admin's tenant |
| GET | `/api/v1/agent-access/{agent_name}` | Admin JWT | — | `AgentAccessRuleResponse` | Get rule for specific agent |
| PUT | `/api/v1/agent-access/{agent_name}` | Admin JWT | `AgentAccessRuleUpdate` | `AgentAccessRuleResponse` | Create or update access rule |
| DELETE | `/api/v1/agent-access/{agent_name}` | Admin JWT | — | `{"status": "deleted"}` | Delete rule (reverts to permissive default) |
| GET | `/api/v1/agent-access/employee/{emp_id}` | Admin JWT | — | `list[str]` | List agent names this employee can access |

**Request/Response Schemas:**

```python
from pydantic import BaseModel
from uuid import UUID


class AgentAccessRuleResponse(BaseModel):
    id: str
    tenant_id: str
    agent_name: str
    access_type: str          # "all" | "role_based" | "department" | "specific_users"
    allowed_roles: list[str] | None
    allowed_departments: list[str] | None
    allowed_users: list[str] | None
    is_active: bool
    created_at: str
    updated_at: str


class AgentAccessRuleUpdate(BaseModel):
    access_type: str          # "all" | "role_based" | "department" | "specific_users"
    allowed_roles: list[str] | None = None
    allowed_departments: list[str] | None = None
    allowed_users: list[str] | None = None
    is_active: bool = True
```

**Cache invalidation:** The PUT and DELETE endpoints call `invalidate_access_cache(tenant_id, agent_name)` after updating the DB.

---

### 5.4 Chat API Changes — Exact Schema Changes

**File:** `backend/app/api/chat.py` (MODIFY)

#### 5.4.1 ChatResponse Modifications

Current `ChatResponse` (lines 35-41):
```python
class ChatResponse(BaseModel):
    agent: str
    response: str
    conversation_id: str
    topic: str = ""
    suggestions: list[str] = []
```

New `ChatResponse`:
```python
class ChatResponse(BaseModel):
    agent: str                        # existing — canonical agent name ("deema", "ahmad", etc.)
    agent_display_name: str = ""      # NEW — human-readable name ("Deema" / "ديمة")
    agent_name_ar: str = ""           # NEW — Arabic name for bilingual UI
    agent_color: str = ""             # NEW — hex color for UI badge (#3B82F6)
    response: str                     # existing
    conversation_id: str              # existing
    topic: str = ""                   # existing
    suggestions: list[str] = []       # existing
    available_agents: list[dict] = [] # NEW — access-filtered list for @mention autocomplete
    routed_by: str = ""               # NEW — "mention" | "keyword" | "sticky" | "default"
```

**Agent display metadata constant** (add to `chat.py`):

```python
# Agent display info — synced with agentMap/agentColors in chat.html
AGENT_DISPLAY = {
    "deema":    {"name": "Deema",    "name_ar": "ديمة",  "role": "Employee Services",   "role_ar": "خدمات الموظفين",   "color": "#4F46E5", "letter": "D"},
    "waleed":   {"name": "Waleed",   "name_ar": "وليد",  "role": "Onboarding",          "role_ar": "التهيئة",          "color": "#16A34A", "letter": "W"},
    "mohammad": {"name": "Mohammad", "name_ar": "محمد",  "role": "Recruitment",         "role_ar": "التوظيف",          "color": "#2563EB", "letter": "M"},
    "yara":     {"name": "Yara",     "name_ar": "يارا",  "role": "Agent Factory",       "role_ar": "مصنع الوكلاء",     "color": "#CA8A04", "letter": "Y"},
    "ahmad":    {"name": "Ahmad",    "name_ar": "أحمد",  "role": "CHRO Analytics",      "role_ar": "تحليلات الموارد",   "color": "#1E3A5F", "letter": "A"},
}
```

#### 5.4.2 Chat Endpoint Modifications

The `chat()` endpoint (lines 43-240) needs these changes:

**1. After employee lookup (line 71), derive role and load accessible agents:**

```python
    # ── NEW: Derive employee role for access control ──
    from app.utils.employee_role import derive_employee_role
    from app.utils.agent_access import get_accessible_agents

    employee_role = await derive_employee_role(db, chat_emp.tenant_id, emp_id)
    employee_dept_id = employee.department_id
```

**2. Modify orchestrator call (replace lines 188-197):**

```python
    # Load last_mentioned_agent from conversation (NEW)
    last_mentioned = getattr(conversation, 'last_mentioned_agent', None)

    orchestrator = AgentOrchestrator(db, employee.tenant_id)
    agent_name, response, new_last_mentioned = await orchestrator.handle_message(
        message=cleaned_message,
        employee_name=employee.first_name,
        employee_id=str(employee.id),
        conversation_history=history,
        current_agent=current_agent,
        language=employee.preferred_language,
        conversation_id=conversation.id,
        # ── NEW parameters ──
        last_mentioned_agent=last_mentioned,
        employee_role=employee_role,
        employee_dept_id=employee_dept_id,
    )

    # Update last_mentioned_agent on conversation (NEW)
    conversation.last_mentioned_agent = new_last_mentioned
```

**3. Add agent_name to saved messages (lines 207-220):**

```python
    # Save messages — add agent_name for per-agent context filtering (UC-04)
    db.add(Message(
        conversation_id=conversation.id,
        role="employee",
        content=cleaned_message,
        channel="web",
        language=employee.preferred_language,
        agent_name=agent_name,  # NEW — which agent this message was directed to
    ))
    db.add(Message(
        conversation_id=conversation.id,
        role="agent",
        content=response,
        channel="web",
        language=employee.preferred_language,
        agent_name=agent_name,  # NEW — which agent generated this response
    ))
```

**4. Build available_agents list and enriched response (replace lines 234-240):**

```python
    # Build access-filtered available agents list for autocomplete (NEW)
    accessible = await get_accessible_agents(
        db, chat_emp.tenant_id, emp_id, employee_role, employee_dept_id,
    )
    available_agents = []
    for a_name in accessible:
        info = AGENT_DISPLAY.get(a_name)
        if info:
            available_agents.append({
                "name": a_name,
                "display_name": info["name"],
                "name_ar": info["name_ar"],
                "role": info["role"],
                "role_ar": info["role_ar"],
                "color": info["color"],
                "letter": info["letter"],
            })
        elif a_name.startswith("dept:"):
            # Dynamic agent — fetch display info from DB
            da = await orchestrator.get_dynamic_agent(a_name)
            if da:
                config = da._config  # DeployedAgent row
                available_agents.append({
                    "name": a_name,
                    "display_name": config.name,
                    "name_ar": config.name_ar or config.name,
                    "role": config.role_title,
                    "role_ar": config.role_title_ar or config.role_title,
                    "color": "#DB2777",  # Default pink for deployed agents
                    "letter": config.name[0].upper(),
                })

    # Determine routing method for UI indicator
    from app.utils.mention_parser import parse_mention
    mentioned, _ = parse_mention(cleaned_message)
    if agent_name == "system":
        routed_by = "error"
    elif mentioned is not None:
        routed_by = "mention"
    elif last_mentioned and agent_name == last_mentioned:
        routed_by = "sticky"
    elif any(any(p in cleaned_message.lower() for p in phrases) for phrases in orchestrator.SWITCH_PHRASES.values()):
        routed_by = "switch"
    else:
        routed_by = "keyword"

    agent_info = AGENT_DISPLAY.get(agent_name, {})

    return ChatResponse(
        agent=agent_name,
        agent_display_name=agent_info.get("name", agent_name.capitalize()),
        agent_name_ar=agent_info.get("name_ar", ""),
        agent_color=agent_info.get("color", "#6B7280"),
        response=response,
        conversation_id=str(conversation.id),
        topic=conversation.topic or "",
        suggestions=suggestions,
        available_agents=available_agents,
        routed_by=routed_by,
    )
```

**5. Modify `/conversations/{id}/messages` endpoint to include agent_name per message:**

In the message response (around line 460), add `agent_name`:
```python
    "messages": [
        {
            "id": str(m.id),
            "role": m.role,
            "content": m.content,
            "agent_name": m.agent_name,  # NEW
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in messages
    ],
```

#### 5.4.3 Request Flow Diagram

```
Browser: POST /api/v1/chat
  { message: "@ahmad show analytics", conversation_id: "..." }
         │
         ▼
┌─────────────────────────────────┐
│ chat() endpoint                 │
│ ├─ validate_chat_message()      │
│ ├─ lookup Employee              │
│ ├─ derive_employee_role() ──────┤──→ "department_head"
│ ├─ find/create Conversation     │
│ ├─ load history (20 messages)   │
│ │                               │
│ ├─ orchestrator.handle_message()│
│ │   ├─ parse_mention()          │──→ ("ahmad", "show analytics")
│ │   ├─ check_agent_access()     │──→ True (dept_head in allowed_roles)
│ │   ├─ build_agent_context()    │──→ filter history for ahmad only
│ │   ├─ agent.respond()          │──→ Claude API call with ahmad's tools
│ │   └─ return ("ahmad", resp,   │
│ │          "ahmad")             │    last_mentioned_agent
│ │                               │
│ ├─ save Message (role=employee, │
│ │   agent_name="ahmad")         │
│ ├─ save Message (role=agent,    │
│ │   agent_name="ahmad")         │
│ ├─ update conversation:         │
│ │   agent_name="ahmad"          │
│ │   last_mentioned_agent="ahmad"│
│ │                               │
│ ├─ get_accessible_agents() ─────┤──→ ["deema", "waleed", "ahmad"]
│ └─ return ChatResponse          │
└─────────────────────────────────┘
         │
         ▼
Browser receives:
  {
    agent: "ahmad",
    agent_display_name: "Ahmad",
    agent_color: "#1E3A5F",
    response: "Here's the analytics...",
    available_agents: [
      { name: "deema", display_name: "Deema", color: "#4F46E5", ... },
      { name: "waleed", display_name: "Waleed", color: "#16A34A", ... },
      { name: "ahmad", display_name: "Ahmad", color: "#1E3A5F", ... }
    ],
    routed_by: "mention",
    suggestions: ["Workforce overview", "Salary distribution"]
  }
```

---

### 5.5 Per-Agent Conversation Context

#### 5.5.1 Message Storage Changes

Add `agent_name` column to the `messages` table (see `conversation.py` line 41):

```python
class Message(Base):
    __tablename__ = "messages"

    # ... existing columns (lines 45-53) ...
    agent_name: Mapped[str | None] = mapped_column(String(100), nullable=True)  # NEW
    #   - For role="employee": the agent this message was directed to
    #   - For role="agent": the agent that generated this response
    #   - For role="system": None (system messages are agent-agnostic)
```

This column is set by the chat endpoint when saving messages (see 5.4.2 step 3 above).

#### 5.5.2 Context Building Algorithm

When the orchestrator calls an agent, it must filter conversation history to only include messages relevant to that agent. This prevents context pollution (e.g., Ahmad seeing Deema's leave conversation).

```python
# File: backend/app/utils/agent_context.py (NEW)

def build_agent_context(
    messages: list[dict],
    target_agent: str,
    max_messages: int = 20,
) -> list[dict]:
    """Filter conversation history to only include messages relevant to target_agent.

    Args:
        messages: Full conversation history, each dict has:
            - role: "user" | "assistant"
            - content: str
            - agent_name: str | None (which agent this message belongs to)
        target_agent: canonical agent name to filter for
        max_messages: max messages to include (newest first, then reversed)

    Returns:
        Filtered list of messages in chronological order, containing:
        - All user messages directed to target_agent (agent_name == target_agent)
        - All assistant messages from target_agent (agent_name == target_agent)
        - The FIRST user message in the conversation (always included for context,
          even if directed to a different agent — helps the agent understand the
          conversation's starting context)

    Does NOT include:
        - Messages to/from other agents (prevents context pollution)
        - System messages

    Note: The CURRENT user message is always appended by the orchestrator
    after this function returns — it is NOT included in the input to this function.
    """
    if not messages:
        return []

    # Filter for target agent
    relevant = []
    first_user_msg = None

    for msg in messages:
        msg_agent = msg.get("agent_name")

        # Track first user message for context
        if msg["role"] == "user" and first_user_msg is None:
            first_user_msg = msg

        # Include messages belonging to target agent
        if msg_agent == target_agent:
            relevant.append({"role": msg["role"], "content": msg["content"]})

    # Ensure first user message is included for opening context
    if first_user_msg and first_user_msg.get("agent_name") != target_agent:
        relevant.insert(0, {"role": "user", "content": first_user_msg["content"]})

    # Trim to max_messages (take newest)
    if len(relevant) > max_messages:
        relevant = relevant[-max_messages:]

    return relevant
```

#### 5.5.3 Integration in Chat Endpoint

The history loading code in `chat.py` (lines 164-180) needs modification to include `agent_name`:

```python
    # Load conversation history — newest 20 messages, then reverse to chronological
    msg_result = await db.execute(
        select(Message)
        .where(
            Message.conversation_id == conversation.id,
            Message.role.in_(["employee", "agent"]),
        )
        .order_by(Message.created_at.desc())
        .limit(40)  # Load more to allow per-agent filtering (was 20)
    )
    raw_history = [
        {
            "role": "user" if m.role == "employee" else "assistant",
            "content": m.content,
            "agent_name": m.agent_name,  # NEW
        }
        for m in reversed(msg_result.scalars().all())
    ]

    # Filter to per-agent context AFTER routing determines which agent
    # (moved to after orchestrator.route() call)
```

Then, inside `handle_message()`, after routing determines `agent_name`, filter the context:

```python
    from app.utils.agent_context import build_agent_context

    # Filter conversation history to target agent's context
    filtered_history = build_agent_context(conversation_history, agent_name, max_messages=20)

    # Use filtered_history instead of full conversation_history for agent.respond()
    filtered_history.append({"role": "user", "content": cleaned_message})
    response = await agent.respond(
        filtered_history,
        employee_name,
        employee_id,
        language,
        conversation_id=conversation_id,
    )
```

#### 5.5.4 Context Window Management

| Scenario | Behavior |
|----------|----------|
| User talks only to Deema (10 messages) | Deema sees all 10 messages |
| User talks to Deema (5), then Ahmad (5) | Ahmad sees only his 5 messages + first user message for context |
| User switches back to Deema after Ahmad | Deema sees her 5 original messages (Ahmad's are filtered out) |
| Long conversation (50+ messages per agent) | Each agent sees last 20 of their own messages |
| New @mention to an agent with no prior messages | Agent sees only the current message + first conversation message |
| System messages (escalation notices) | Excluded from agent context (not role "user" or "assistant") |

**Memory impact:** Loading 40 messages from DB instead of 20, then filtering to ~20 per agent. Negligible additional cost — one extra DB fetch that was already indexed.

---

### 5.6 Frontend Architecture — Detailed UI Spec

**File:** `backend/static/chat.html` (MODIFY)

#### 5.6.1 Unified Thread Rendering

**Current behavior** (lines 2036-2155 `addMessage` function): Messages render in a single thread, with agent avatar/name header when `role === 'agent'`. The `agentMap` (line 2330) and `agentColors` (line 2338) provide display info.

**Changes needed:**

1. **Agent badge colors** — The current `agentColors` uses gradient strings. Keep gradients for avatars, add flat hex colors for badges:

```javascript
// ADD after agentColors (line 2344):
const agentBadgeColors = {
    deema:    '#4F46E5',
    waleed:   '#16A34A',
    mohammad: '#2563EB',
    yara:     '#CA8A04',
    ahmad:    '#1E3A5F',
};
```

2. **Auto-route indicator** — When `data.routed_by !== 'mention'`, show a subtle label above the agent response. Modify `addMessage` (around line 2047):

```javascript
// In addMessage(), after creating the header (line 2067), add route indicator:
if (role === 'agent' && agent && window._lastRoutedBy) {
    if (window._lastRoutedBy === 'keyword' || window._lastRoutedBy === 'sticky') {
        const routeLabel = document.createElement('div');
        routeLabel.className = 'auto-route-label';
        const arrow = '↗';
        const info = agentMap[agent] || { name: agent };
        routeLabel.textContent = `${arrow} auto-routed to ${info.name}`;
        group.insertBefore(routeLabel, group.firstChild);
    }
}
```

3. **CSS for auto-route label and agent badges:**

```css
/* Add to <style> section */
.auto-route-label {
    font-size: 10px;
    color: var(--text3);
    padding: 2px 8px;
    margin-bottom: 2px;
    font-style: italic;
}

.agent-badge {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 11px;
    font-weight: 500;
    color: white;
    margin-bottom: 4px;
}

.mention-chip {
    display: inline-block;
    background: var(--accent-light);
    color: var(--accent);
    padding: 1px 6px;
    border-radius: 4px;
    font-weight: 500;
    font-size: 13px;
}
```

#### 5.6.2 @Mention Autocomplete

**Trigger:** User types `@` in the message input (`#messageInput`, line 1497).

**Data source:** `available_agents` from the last `ChatResponse`. Cached in a JS variable, updated on each response.

```javascript
// ── NEW: @Mention Autocomplete System ──

let availableAgents = [];  // Populated from ChatResponse.available_agents

// State
let mentionDropdownVisible = false;
let mentionFilterText = '';
let mentionSelectedIndex = 0;
let mentionTriggerPos = -1;  // cursor position where @ was typed

function initMentionAutocomplete() {
    const input = document.getElementById('messageInput');
    const dropdown = document.createElement('div');
    dropdown.id = 'mentionDropdown';
    dropdown.className = 'mention-dropdown';
    dropdown.style.display = 'none';
    input.parentNode.style.position = 'relative';
    input.parentNode.appendChild(dropdown);

    input.addEventListener('input', handleMentionInput);
    input.addEventListener('keydown', handleMentionKeydown);
    document.addEventListener('click', (e) => {
        if (!e.target.closest('#mentionDropdown') && e.target !== input) {
            closeMentionDropdown();
        }
    });
}

function handleMentionInput(e) {
    const input = e.target;
    const value = input.value;
    const cursorPos = input.selectionStart;

    // Find the @ closest before cursor
    let atPos = -1;
    for (let i = cursorPos - 1; i >= 0; i--) {
        if (value[i] === '@') {
            // Check that @ is at start or after whitespace
            if (i === 0 || /\s/.test(value[i - 1])) {
                atPos = i;
                break;
            }
        }
        // Stop searching if we hit a space (no @ in this word)
        if (/\s/.test(value[i]) && value[i] !== '@') break;
    }

    if (atPos === -1) {
        closeMentionDropdown();
        return;
    }

    mentionTriggerPos = atPos;
    mentionFilterText = value.substring(atPos + 1, cursorPos).toLowerCase();

    const filtered = availableAgents.filter(a =>
        a.name.toLowerCase().startsWith(mentionFilterText) ||
        a.display_name.toLowerCase().startsWith(mentionFilterText) ||
        a.name_ar.startsWith(mentionFilterText)
    );

    if (filtered.length === 0) {
        closeMentionDropdown();
        return;
    }

    mentionSelectedIndex = 0;
    renderMentionDropdown(filtered);
}

function renderMentionDropdown(agents) {
    const dropdown = document.getElementById('mentionDropdown');
    dropdown.innerHTML = '';
    dropdown.style.display = 'block';
    mentionDropdownVisible = true;

    agents.forEach((agent, idx) => {
        const item = document.createElement('div');
        item.className = 'mention-item' + (idx === mentionSelectedIndex ? ' selected' : '');
        item.innerHTML = `
            <div class="mention-avatar" style="background:${agentColors[agent.name] || 'linear-gradient(135deg,#999,#bbb)'}">
                ${escapeHtml(agent.letter || agent.name[0].toUpperCase())}
            </div>
            <div class="mention-info">
                <div class="mention-name">${escapeHtml(agent.display_name)} <span class="mention-name-ar">${escapeHtml(agent.name_ar)}</span></div>
                <div class="mention-role">${escapeHtml(agent.role)}</div>
            </div>
        `;
        item.onclick = () => selectMention(agent);
        dropdown.appendChild(item);
    });

    // Position dropdown above the input
    const inputRect = document.getElementById('messageInput').getBoundingClientRect();
    dropdown.style.bottom = '100%';
    dropdown.style.left = '0';
    dropdown.style.marginBottom = '4px';
}

function handleMentionKeydown(e) {
    if (!mentionDropdownVisible) return;

    const dropdown = document.getElementById('mentionDropdown');
    const items = dropdown.querySelectorAll('.mention-item');

    if (e.key === 'ArrowDown') {
        e.preventDefault();
        mentionSelectedIndex = Math.min(mentionSelectedIndex + 1, items.length - 1);
        items.forEach((item, i) => item.classList.toggle('selected', i === mentionSelectedIndex));
    } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        mentionSelectedIndex = Math.max(mentionSelectedIndex - 1, 0);
        items.forEach((item, i) => item.classList.toggle('selected', i === mentionSelectedIndex));
    } else if (e.key === 'Enter' || e.key === 'Tab') {
        if (items.length > 0) {
            e.preventDefault();
            const selectedAgent = availableAgents.filter(a =>
                a.name.toLowerCase().startsWith(mentionFilterText) ||
                a.display_name.toLowerCase().startsWith(mentionFilterText) ||
                a.name_ar.startsWith(mentionFilterText)
            )[mentionSelectedIndex];
            if (selectedAgent) selectMention(selectedAgent);
        }
    } else if (e.key === 'Escape') {
        closeMentionDropdown();
    }
}

function selectMention(agent) {
    const input = document.getElementById('messageInput');
    const value = input.value;

    // Replace @filterText with @agent_name
    const before = value.substring(0, mentionTriggerPos);
    const after = value.substring(mentionTriggerPos + 1 + mentionFilterText.length);
    input.value = before + '@' + agent.name + ' ' + after.trimStart();

    closeMentionDropdown();
    input.focus();

    // Move cursor to after the inserted mention
    const newPos = mentionTriggerPos + agent.name.length + 2; // +2 for @ and space
    input.setSelectionRange(newPos, newPos);
}

function closeMentionDropdown() {
    const dropdown = document.getElementById('mentionDropdown');
    if (dropdown) dropdown.style.display = 'none';
    mentionDropdownVisible = false;
}
```

**CSS for mention dropdown:**

```css
.mention-dropdown {
    position: absolute;
    bottom: 100%;
    left: 8px;
    right: 8px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    box-shadow: var(--shadow-lg);
    max-height: 240px;
    overflow-y: auto;
    z-index: 100;
    margin-bottom: 4px;
}

.mention-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 12px;
    cursor: pointer;
    transition: background var(--transition);
}

.mention-item:hover, .mention-item.selected {
    background: var(--accent-light);
}

.mention-avatar {
    width: 28px;
    height: 28px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    color: white;
    font-size: 12px;
    font-weight: 600;
    flex-shrink: 0;
}

.mention-info { flex: 1; min-width: 0; }

.mention-name {
    font-size: 13px;
    font-weight: 500;
    color: var(--text);
}

.mention-name-ar {
    font-size: 11px;
    color: var(--text3);
    margin-left: 6px;
}

.mention-role {
    font-size: 11px;
    color: var(--text2);
}
```

#### 5.6.3 Sidebar Transformation

**Current behavior** (lines 2372-2460, `buildAgentTree` function): The sidebar shows agents as expandable sections, each containing their conversations. Clicking an agent header expands to show conversations. Clicking a conversation loads it.

**New behavior:** Agent headers in the sidebar, when clicked, insert `@agent_name ` into the chat input instead of expanding conversations. Conversations are listed in a flat list below, not grouped by agent.

**Changes to `buildAgentTree()` (rename to `buildSidebar()`):**

```javascript
function buildSidebar(conversations) {
    const tree = document.getElementById('agentTree');
    tree.innerHTML = '';

    // ── Section 1: Agent @mention shortcuts ──
    const mentionSection = document.createElement('div');
    mentionSection.className = 'sidebar-section';

    const mentionLabel = document.createElement('div');
    mentionLabel.className = 'sidebar-section-label';
    mentionLabel.textContent = 'AGENTS';
    mentionSection.appendChild(mentionLabel);

    // Only show agents the employee has access to
    const accessibleNames = availableAgents.map(a => a.name);
    const agentsToShow = accessibleNames.length > 0 ? accessibleNames : agentOrder;

    agentsToShow.forEach(agentName => {
        if (agentName.startsWith('dept:')) return; // Show dept agents separately
        const info = agentMap[agentName] || {};
        const color = agentColors[agentName] || 'linear-gradient(135deg, #999, #bbb)';

        const item = document.createElement('div');
        item.className = 'agent-mention-item';
        item.innerHTML = `
            <div class="ai-avatar" style="background:${color}; width:24px; height:24px; font-size:11px;">
                ${info.letter || agentName[0].toUpperCase()}
                <div class="online-dot"></div>
            </div>
            <span class="ai-name">@${escapeHtml(info.name || agentName)}</span>
            <span class="ai-role-tag">${escapeHtml(info.role || '')}</span>
        `;
        item.onclick = () => insertMentionFromSidebar(agentName);
        item.title = `Click to @mention ${info.name || agentName}`;
        mentionSection.appendChild(item);
    });

    tree.appendChild(mentionSection);

    // ── Section 2: Recent conversations (flat list, not grouped by agent) ──
    const convSection = document.createElement('div');
    convSection.className = 'sidebar-section';

    const convLabel = document.createElement('div');
    convLabel.className = 'sidebar-section-label';
    convLabel.textContent = 'CONVERSATIONS';
    convSection.appendChild(convLabel);

    // New chat button
    const newBtn = document.createElement('div');
    newBtn.className = 'new-chat-btn';
    newBtn.innerHTML = '<span>+</span> New conversation';
    newBtn.onclick = () => startNewChat('deema');
    convSection.appendChild(newBtn);

    // Flat conversation list (newest first), showing agent badge per conversation
    conversations.forEach(c => {
        const item = document.createElement('div');
        item.className = 'conv-item' + (activeConversationId === c.id ? ' active' : '');
        const badgeColor = agentBadgeColors[c.agent_name] || '#6B7280';
        item.innerHTML = `
            <span class="conv-agent-dot" style="background:${badgeColor}"></span>
            <span class="conv-label">${escapeHtml(c.topic || 'New conversation')}</span>
        `;
        item.onclick = () => resumeConversation(c.id, c.agent_name);
        convSection.appendChild(item);
    });

    tree.appendChild(convSection);
}

function insertMentionFromSidebar(agentName) {
    const input = document.getElementById('messageInput');
    const currentValue = input.value;

    // If input already has content, add space before @mention
    const prefix = currentValue && !currentValue.endsWith(' ') ? ' ' : '';
    input.value = currentValue + prefix + '@' + agentName + ' ';
    input.focus();

    // Position cursor at end
    const len = input.value.length;
    input.setSelectionRange(len, len);
}
```

**CSS for sidebar @mention items:**

```css
.agent-mention-item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 12px;
    cursor: pointer;
    border-radius: var(--radius-sm);
    transition: background var(--transition);
}

.agent-mention-item:hover {
    background: var(--accent-lighter);
}

.ai-role-tag {
    font-size: 10px;
    color: var(--text3);
    margin-left: auto;
}

.conv-agent-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
}
```

#### 5.6.4 sendMessage Modifications

Modify `sendMessage()` (line 1870) to capture `routed_by` and `available_agents` from response:

```javascript
// In sendMessage(), after line 1908 (data received from API):
if (res.ok) {
    // Store routing info for UI indicators
    window._lastRoutedBy = data.routed_by || 'keyword';

    // Update available agents for @mention autocomplete
    if (data.available_agents && data.available_agents.length > 0) {
        availableAgents = data.available_agents;
    }

    addMessage('agent', data.agent, data.response, isAr, data.suggestions);
    selectedAgent = data.agent;
    activeConversationId = data.conversation_id;
    updateAgent(data.agent);
    detectIntent(message, data.response);
    if (soundEnabled) playNotifSound();
    loadPastConversations();
}
```

#### 5.6.5 Quick Actions Bar Integration

The quick actions bar (line 1938 `loadQuickActions`) already sets `selectedAgent` when an action has an `agent` property (line 1958). With unified chat, quick actions should instead insert `@agent_name` + the message:

```javascript
// Modify the quick action click handler (around line 1957):
btn.onclick = () => {
    if (action.agent) {
        // Instead of switching agent, insert @mention + message
        document.getElementById('messageInput').value = `@${action.agent} ${action.message}`;
    } else {
        document.getElementById('messageInput').value = action.message;
    }
    sendMessage();
};
```

#### 5.6.6 Initialization

Add to the initialization sequence (after login/auth completes):

```javascript
// After successful login, initialize mention autocomplete
initMentionAutocomplete();

// Set default available agents (will be updated on first API response)
availableAgents = agentOrder.map(name => ({
    name,
    display_name: agentMap[name]?.name || name,
    name_ar: '', // Updated on first response
    role: agentMap[name]?.role || '',
    color: agentBadgeColors[name] || '#6B7280',
    letter: agentMap[name]?.letter || name[0].toUpperCase(),
}));
```

---

### 5.7 Database Migration

**File:** `backend/alembic/versions/xxxx_add_unified_chat_tables.py` (NEW)

#### 5.7.1 New Table: `agent_access_rules`

```python
def upgrade() -> None:
    # 1. Create agent_access_rules table
    op.create_table(
        'agent_access_rules',
        sa.Column('id', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', sa.UUID(), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('agent_name', sa.String(100), nullable=False),
        sa.Column('access_type', sa.String(20), nullable=False, server_default='all'),
        sa.Column('allowed_roles', postgresql.JSONB(), nullable=True),
        sa.Column('allowed_departments', postgresql.JSONB(), nullable=True),
        sa.Column('allowed_users', postgresql.JSONB(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_agent_access_tenant_agent', 'agent_access_rules',
                     ['tenant_id', 'agent_name'], unique=True)
    op.create_index('ix_agent_access_rules_tenant_id', 'agent_access_rules', ['tenant_id'])
```

#### 5.7.2 Altered Column: `messages.agent_name`

```python
    # 2. Add agent_name to messages table
    op.add_column('messages',
        sa.Column('agent_name', sa.String(100), nullable=True)
    )
    op.create_index('ix_messages_conversation_agent',
                     'messages', ['conversation_id', 'agent_name'])
```

#### 5.7.3 Altered Column: `conversations.last_mentioned_agent`

```python
    # 3. Add last_mentioned_agent to conversations table
    op.add_column('conversations',
        sa.Column('last_mentioned_agent', sa.String(100), nullable=True)
    )
```

#### 5.7.4 Seed Default Access Rules

```python
    # 4. Seed default access rules for all existing tenants
    # Uses raw SQL for migration context (no async ORM available)
    op.execute("""
        INSERT INTO agent_access_rules (id, tenant_id, agent_name, access_type, allowed_roles)
        SELECT gen_random_uuid(), t.id, 'deema', 'all', NULL
        FROM tenants t
        WHERE NOT EXISTS (
            SELECT 1 FROM agent_access_rules r
            WHERE r.tenant_id = t.id AND r.agent_name = 'deema'
        );

        INSERT INTO agent_access_rules (id, tenant_id, agent_name, access_type, allowed_roles)
        SELECT gen_random_uuid(), t.id, 'waleed', 'all', NULL
        FROM tenants t
        WHERE NOT EXISTS (
            SELECT 1 FROM agent_access_rules r
            WHERE r.tenant_id = t.id AND r.agent_name = 'waleed'
        );

        INSERT INTO agent_access_rules (id, tenant_id, agent_name, access_type, allowed_roles)
        SELECT gen_random_uuid(), t.id, 'mohammad', 'role_based',
            '["hr_admin", "hr_manager", "hr_specialist", "hiring_manager", "department_head", "c_suite"]'::jsonb
        FROM tenants t
        WHERE NOT EXISTS (
            SELECT 1 FROM agent_access_rules r
            WHERE r.tenant_id = t.id AND r.agent_name = 'mohammad'
        );

        INSERT INTO agent_access_rules (id, tenant_id, agent_name, access_type, allowed_roles)
        SELECT gen_random_uuid(), t.id, 'ahmad', 'role_based',
            '["hr_admin", "hr_manager", "department_head", "c_suite"]'::jsonb
        FROM tenants t
        WHERE NOT EXISTS (
            SELECT 1 FROM agent_access_rules r
            WHERE r.tenant_id = t.id AND r.agent_name = 'ahmad'
        );

        INSERT INTO agent_access_rules (id, tenant_id, agent_name, access_type, allowed_roles)
        SELECT gen_random_uuid(), t.id, 'yara', 'role_based',
            '["hr_admin", "it_admin", "c_suite"]'::jsonb
        FROM tenants t
        WHERE NOT EXISTS (
            SELECT 1 FROM agent_access_rules r
            WHERE r.tenant_id = t.id AND r.agent_name = 'yara'
        );
    """)


def downgrade() -> None:
    op.drop_column('conversations', 'last_mentioned_agent')
    op.drop_index('ix_messages_conversation_agent', 'messages')
    op.drop_column('messages', 'agent_name')
    op.drop_index('ix_agent_access_tenant_agent', 'agent_access_rules')
    op.drop_index('ix_agent_access_rules_tenant_id', 'agent_access_rules')
    op.drop_table('agent_access_rules')
```

#### 5.7.5 Backfill Existing Messages

Existing messages have `agent_name = NULL`. A one-time backfill populates this from the parent conversation's `agent_name`:

```python
    # 5. Backfill agent_name on existing messages from their conversation
    op.execute("""
        UPDATE messages m
        SET agent_name = c.agent_name
        FROM conversations c
        WHERE m.conversation_id = c.id
        AND m.agent_name IS NULL
        AND m.role IN ('employee', 'agent')
    """)
```

This is safe because before unified chat, each conversation only had one agent.

---

### 5.8 Testing Strategy for Track 5

#### 5.8.1 Unit Tests — @Mention Parser (UC-01)

**File:** `backend/tests/test_mention_parser.py` — see section 5.1.5 above for full test suite.

**Coverage:**
- English names (all 5 agents)
- Arabic names (all 5 agents)
- Aliases (ahmed, sarah, norah, walid, mohammed, dima)
- Diacritics stripping
- Position variants (start, middle, end)
- Edge cases (email, no mention, multiple mentions, empty after @)
- `dept:{uuid}` format
- `get_mentioned_raw()` utility

#### 5.8.2 Integration Tests — Orchestrator Routing (UC-02)

**File:** `backend/tests/test_orchestrator_mention.py`

```python
import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4
from app.agents.orchestrator import AgentOrchestrator

@pytest.fixture
def orchestrator(db_session, tenant_id):
    return AgentOrchestrator(db_session, tenant_id)

class TestMentionRouting:
    """UC-02: Orchestrator @mention integration tests."""

    async def test_mention_overrides_keyword(self, orchestrator):
        """@mention should take priority over keyword routing."""
        # "leave" is a deema keyword, but @ahmad should win
        name, cleaned, error = await orchestrator.route(
            "@ahmad check leave patterns",
            employee_id=uuid4(), employee_role="c_suite",
            employee_dept_id=uuid4(),
        )
        assert name == "ahmad"
        assert "check leave patterns" in cleaned
        assert error is None

    async def test_mention_overrides_sticky(self, orchestrator):
        """@mention should override sticky agent."""
        name, cleaned, error = await orchestrator.route(
            "@mohammad hire someone",
            current_agent="deema",
            employee_id=uuid4(), employee_role="hr_admin",
            employee_dept_id=uuid4(),
        )
        assert name == "mohammad"

    async def test_unrecognized_mention_returns_error(self, orchestrator):
        """Unknown @mention should produce an error with available agents."""
        name, _, error = await orchestrator.route(
            "@bob help me",
            employee_id=uuid4(), employee_role="employee",
            employee_dept_id=uuid4(),
        )
        assert name == "system"
        assert error is not None
        assert "@bob" in error

    async def test_access_denied_mention(self, orchestrator, seed_access_rules):
        """@mention to restricted agent should produce access denied error."""
        name, _, error = await orchestrator.route(
            "@ahmad analytics",
            employee_id=uuid4(), employee_role="employee",  # employee can't access ahmad
            employee_dept_id=uuid4(),
        )
        assert name == "system"
        assert "don't have access" in error

    async def test_no_mention_falls_to_keyword(self, orchestrator):
        """Without @mention, keyword routing should work as before."""
        name, cleaned, error = await orchestrator.route(
            "check my leave balance",
            employee_id=uuid4(), employee_role="employee",
            employee_dept_id=uuid4(),
        )
        assert name == "deema"
        assert error is None

    async def test_sticky_mention(self, orchestrator):
        """After @mention, follow-up without @mention should stick."""
        name, _, error = await orchestrator.route(
            "show me more details",
            last_mentioned_agent="ahmad",
            employee_id=uuid4(), employee_role="c_suite",
            employee_dept_id=uuid4(),
        )
        assert name == "ahmad"

    async def test_arabic_mention(self, orchestrator):
        """Arabic @mention should resolve to correct agent."""
        name, cleaned, error = await orchestrator.route(
            "@ديمة كم رصيد إجازاتي؟",
            employee_id=uuid4(), employee_role="employee",
            employee_dept_id=uuid4(),
        )
        assert name == "deema"
        assert "كم رصيد إجازاتي؟" in cleaned
```

#### 5.8.3 Access Control Tests (UC-05)

**File:** `backend/tests/test_agent_access.py`

```python
import pytest
from uuid import uuid4
from app.utils.agent_access import check_agent_access, get_accessible_agents
from app.models.agent_access_rule import AgentAccessRule, AccessType

class TestAgentAccess:
    """UC-05: Agent access privilege tests."""

    async def test_all_access_allows_everyone(self, db, tenant_id):
        """access_type='all' grants access to any employee."""
        db.add(AgentAccessRule(
            tenant_id=tenant_id, agent_name="deema",
            access_type=AccessType.all,
        ))
        await db.flush()
        assert await check_agent_access(
            db, tenant_id, uuid4(), "employee", uuid4(), "deema"
        ) is True

    async def test_role_based_allows_matching_role(self, db, tenant_id):
        db.add(AgentAccessRule(
            tenant_id=tenant_id, agent_name="ahmad",
            access_type=AccessType.role_based,
            allowed_roles=["c_suite", "hr_admin"],
        ))
        await db.flush()
        assert await check_agent_access(
            db, tenant_id, uuid4(), "c_suite", uuid4(), "ahmad"
        ) is True

    async def test_role_based_denies_wrong_role(self, db, tenant_id):
        db.add(AgentAccessRule(
            tenant_id=tenant_id, agent_name="ahmad",
            access_type=AccessType.role_based,
            allowed_roles=["c_suite", "hr_admin"],
        ))
        await db.flush()
        assert await check_agent_access(
            db, tenant_id, uuid4(), "employee", uuid4(), "ahmad"
        ) is False

    async def test_no_rule_allows_by_default(self, db, tenant_id):
        """Permissive default: no rule = access granted."""
        assert await check_agent_access(
            db, tenant_id, uuid4(), "employee", uuid4(), "new_agent"
        ) is True

    async def test_department_access(self, db, tenant_id):
        dept_id = uuid4()
        db.add(AgentAccessRule(
            tenant_id=tenant_id, agent_name="custom_agent",
            access_type=AccessType.department,
            allowed_departments=[str(dept_id)],
        ))
        await db.flush()
        assert await check_agent_access(
            db, tenant_id, uuid4(), "employee", dept_id, "custom_agent"
        ) is True
        assert await check_agent_access(
            db, tenant_id, uuid4(), "employee", uuid4(), "custom_agent"
        ) is False

    async def test_specific_users(self, db, tenant_id):
        emp_id = uuid4()
        db.add(AgentAccessRule(
            tenant_id=tenant_id, agent_name="vip_agent",
            access_type=AccessType.specific_users,
            allowed_users=[str(emp_id)],
        ))
        await db.flush()
        assert await check_agent_access(
            db, tenant_id, emp_id, "employee", uuid4(), "vip_agent"
        ) is True
        assert await check_agent_access(
            db, tenant_id, uuid4(), "employee", uuid4(), "vip_agent"
        ) is False

    async def test_get_accessible_agents(self, db, tenant_id):
        """get_accessible_agents returns only agents the employee can access."""
        # Seed rules: deema=all, ahmad=c_suite only
        db.add(AgentAccessRule(
            tenant_id=tenant_id, agent_name="deema",
            access_type=AccessType.all,
        ))
        db.add(AgentAccessRule(
            tenant_id=tenant_id, agent_name="ahmad",
            access_type=AccessType.role_based,
            allowed_roles=["c_suite"],
        ))
        await db.flush()

        # Employee role can't access ahmad
        accessible = await get_accessible_agents(
            db, tenant_id, uuid4(), "employee", uuid4()
        )
        assert "deema" in accessible
        assert "ahmad" not in accessible

    async def test_tenant_isolation(self, db):
        """Access rules for tenant A should not affect tenant B."""
        tenant_a = uuid4()
        tenant_b = uuid4()
        db.add(AgentAccessRule(
            tenant_id=tenant_a, agent_name="ahmad",
            access_type=AccessType.role_based,
            allowed_roles=["c_suite"],
        ))
        await db.flush()
        # Tenant B has no rules — permissive default
        assert await check_agent_access(
            db, tenant_b, uuid4(), "employee", uuid4(), "ahmad"
        ) is True
```

#### 5.8.4 Per-Agent Context Tests (UC-04)

**File:** `backend/tests/test_agent_context.py`

```python
import pytest
from app.utils.agent_context import build_agent_context

class TestAgentContext:
    """UC-04: Per-agent conversation context filtering."""

    def test_filters_to_target_agent(self):
        messages = [
            {"role": "user", "content": "check leave", "agent_name": "deema"},
            {"role": "assistant", "content": "Your balance is 14 days", "agent_name": "deema"},
            {"role": "user", "content": "show analytics", "agent_name": "ahmad"},
            {"role": "assistant", "content": "Here are the metrics", "agent_name": "ahmad"},
        ]
        result = build_agent_context(messages, "ahmad")
        assert len(result) == 3  # first user msg + ahmad's 2 messages
        assert result[-1]["content"] == "Here are the metrics"

    def test_includes_first_user_message(self):
        messages = [
            {"role": "user", "content": "hello", "agent_name": "deema"},
            {"role": "assistant", "content": "Hi!", "agent_name": "deema"},
            {"role": "user", "content": "analytics", "agent_name": "ahmad"},
        ]
        result = build_agent_context(messages, "ahmad")
        assert result[0]["content"] == "hello"  # First msg included for context

    def test_empty_messages(self):
        assert build_agent_context([], "deema") == []

    def test_no_messages_for_agent(self):
        messages = [
            {"role": "user", "content": "check leave", "agent_name": "deema"},
            {"role": "assistant", "content": "Balance is 14", "agent_name": "deema"},
        ]
        result = build_agent_context(messages, "ahmad")
        # Should include first user message only
        assert len(result) == 1
        assert result[0]["content"] == "check leave"

    def test_max_messages_limit(self):
        messages = [
            {"role": "user", "content": f"msg {i}", "agent_name": "deema"}
            for i in range(30)
        ]
        result = build_agent_context(messages, "deema", max_messages=10)
        assert len(result) == 10

    def test_agent_name_none_excluded(self):
        """Messages with no agent_name (legacy) should not match any agent."""
        messages = [
            {"role": "user", "content": "old msg", "agent_name": None},
            {"role": "user", "content": "new msg", "agent_name": "deema"},
        ]
        result = build_agent_context(messages, "deema")
        assert len(result) == 2  # first user msg (context) + deema's msg
```

#### 5.8.5 Frontend Behavior Tests (Manual + Automated)

| Test Case | Steps | Expected |
|-----------|-------|----------|
| @mention autocomplete appears | Type `@` in input | Dropdown shows accessible agents |
| Filter autocomplete | Type `@de` | Only Deema shown |
| Arabic filter | Type `@دي` | Deema shown (Arabic name match) |
| Select from autocomplete | Type `@de`, press Enter | Input becomes `@deema ` with cursor after space |
| Keyboard navigation | Type `@`, press ArrowDown, Enter | Second agent selected and inserted |
| Escape closes dropdown | Type `@`, press Escape | Dropdown closes, `@` remains in input |
| Sidebar @mention insert | Click agent in sidebar | `@agent_name ` inserted in input |
| Agent badge on response | Send `@deema check leave` | Response shows Deema avatar + name with blue accent |
| Auto-route label | Send `check leave` (no @mention) | Subtle "auto-routed to Deema" label above response |
| Access denied message | Send `@ahmad analytics` as regular employee | Error: "You don't have access to @ahmad" |
| Agent switch via @mention | Send `@deema leave`, then `@ahmad analytics` | Second response is from Ahmad, different color badge |
| Sticky @mention | Send `@deema leave`, then `more details` | Follow-up goes to Deema (no @mention needed) |
| Quick action with @mention | Click quick action for Ahmad | Input gets `@ahmad <action message>`, sends correctly |

---

### 5.9 New Files Summary

| File | Type | Description |
|------|------|-------------|
| `backend/app/utils/mention_parser.py` | NEW | @mention regex parser, agent name registry |
| `backend/app/utils/agent_access.py` | NEW | Access check function, cache, get_accessible_agents |
| `backend/app/utils/agent_context.py` | NEW | Per-agent conversation history filter |
| `backend/app/utils/employee_role.py` | NEW | Derive employee role from existing data |
| `backend/app/utils/seed_agent_access.py` | NEW | Default access rule seeding |
| `backend/app/models/agent_access_rule.py` | NEW | AgentAccessRule SQLAlchemy model |
| `backend/app/api/agent_access.py` | NEW | Admin API for access rule management |
| `backend/tests/test_mention_parser.py` | NEW | Parser unit tests |
| `backend/tests/test_orchestrator_mention.py` | NEW | Orchestrator routing integration tests |
| `backend/tests/test_agent_access.py` | NEW | Access control tests |
| `backend/tests/test_agent_context.py` | NEW | Per-agent context filter tests |
| `backend/alembic/versions/xxxx_unified_chat.py` | NEW | Migration: new table + altered columns |

### 5.10 Modified Files Summary

| File | Changes |
|------|---------|
| `backend/app/agents/orchestrator.py` | New `route()` signature with @mention priority, access checks, sticky @mention tracking. `handle_message()` returns `last_mentioned_agent`. Import `parse_mention`, `check_agent_access`. |
| `backend/app/api/chat.py` | `ChatResponse` adds 4 new fields. Chat endpoint derives employee role, passes to orchestrator, saves `agent_name` on messages, builds `available_agents`, sets `routed_by`. Message list endpoint returns `agent_name`. |
| `backend/app/models/conversation.py` | `Message` gains `agent_name` column. `Conversation` gains `last_mentioned_agent` column. |
| `backend/static/chat.html` | @mention autocomplete system, sidebar transformation, auto-route labels, agent badge colors, `availableAgents` state, `sendMessage` captures new response fields, quick actions insert @mention. |

---


## Build Order

### Week Plan (recommended sequence)

```
Day 1-2: Foundation
├── Track 4: Ahmad English-Only (S8-AHM-LANG-01) — 1 hour, no deps
├── Track 3: KM-01 Data Models + Migration — 2 hours
├── Track 5: UC-01 @mention parser — 2 hours
├── Track 5: UC-05 agent_access_rules model + seed — 2 hours
├── Track 2: CUX-04-01 Backend quick actions — 2 hours
└── Track 1: A3-01 predict_attrition_risk — 4 hours

Day 2-3: Core Pipeline
├── Track 5: UC-02 Orchestrator @mention integration — 4 hours
├── Track 3: KM-02 Ingestion pipeline — 4 hours
├── Track 3: KM-03 Scoped RAG retriever — 3 hours
├── Track 1: A3-02 forecast_budget — 3 hours
└── Track 1: A3-03 audit_gosi_compliance — 3 hours

Day 4-5: API + UI
├── Track 5: UC-03 Unified thread UI + @mention autocomplete — 6 hours
├── Track 3: KM-04 Admin API endpoints — 4 hours
├── Track 1: A3-04 get_policy_acknowledgments — 3 hours
├── Track 2: CUX-04-02 Frontend agent switching — 2 hours
├── Track 2: CUX-04-03 Suggestion chips boost — 1 hour
└── Track 3: KM-05 Knowledge UI page — 6 hours

Day 5-6: Integration + Polish
├── Track 5: UC-04 Per-agent conversation context — 3 hours
├── Track 1: A3-05 generate_custom_report (depends on all other A3 tools) — 4 hours
├── Track 3: KM-06 Policy migration script — 2 hours
└── Integration testing across all tracks — 4 hours
```

**Parallel work streams:**
- **Developer A:** Track 1 (Ahmad A3 tools) + Track 4 (English-only)
- **Developer B:** Track 3 (Knowledge Management)
- **Developer C:** Track 5 (Unified Chat + @Mention) + Track 2 (Quick Actions)

---

## Testing Strategy

### Track 1: Ahmad A3 Tools

**Unit tests per tool (in `/backend/tests/test_ahmad_a3.py`):**

For each of the 5 tools:
1. **Happy path:** Seed test employees, leave requests, attendance records, payslips, policies, and acknowledgments. Call tool, verify response schema matches spec.
2. **k-anonymity:** Create a department with 3 employees. Verify it appears in `too_small_to_report` or is excluded from department-level results.
3. **Tenant isolation:** Create employees in tenant A and tenant B. Call tool as tenant A, verify no tenant B data leaks.
4. **Empty data:** Call tool with no matching records. Verify graceful "No data found" response.
5. **Edge cases per tool:**
   - A3-01: New employee (< 30 days), zero leave records, all employees below median
   - A3-02: Negative custom growth, NULL salary_sar, all non-Saudi department
   - A3-03: NULL gosi_employee, salary above GOSI ceiling, no payslips for month
   - A3-04: Future effective_date policy, archived policy, new policy with 0% compliance
   - A3-05: Ambiguous query, 4+ domain query, out-of-scope query

**GOSI rate constants test:**
```python
def test_gosi_constants():
    assert GOSI_EMPLOYER_SAUDI_PCT == 0.12
    assert GOSI_EMPLOYEE_SAUDI_PCT == 0.10
    assert GOSI_EMPLOYER_NON_SAUDI_PCT == 0.02
    assert GOSI_SALARY_CEILING_SAR == 45_000
```

### Track 2: Quick Actions

1. **Backend:** Call `GET /api/v1/suggestions/quick-actions?agent=ahmad` with employee role, verify only role-appropriate Ahmad actions returned.
2. **Backend:** Call without `agent` param, verify existing behavior unchanged.
3. **Frontend:** Manual test -- switch agents in sidebar, verify quick actions bar updates with fade animation.
4. **Suggestions boost:** Call `GET /api/v1/suggestions?agent=deema`, verify deema-targeted suggestions have boosted priority.

### Track 3: Knowledge Management

1. **Model tests:** Create KnowledgeSource, KnowledgeChunk, AgentKnowledgeAssignment. Verify constraints (unique agent+source), cascading deletes, indexes.
2. **Ingestion tests:** Ingest a sample Markdown file. Verify:
   - Correct chunk count
   - Heading context prepended to chunks
   - Token counts are reasonable
   - Embeddings are 1536-dimensional
   - Atomicity on failure (mock OpenAI error, verify no partial chunks)
3. **Scoped retriever tests:**
   - Assign 2 sources to agent A, 3 to agent B. Search as agent A, verify only agent A's sources returned.
   - Search with no agent_id, verify global fallback returns all sources.
4. **API tests:** Full CRUD lifecycle -- create source, upload markdown, verify processing status transitions, assign to agent, unassign, soft delete.
5. **Capture endpoint:** Send raw text, verify Claude returns structured response with title, category, agents.
6. **Migration script:** Run on test data with existing policies. Verify KnowledgeSource records created, chunks copied with embeddings intact, idempotency on re-run.

### Track 4: Ahmad English-Only

1. **System prompt test:** Verify `_get_scope_rules()` output starts with "LANGUAGE RULE:".
2. **Integration test:** Send Arabic message to Ahmad ("اعطني ملخص القوى العاملة"), verify response is in English.
3. **Suggestions test:** Verify `_generate_suggestions()` still returns Arabic suggestions when `language == "ar"`.

---

## Integration Matrix

| Feature | Reads From | Writes To | Agent Impact | API Impact |
|---------|-----------|-----------|-------------|------------|
| A3-01 | Employee, Department, LeaveRequest, AttendanceRecord | None | Ahmad only | None |
| A3-02 | Employee, Department | None | Ahmad only | None |
| A3-03 | Payslip, Employee, Department | None | Ahmad only | None |
| A3-04 | HRPolicy, PolicyAcknowledgment, Employee, Department | None | Ahmad only | None |
| A3-05 | All A1/A2/A3 tool outputs | None | Ahmad only | None |
| CUX-04 | Employee | None | None | Modified endpoint |
| KM-01 | -- | knowledge_sources, knowledge_chunks, agent_knowledge_assignments | None | None |
| KM-02 | KnowledgeSource | KnowledgeChunk | None | None |
| KM-03 | KnowledgeChunk, AgentKnowledgeAssignment | None | All agents (future) | None |
| KM-04 | All KM tables | All KM tables | None | New router |
| KM-05 | -- | -- | None | New page |
| KM-06 | Policy, PolicyChunk | KnowledgeSource, KnowledgeChunk | None | None |
| AHM-LANG | -- | -- | Ahmad only | None |

### Data Flow

```
Track 1 — Ahmad A3 Tool Call Flow:
┌──────────┐     ┌──────────────┐     ┌──────────┐     ┌──────────┐
│ Employee  │────>│ Orchestrator │────>│  Ahmad   │────>│ Database │
│ (Chat UI) │     │  (routing)   │     │ (agent)  │     │ (SELECT) │
└──────────┘     └──────────────┘     └──────────┘     └──────────┘
                                            │
                                            ▼
                                      ┌──────────┐
                                      │  Claude  │ (formats in ENGLISH)
                                      │  (LLM)   │
                                      └──────────┘

Track 3 — Knowledge Ingestion Flow:
┌──────────┐     ┌──────────────┐     ┌──────────────────┐     ┌──────────┐
│ Admin UI  │────>│ POST /upload │────>│ ingest_markdown() │────>│ OpenAI   │
│ (KM page) │     │ (API)        │     │ (chunk + embed)   │     │ Embeddings│
└──────────┘     └──────────────┘     └──────────────────┘     └──────────┘
                                               │
                                               ▼
                                      ┌──────────────────┐
                                      │ knowledge_chunks  │ (pgvector)
                                      └──────────────────┘

Track 3 — Scoped RAG Search Flow:
┌──────────┐     ┌──────────┐     ┌──────────────────────┐     ┌──────────┐
│ Agent     │────>│ Scoped   │────>│ knowledge_chunks     │────>│ pgvector │
│ (any)     │     │ Retriever│     │ + agent_assignments  │     │ <=> cosine│
└──────────┘     └──────────┘     └──────────────────────┘     └──────────┘
```

---

## Open Questions

### For the CTO:

1. **A3-01 Role validation for individual risk scores:** The story says individual results require "manager/HR role". Currently we have no role field on Employee -- we detect managers via `Employee.manager_id` chain and HR via job title keywords (same as `_determine_role()` in suggestions.py). Should we use the same `_determine_role()` pattern, or should A3-01 simply check if `requesting_employee.manager_id` matches target employees? **My recommendation:** Use the manager_id chain check -- if the requesting employee is the manager of employees in the target department, show individuals. Otherwise, department-level only.

2. **A3-03 Missing `gosi_employer` column on Payslip:** The Payslip model has `gosi_employee` (employee GOSI deduction) but no `gosi_employer` column. The A3-03 audit tool can only verify the employee's GOSI deduction against the expected rate. The employer's share is estimated, not verified. Should we add a `gosi_employer` column to Payslip in this sprint for accurate auditing, or is estimated sufficient? **My recommendation:** Defer the column addition. Estimated is acceptable for Sprint 8. Add the column in a future payroll integration sprint.

3. **KM-05 Voice input browser support:** Web Speech API works in Chrome and Edge but not Firefox or Safari. Should we gate the voice button behind feature detection and show a tooltip ("Voice input requires Chrome or Edge"), or invest in server-side Whisper integration now? **My recommendation:** Feature detection with tooltip for Sprint 8. Whisper integration in Sprint 9 as the stories suggest.

4. **KM-04 Upload processing:** Should file upload trigger ingestion synchronously (simpler, but blocks the request until embedding completes) or asynchronously (returns 202, client polls)? **My recommendation:** Asynchronous via `asyncio.create_task()`. Embedding can take 10-30 seconds for large files, which exceeds acceptable HTTP response times. The client polls `GET /sources/{id}` to check `embedding_status`.

5. **KM-06 Migration timing:** Should the policy migration script run automatically during Alembic migration, or be a manual one-time script? **My recommendation:** Manual script (`python -m scripts.migrate_policies_to_knowledge`). Keep migrations additive-only. The migration is data-copy, not schema change, and should be run after verifying the new tables work correctly.

6. **A3-05 Custom report depth:** The `generate_custom_report` tool maps keywords to existing tools and calls them. Should it also support Claude-generated SQL for truly custom queries (e.g., "show me the average salary of employees hired in Q1 2026"), or should it be strictly limited to orchestrating existing tools? **My recommendation:** Strictly existing tools only. No raw SQL generation. This prevents SQL injection risk and keeps the tool safe. Unsupported queries get a clear "I can only report on [list of domains]" response.
