# Ahmad -- CHRO Agent: Full Implementation Plan

**Author:** Tariq (Product Owner)
**Date:** 2026-03-26
**Status:** Planning
**Supersedes:** Norah (Analytics) + Sarah (Compliance) -- merged by CTO decision
**Current state:** Two stubs -- Norah (3 mock tools: get_department_budget, get_workforce_metrics, generate_cost_report) and Sarah (3 mock tools: check_compliance_status, get_regulation_updates, create_compliance_alert)

---

## Agent Identity

| Field | Value |
|-------|-------|
| **Name** | Ahmad |
| **Name (AR)** | احمد |
| **Role** | CHRO -- Chief Human Resources Officer |
| **Division** | Analytics, Finance & Compliance |
| **Audience** | HR directors, executives, CEO/CFO, compliance officers |
| **Personality** | Strategic, data-driven, authoritative but approachable. Speaks in executive summaries. Always ties data to business impact. Backs every claim with numbers, flags risks before they become problems, and frames compliance as a business enabler rather than a burden. |

Ahmad is a **READ-ONLY** agent. He queries data and produces insights but never creates, updates, or deletes records. He is a consumer of every other agent's data.

---

## Vision

Ahmad is the **strategic brain of Krew** -- the single conversational interface for the C-suite and HR leadership. He merges what were previously two separate concerns (analytics and compliance) into a unified CHRO perspective, because in practice a Chief HR Officer never thinks about metrics without compliance context, and never thinks about compliance without data.

Ahmad answers questions like:
- "Give me the executive HR summary for this quarter."
- "What is our Nitaqat status, and how many Saudi hires do we need this year?"
- "Are we at risk of any labor law violations?"
- "Which department is burning through its budget fastest?"
- "Show me turnover trends -- are we losing Saudis at a higher rate?"
- "What is our GOSI compliance status?"
- "Predict our attrition risk for Q3."
- "Are all employees acknowledging the latest policies?"

All output is formatted for chat display: clean tables, percentages, directional indicators, and trend summaries in both Arabic and English.

---

## Data Sources (existing models -- no new tables required)

| Model | Key Fields for Ahmad | File |
|-------|---------------------|------|
| **Employee** | status, hire_date, end_date, is_saudi, salary_sar, gender, department_id, contract_type, probation_end_date, work_mode, gosi_registered | `models/employee.py` |
| **Department** | name, headcount_budget, cost_budget_sar | `models/employee.py` |
| **LeaveBalance** | leave_type, year, total_days, used_days | `models/leave.py` |
| **LeaveRequest** | leave_type, start_date, end_date, business_days, status, created_at | `models/leave.py` |
| **JobPosting** | title, department_id, status, salary_min/max, created_at | `models/candidate.py` |
| **Candidate** | stage, ai_match_score, created_at | `models/candidate.py` |
| **Interview** | status, overall_score, created_at, completed_at | `models/interview.py` |
| **AttendanceRecord** | date, status, overtime_hours, check_in, check_out | `models/attendance.py` |
| **WorkSchedule** | work_days, work_start, work_end, late_threshold_minutes | `models/attendance.py` |
| **Payslip** | year, month, basic_salary, housing_allowance, transport_allowance, gosi_employee, gross_salary, net_salary, total_deductions | `models/payslip.py` |
| **NitaqatConfig** | industry, size_category, thresholds, target_saudization_pct, alert_buffer_pct | `models/nitaqat.py` |
| **OnboardingAssignment** | status, started_at, completed_at | `models/onboarding.py` |
| **WorkforcePlan** | current_headcount, recommended_humans, recommended_ai_agents, estimated_annual_savings_sar, saudization_before/after | `models/workforce_plan.py` |
| **DeployedAgent** | status, performance_metrics | `models/deployed_agent.py` |
| **ComplianceRecord** | category, title, is_compliant, last_checked, next_deadline | `models/compliance.py` |
| **ComplianceAlert** | severity, title, regulation_reference, recommended_action, is_resolved, created_at | `models/compliance.py` |
| **HRPolicy** | title, category, status, version, effective_date | `models/hr_policy.py` |
| **PolicyAcknowledgment** | policy_id, employee_id, acknowledged_at | `models/hr_policy.py` |

---

## Phased Implementation

### Phase A1: Core HR Metrics + Compliance Status (8 tools)
**Goal:** Replace all 6 stub tools (3 from Norah, 3 from Sarah) with real DB queries and add 2 essential tools. After A1, Ahmad can answer the most common CHRO questions: headcount, Saudization, turnover, budget, and compliance posture -- all with live data.

### Phase A2: Cross-Domain Analytics (5 tools)
**Goal:** Cross-domain analytics that pull from recruitment pipeline, leave, attendance, and onboarding data. Funnel conversion, leave patterns, payroll cost trends.

### Phase A3: Predictive Intelligence + Governance Reports (5 tools)
**Goal:** Forward-looking analytics (attrition risk, budget forecast), compliance governance (GOSI audit, policy acknowledgment tracking), and the custom report generator.

---

## Phase A1: Core HR Metrics + Compliance Status

### Epic: A1 -- Foundational Workforce Analytics & Compliance Posture

---

**Story A1-01: Headcount Dashboard**
> As an HR director, I want to see current headcount broken down by department, status, gender, and nationality so that I have a real-time snapshot of my workforce.

**Tool:** `get_headcount_summary`

**What it does:** Queries all active Employee records for the tenant, groups them by the requested dimension, and returns totals with period-over-period change.

**Inputs:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| department_id | string (UUID) | No | Filter to one department; omit for org-wide |
| group_by | enum: department, status, gender, nationality, contract_type, work_mode | No | Grouping dimension (default: department) |

**Output:** JSON with total headcount, breakdown by requested dimension, and period-over-period change.

**DB Models queried:** Employee, Department

**Acceptance Criteria:**
- [ ] Given a tenant with 50 employees across 3 departments, when `get_headcount_summary` is called with no filters, then the response includes total=50 and per-department counts that sum to 50
- [ ] Given group_by=nationality, the response splits counts into saudi and non_saudi with a saudization_pct field
- [ ] Given group_by=gender, the response includes male_count, female_count, and female_pct
- [ ] All queries filter by tenant_id -- no cross-tenant data leakage
- [ ] Employees with status=terminated are excluded from active headcount but included in a separate terminated_count field
- [ ] Response includes a comparison with 30 days ago (change and change_pct)

**Priority:** P0
**Dependencies:** Employee model (exists), Department model (exists)
**Saudi-specific:** Saudization percentage calculation must match Nitaqat counting rules (only active employees count).

---

**Story A1-02: Saudization & Nitaqat Status**
> As an HR director, I want to see our current Saudization ratio and Nitaqat band so that I can ensure compliance with MOLSD regulations.

**Tool:** `get_saudization_status`

**What it does:** Computes the current Saudi/non-Saudi ratio from active employees, looks up the tenant's NitaqatConfig to determine the current band, and calculates the gap to target and risk buffer.

**Inputs:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| department_id | string (UUID) | No | Filter to one department; omit for org-wide |
| include_trend | boolean | No | Include monthly trend for the last 6 months (default: false) |

**Output:** JSON with saudi_count, non_saudi_count, total_active, saudization_pct, current_nitaqat_band, target_pct, gap_to_target, distance_to_next_band_down (risk buffer), and optional monthly trend array.

**DB Models queried:** Employee, NitaqatConfig

**Acceptance Criteria:**
- [ ] Given 30 Saudi and 70 non-Saudi active employees, saudization_pct=30.0 is returned
- [ ] Given NitaqatConfig thresholds, the correct band is determined (e.g., 30% with green_high_threshold=26% returns "green_high")
- [ ] Given include_trend=true, the response contains up to 6 monthly data points computed from hire_date and end_date history
- [ ] If no NitaqatConfig exists for the tenant, the response includes a warning and uses default thresholds
- [ ] The gap_to_target field shows how many Saudi hires are needed to reach the target
- [ ] Department-level queries return department-specific ratios
- [ ] Response includes the alert_buffer_pct and whether the tenant is within the danger zone of dropping a band

**Priority:** P0
**Dependencies:** Employee model, NitaqatConfig model
**Saudi-specific:** Core Saudi Labor Law compliance feature. Nitaqat band logic must match MOLSD rules for the configured industry and size category.

---

**Story A1-03: Turnover Analytics**
> As a CEO, I want to understand our turnover rate, broken down by voluntary vs. involuntary and by department, so that I can identify retention problems.

**Tool:** `get_turnover_metrics`

**What it does:** Counts terminated employees within the specified period, computes turnover rate against average headcount, and breaks down by department and tenure-at-exit buckets.

**Inputs:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| department_id | string (UUID) | No | Filter to one department |
| period | enum: monthly, quarterly, yearly | No | Time granularity (default: quarterly) |
| start_date | string (YYYY-MM-DD) | No | Start of analysis window (default: 12 months ago) |
| end_date | string (YYYY-MM-DD) | No | End of analysis window (default: today) |

**Output:** JSON with overall_turnover_rate, period_breakdown (array of {period_label, turnover_rate, terminations, avg_headcount}), department_comparison (if org-wide), and tenure_at_exit distribution.

**DB Models queried:** Employee, Department

**Acceptance Criteria:**
- [ ] Turnover rate = (terminated employees in period / average headcount in period) * 100, computed correctly
- [ ] Employees with end_date in the period and status=terminated are counted as terminations
- [ ] Average headcount is calculated as (start_headcount + end_headcount) / 2 for each sub-period
- [ ] Department comparison ranks departments by turnover rate descending and flags any department above 15% annualized
- [ ] Tenure at exit is bucketed: <6 months, 6-12 months, 1-2 years, 2-5 years, 5+ years
- [ ] Period-over-period change is included (e.g., "turnover improved by 2.1% vs. last quarter")

**Priority:** P0
**Dependencies:** Employee model (hire_date, end_date, status, department_id)
**Saudi-specific:** Probation-period terminations (within 90 days of hire) are flagged separately since they are common and treated differently under Saudi Labor Law Article 53.

---

**Story A1-04: Department Budget vs. Actual**
> As a department manager, I want to see my budget utilization -- allocated vs. spent -- so that I can manage costs proactively.

**Tool:** `get_department_budget` (replaces existing Norah stub)

**What it does:** Reads the department's cost_budget_sar, sums actual spend from Payslip records for the fiscal year, and projects year-end spend based on monthly burn rate.

**Inputs:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| department_id | string (UUID) | Yes | The department UUID |
| fiscal_year | integer | No | Year (default: current year) |

**Output:** JSON with allocated (from department.cost_budget_sar), spent (sum of payslips), remaining, utilization_pct, monthly_burn_rate, projected_year_end_spend, over_budget_risk (boolean), and salary_breakdown.

**DB Models queried:** Department, Payslip, Employee

**Acceptance Criteria:**
- [ ] Allocated amount comes from Department.cost_budget_sar
- [ ] Spent amount is computed as SUM(gross_salary) from Payslip records for employees in the department for the given fiscal year
- [ ] Monthly burn rate = spent / months_elapsed
- [ ] Projected year-end spend = burn_rate * 12, and over_budget_risk is True if projected > allocated
- [ ] If Department.cost_budget_sar is NULL, the response says "No budget configured for this department" and still shows actual spending
- [ ] Multi-tenant isolation: only payslips for the requesting tenant's employees are summed

**Priority:** P0
**Dependencies:** Department model (cost_budget_sar), Payslip model, Employee model
**Saudi-specific:** Currency is always SAR. GOSI employer contribution (12% of base salary for Saudis, 2% for non-Saudis) should be noted in the cost breakdown.

---

**Story A1-05: Salary Distribution Analysis**
> As an HR director, I want to see salary distribution across the organization or a department so that I can identify pay equity issues and outliers.

**Tool:** `get_salary_distribution`

**What it does:** Computes min, max, median, mean, percentile statistics on Employee.salary_sar for active employees, grouped by the requested dimension. Flags outliers but never exposes individual names.

**Inputs:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| department_id | string (UUID) | No | Filter to one department |
| group_by | enum: department, gender, nationality, job_title | No | Grouping dimension (default: department) |

**Output:** JSON with org_stats (min, max, median, mean, p25, p75), group_breakdown (same stats per group), and outlier_flags (count of employees more than 2 standard deviations from their group mean -- no names).

**DB Models queried:** Employee, Department

**Acceptance Criteria:**
- [ ] Statistics are computed from Employee.salary_sar for active employees only
- [ ] Employees with salary_sar=NULL are excluded and their count is reported as unmapped_count
- [ ] Gender pay gap analysis: when group_by=gender, the response includes a gender_pay_gap_pct field (median female / median male - 1) * 100
- [ ] Nationality grouping shows Saudi vs. non-Saudi salary medians
- [ ] Outlier detection flags count of employees whose salary is >2 std dev from their department median
- [ ] Output does NOT include employee names or IDs -- only aggregated statistics (privacy)

**Priority:** P1
**Dependencies:** Employee model (salary_sar, gender, is_saudi, department_id)
**Saudi-specific:** Pay gap analysis between Saudi and non-Saudi employees is a common reporting need for Saudization strategy.

---

**Story A1-06: Workforce Composition Overview**
> As a CEO, I want a single "state of the workforce" summary that covers headcount, Saudization, gender split, tenure distribution, and contract types so I can present to the board.

**Tool:** `get_workforce_overview` (replaces existing Norah get_workforce_metrics stub)

**What it does:** A comprehensive single-call summary that aggregates headcount, Saudization ratio, gender breakdown, tenure distribution, contract types, work modes, probation stats, and recent hires into one response.

**Inputs:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| department_id | string (UUID) | No | Filter to one department |

**Output:** Comprehensive JSON with sections: headcount, saudization, gender, tenure_distribution (bucketed), contract_type_breakdown, work_mode_breakdown, probation_stats (count on probation, upcoming completions), and new_hires_last_30_days.

**DB Models queried:** Employee, Department, NitaqatConfig

**Acceptance Criteria:**
- [ ] All metrics are computed from live Employee records filtered by tenant_id
- [ ] Tenure distribution buckets: <1 year, 1-2 years, 2-5 years, 5-10 years, 10+ years
- [ ] Probation stats include count of employees currently on probation and those completing probation in the next 30 days
- [ ] New hires count = employees with hire_date in the last 30 days
- [ ] Response is formatted with clear section headers so the LLM can present it as a structured summary

**Priority:** P0
**Dependencies:** Employee model
**Saudi-specific:** Saudization section mirrors A1-02 output. Contract types include Saudi-specific types (limited vs. unlimited contracts).

---

**Story A1-07: Compliance Status Dashboard**
> As a compliance officer, I want a single view of all compliance items -- which are compliant, which are overdue, and which are approaching deadlines -- so I can prioritize action.

**Tool:** `get_compliance_status` (replaces existing Sarah check_compliance_status stub)

**What it does:** Queries ComplianceRecord for the tenant, groups by category, computes overall compliance score, identifies overdue items (next_deadline < today and is_compliant=false), and surfaces active unresolved alerts.

**Inputs:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| department_id | string (UUID) | No | Filter by department (via related employees); omit for org-wide |
| category | enum: gosi, nitaqat, wps, labor_law, data_privacy, health_safety, financial, all | No | Compliance category to check (default: all) |

**Output:** JSON with overall_compliance_score (pct of items that are compliant), items_by_category (array of {category, total, compliant, non_compliant, overdue_count}), overdue_items (array with title, category, next_deadline, days_overdue), upcoming_deadlines (items due in next 30 days), active_alerts (unresolved ComplianceAlert records with severity).

**DB Models queried:** ComplianceRecord, ComplianceAlert

**Acceptance Criteria:**
- [ ] Given 10 compliance records, 8 compliant and 2 non-compliant, overall_compliance_score=80.0
- [ ] Overdue items are those where next_deadline < today AND is_compliant=false
- [ ] Upcoming deadlines include all items with next_deadline within the next 30 calendar days
- [ ] Active alerts are ComplianceAlert records where is_resolved=false, sorted by severity (critical first)
- [ ] Categories include Saudi-specific: gosi, nitaqat, wps (Wage Protection System)
- [ ] All queries filter by tenant_id
- [ ] If no compliance records exist, the response says "No compliance records configured -- set up compliance tracking to monitor regulatory status"

**Priority:** P0
**Dependencies:** ComplianceRecord model, ComplianceAlert model
**Saudi-specific:** Saudi categories (GOSI, Nitaqat, WPS, Saudi Labor Law) are first-class categories. GOSI registration compliance can be cross-referenced with Employee.gosi_registered.

---

**Story A1-08: Ahmad System Prompt & Scope Rules**
> As the system, Ahmad needs a tailored system prompt and scope boundaries so he responds strategically and stays within his domain.

**Acceptance Criteria:**
- [ ] Ahmad's `_get_scope_rules()` returns rules stating he handles: analytics, metrics, dashboards, reports, budgets, workforce composition, trends, predictions, compliance status, regulatory monitoring, audit readiness, GOSI compliance, Nitaqat tracking
- [ ] Ahmad does NOT handle: individual leave requests (defer to Deema), recruitment actions (defer to Mohammad), onboarding tasks (defer to Waleed), agent creation (defer to Sarah/Yara)
- [ ] Ahmad does NOT create or modify data -- he is strictly read-only. The one exception is noted below in A1-07 where Sarah had create_compliance_alert; this capability is NOT carried forward into Ahmad. Alert creation should be handled by a future compliance-write agent or an admin API.
- [ ] Ahmad's personality produces responses framed as executive summaries: lead with the headline number, then supporting breakdown, then recommendations
- [ ] Ahmad uses directional indicators: percentages, arrows or text like "up 3.2% from last quarter", red/yellow/green risk labels
- [ ] Bilingual: Ahmad responds in the user's preferred language with proper Arabic number formatting (e.g., "٣٤٢ موظف" or "342 employees")
- [ ] When asked about both metrics and compliance in one question, Ahmad cross-references them (e.g., "Saudization is 28% which puts us in the green_low Nitaqat band -- 2 hires away from dropping to yellow")

**Priority:** P0
**Dependencies:** BaseAgent (exists)
**Saudi-specific:** N/A

---

### A1 Coverage Matrix

| Capability | Story | Status |
|-----------|-------|--------|
| Real-time headcount dashboard | A1-01 | Covered |
| Saudization / Nitaqat compliance tracking | A1-02 | Covered |
| Turnover rate analysis | A1-03 | Covered |
| Department budget vs. actual | A1-04 | Covered |
| Salary distribution & pay equity | A1-05 | Covered |
| Workforce composition overview | A1-06 | Covered |
| Compliance status dashboard (from Sarah) | A1-07 | Covered |
| Agent personality & scope | A1-08 | Covered |

**Total A1 tools: 7** (get_headcount_summary, get_saudization_status, get_turnover_metrics, get_department_budget, get_salary_distribution, get_workforce_overview, get_compliance_status)
Plus 1 non-tool story (A1-08: system prompt).

**Stubs replaced:** 4 of 6 (Norah: get_department_budget, get_workforce_metrics; Sarah: check_compliance_status. Norah's generate_cost_report is replaced in A2. Sarah's get_regulation_updates is replaced in A3. Sarah's create_compliance_alert is dropped -- Ahmad is read-only.)

---

## Phase A2: Cross-Domain Analytics

### Epic: A2 -- Cross-Domain Analytics

---

**Story A2-01: Recruitment Funnel Analytics**
> As an HR director, I want to see our recruitment pipeline metrics -- applications, conversion rates at each stage, time to fill, and cost per hire -- so I can optimize our hiring process.

**Tool:** `get_recruitment_analytics`

**What it does:** Queries JobPosting, Candidate, and Interview records to build funnel conversion rates, compute time-to-fill, and break down by department.

**Inputs:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| department_id | string (UUID) | No | Filter to one department |
| start_date | string (YYYY-MM-DD) | No | Start of window (default: 6 months ago) |
| end_date | string (YYYY-MM-DD) | No | End of window (default: today) |

**Output:** JSON with: open_positions, total_applicants, funnel (array of {stage, count, conversion_rate_from_previous}), avg_time_to_fill_days, avg_ai_match_score, department_breakdown.

**DB Models queried:** JobPosting, Candidate, Interview

**Acceptance Criteria:**
- [ ] Funnel stages match CandidateStage enum: applied -> screened -> shortlisted -> interview_scheduled -> interviewed -> offer_sent -> hired
- [ ] Conversion rate at each stage = count_at_stage / count_at_previous_stage * 100
- [ ] Time to fill = average days between JobPosting.created_at and the earliest Candidate reaching "hired" stage for that posting
- [ ] Only includes JobPostings and Candidates belonging to the tenant
- [ ] If no recruitment data exists, the response says "No recruitment data available for this period" rather than returning zeros
- [ ] Rejected and withdrawn candidates are shown separately and not counted in funnel conversion

**Priority:** P1
**Dependencies:** JobPosting model, Candidate model, Interview model
**Saudi-specific:** Flag positions marked as requiring Saudi nationals (Saudization-mandatory roles).

---

**Story A2-02: Leave Usage Analytics**
> As an HR director, I want to see leave usage patterns -- which types are most used, which departments take the most leave, and when our peak absence periods are -- so I can plan coverage.

**Tool:** `get_leave_analytics`

**What it does:** Aggregates approved LeaveRequest records by type, department, and month to reveal usage patterns and seasonal peaks. Cross-references with LeaveBalance for utilization rate.

**Inputs:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| department_id | string (UUID) | No | Filter to one department |
| year | integer | No | Year to analyze (default: current year) |
| leave_type | string | No | Filter to one leave type |

**Output:** JSON with: total_leave_days_taken, by_type, by_department (with avg_per_employee), monthly_pattern (all 12 months), utilization_rate, pending_requests_count.

**DB Models queried:** LeaveRequest, LeaveBalance, Employee, Department

**Acceptance Criteria:**
- [ ] Only approved leave requests are counted in usage totals
- [ ] Monthly pattern shows all 12 months, with 0 for months with no leave
- [ ] Utilization rate = SUM(used_days) / SUM(total_days) from LeaveBalance for the year
- [ ] Department comparison includes average_days_per_employee to normalize for team size
- [ ] Pending requests count is included for operational awareness
- [ ] If year has no data yet (e.g., January), the response notes "partial year data"

**Priority:** P1
**Dependencies:** LeaveRequest model, LeaveBalance model, Employee model, Department model
**Saudi-specific:** Hajj leave usage is highlighted separately since it is a one-time entitlement. Ramadan period absence patterns should be noted if data is available.

---

**Story A2-03: Attendance & Overtime Analytics**
> As a department manager, I want to see attendance rates and overtime trends so I can identify workload imbalances and attendance issues.

**Tool:** `get_attendance_analytics`

**What it does:** Aggregates AttendanceRecord data to compute attendance rate, late rate, absence rate, overtime totals, and day-of-week patterns. Respects WorkSchedule for weekend exclusion.

**Inputs:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| department_id | string (UUID) | No | Filter to one department |
| start_date | string (YYYY-MM-DD) | No | Start date (default: current month start) |
| end_date | string (YYYY-MM-DD) | No | End date (default: today) |

**Output:** JSON with: attendance_rate_pct, late_rate_pct, absent_rate_pct, total_overtime_hours, avg_overtime_per_employee, department_comparison, daily_pattern (day-of-week attendance rates), top_overtime_departments.

**DB Models queried:** AttendanceRecord, WorkSchedule, Employee, Department

**Acceptance Criteria:**
- [ ] Attendance rate = records with status in (present, late) / total working day records * 100
- [ ] Late rate = records with status=late / total working day records * 100
- [ ] Weekend (Friday-Saturday) and holiday records are excluded from rate calculations
- [ ] Overtime hours are summed from AttendanceRecord.overtime_hours
- [ ] Daily pattern shows average attendance rate per day of week (Sun-Thu for Saudi standard)
- [ ] Department comparison ranks departments by attendance rate

**Priority:** P1
**Dependencies:** AttendanceRecord model, WorkSchedule model
**Saudi-specific:** Saudi weekend is Friday-Saturday. Work week is Sunday-Thursday. Ramadan reduced hours (6 hours/day) should be accounted for in overtime calculations.

---

**Story A2-04: Onboarding Completion Analytics**
> As an HR director, I want to see onboarding metrics -- average time to complete, completion rates, and bottleneck steps -- so I can improve the new hire experience.

**Tool:** `get_onboarding_analytics`

**What it does:** Queries OnboardingAssignment records to compute completion rate, average time-to-complete, and identifies bottleneck steps with the lowest completion rates.

**Inputs:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| start_date | string (YYYY-MM-DD) | No | Start date for filtering assignments (default: 6 months ago) |
| end_date | string (YYYY-MM-DD) | No | End date (default: today) |

**Output:** JSON with: total_assignments, completed_count, in_progress_count, completion_rate_pct, avg_days_to_complete, bottleneck_steps, overdue_count.

**DB Models queried:** OnboardingAssignment, OnboardingStepAssignment

**Acceptance Criteria:**
- [ ] Completion rate = completed_count / total_assignments * 100
- [ ] Avg days to complete = average of (completed_at - started_at) for completed assignments
- [ ] Bottleneck steps are identified by finding OnboardingStepAssignment records with the lowest completion rate across all assignments
- [ ] Overdue count identifies assignments where at least one step is past its due_date and still pending
- [ ] All queries filter by tenant_id

**Priority:** P2
**Dependencies:** OnboardingAssignment model, OnboardingStepAssignment model
**Saudi-specific:** GOSI registration step completion rate should be highlighted as it is a legal requirement.

---

**Story A2-05: Payroll Cost Summary**
> As a CFO, I want to see total payroll costs by month, including breakdowns by department and cost category (basic, housing, transport, GOSI), so I can track our largest expense.

**Tool:** `get_payroll_summary` (replaces existing Norah generate_cost_report stub)

**What it does:** Sums Payslip records across the requested month range, broken down by category (basic, housing, transport, GOSI, other), department, and monthly trend.

**Inputs:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| department_id | string (UUID) | No | Filter to one department |
| start_month | string (YYYY-MM) | Yes | Start month |
| end_month | string (YYYY-MM) | Yes | End month |

**Output:** JSON with: total_gross, total_deductions, total_net, monthly_trend (array), category_breakdown, department_breakdown, avg_cost_per_employee, headcount_in_payroll.

**DB Models queried:** Payslip, Employee, Department

**Acceptance Criteria:**
- [ ] Totals are summed from Payslip records for the given month range
- [ ] Monthly trend shows each month's total gross, deductions, and net
- [ ] Category breakdown sums each Payslip column across all employees in scope
- [ ] Department breakdown joins Payslip -> Employee -> Department and groups accordingly
- [ ] Average cost per employee = total_gross / distinct employee count in payslips
- [ ] Currency is always SAR
- [ ] Multi-tenant isolation via tenant_id filter

**Priority:** P1
**Dependencies:** Payslip model, Employee model, Department model
**Saudi-specific:** GOSI deduction rates: 9.75% employer + 9.75% employee for Saudis; 2% employer for non-Saudis. The summary should note the GOSI split.

---

### A2 Coverage Matrix

| Capability | Story | Status |
|-----------|-------|--------|
| Recruitment funnel & pipeline metrics | A2-01 | Covered |
| Leave usage patterns & seasonality | A2-02 | Covered |
| Attendance & overtime analysis | A2-03 | Covered |
| Onboarding completion metrics | A2-04 | Covered |
| Payroll cost reporting | A2-05 | Covered |

**Total A2 tools: 5** (get_recruitment_analytics, get_leave_analytics, get_attendance_analytics, get_onboarding_analytics, get_payroll_summary)

---

## Phase A3: Predictive Intelligence + Governance Reports

### Epic: A3 -- Predictive Analytics, Compliance Governance & Advanced Reporting

---

**Story A3-01: Turnover Risk Scoring**
> As an HR director, I want to see which departments are at highest risk of attrition so I can intervene proactively.

**Tool:** `get_attrition_risk`

**What it does:** Computes a rule-based risk score per department using weighted factors: short tenure, salary stagnation, high overtime, low leave usage, and department turnover history. Returns department-level aggregates only (no individual names).

**Inputs:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| department_id | string (UUID) | No | Filter to one department |
| risk_threshold | enum: high, medium, all | No | Filter by risk level (default: all) |

**Output:** JSON with: department_risk_ranking (array of {dept, risk_score, risk_level, top_factors}), org_level_risk_score, key_risk_factors, at_risk_count_by_level.

**Calculation methodology (rule-based, not ML):**
Risk factors with weighted scoring:
- Tenure < 1 year AND probation complete: +15 points (early career flight risk)
- Tenure 1-2 years: +10 points (common churn window)
- No salary increase in 18+ months (if payslip history shows flat basic_salary): +20 points
- Department turnover > 15% annualized: +15 points (contagion risk)
- Overtime hours > 20/month average (from attendance): +10 points (burnout risk)
- Leave balance > 80% unused past mid-year: +5 points (disengagement signal)

Risk levels: High (>= 50 points), Medium (30-49), Low (< 30)

**DB Models queried:** Employee, Payslip, AttendanceRecord, LeaveBalance

**Acceptance Criteria:**
- [ ] Risk scores are computed per department (not per individual employee -- privacy)
- [ ] Each department result includes the top 3 contributing risk factors
- [ ] Org-level risk score is the weighted average across departments
- [ ] at_risk_count_by_level shows how many departments fall into each risk tier
- [ ] Tool does NOT expose individual employee names -- only department-level aggregates
- [ ] Response includes actionable recommendations (e.g., "Engineering has high overtime -- consider hiring to reduce workload")

**Priority:** P2
**Dependencies:** Employee, Payslip, AttendanceRecord, LeaveBalance models
**Saudi-specific:** For Saudization-critical roles, losing a Saudi employee has higher impact -- this should be noted in recommendations.

---

**Story A3-02: Budget Forecast**
> As a CFO, I want to see projected workforce costs for the rest of the year based on current spending trends so I can plan accordingly.

**Tool:** `get_budget_forecast`

**What it does:** Uses YTD payslip spend to project year-end totals under three scenarios (current trend, with open positions filled, conservative), and compares against department budgets.

**Inputs:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| department_id | string (UUID) | No | Filter to one department; omit for org-wide |
| fiscal_year | integer | No | Year to forecast (default: current year) |
| scenario | enum: current_trend, with_open_positions, conservative | No | Forecasting scenario (default: current_trend) |

**Output:** JSON with: ytd_spend, monthly_burn_rate, projected_annual_spend, budget_allocated, projected_variance, projected_variance_pct, scenario_details, monthly_forecast (remaining months with projected amounts), risk_assessment.

**Scenarios:**
- `current_trend`: Linear projection based on average monthly spend YTD
- `with_open_positions`: Adds estimated cost of filling open positions (from JobPosting salary ranges) over remaining months
- `conservative`: Uses the highest single month's spend as the projected rate

**DB Models queried:** Payslip, Department, JobPosting

**Acceptance Criteria:**
- [ ] YTD spend is computed from Payslip records for the current year
- [ ] Monthly burn rate = ytd_spend / months_elapsed (minimum 1 to avoid division by zero)
- [ ] with_open_positions scenario counts open JobPostings for the department, estimates monthly cost as avg(salary_min, salary_max), and adds proportional cost for remaining months
- [ ] Projected variance = projected_annual_spend - budget_allocated (negative means under budget)
- [ ] If fewer than 3 months of data exist, the response warns "Limited data -- forecast reliability is low"
- [ ] Risk assessment is: "on_track" if variance < 5%, "at_risk" if 5-15%, "over_budget" if > 15%

**Priority:** P2
**Dependencies:** Payslip model, Department model (cost_budget_sar), JobPosting model
**Saudi-specific:** GOSI employer contribution must be factored into new-hire cost estimates (12% for Saudis, 2% for non-Saudis).

---

**Story A3-03: GOSI Compliance Audit**
> As a compliance officer, I want to see which employees are not registered in GOSI so I can ensure full compliance with social insurance regulations.

**Tool:** `get_gosi_compliance`

**What it does:** Queries Employee.gosi_registered for all active employees, identifies those not yet registered, and computes the compliance rate. Cross-references with hire_date to flag employees who have been unregistered beyond the legal grace period.

**Inputs:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| department_id | string (UUID) | No | Filter to one department |

**Output:** JSON with: total_active_employees, gosi_registered_count, gosi_unregistered_count, compliance_rate_pct, overdue_registrations (employees hired > 15 days ago but not registered -- count and department breakdown, no names), saudi_vs_nonsaudi_breakdown, estimated_monthly_gosi_liability_sar.

**DB Models queried:** Employee, Department, Payslip (for salary-based GOSI calculation)

**Acceptance Criteria:**
- [ ] Compliance rate = gosi_registered_count / total_active_employees * 100
- [ ] Overdue registrations count employees where gosi_registered=false AND hire_date is more than 15 days ago
- [ ] Saudi vs. non-Saudi breakdown is included because GOSI rates differ (9.75% employer for Saudi, 2% employer for non-Saudi)
- [ ] Estimated monthly GOSI liability is calculated from salary_sar using the appropriate rates
- [ ] No employee names or IDs in output -- only aggregate counts by department
- [ ] All queries filter by tenant_id

**Priority:** P1
**Dependencies:** Employee model (gosi_registered, is_saudi, salary_sar, hire_date)
**Saudi-specific:** GOSI (General Organization for Social Insurance) registration is mandatory within 15 days of employment start. Rates: Saudi employees = 9.75% employee + 9.75% employer (of basic + housing); Non-Saudi = 2% employer only (occupational hazard insurance).

---

**Story A3-04: Policy Acknowledgment Tracker**
> As an HR director, I want to see which published policies have been acknowledged by all employees and which have gaps, so I can ensure everyone has read critical policies.

**Tool:** `get_policy_acknowledgment_status`

**What it does:** Queries published HRPolicy records and their corresponding PolicyAcknowledgment records, computes acknowledgment rate per policy, and identifies policies with low compliance.

**Inputs:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| policy_id | string (UUID) | No | Check a specific policy; omit for all published policies |
| department_id | string (UUID) | No | Filter acknowledgment data to a department |

**Output:** JSON with: total_published_policies, policies (array of {title, category, effective_date, total_employees, acknowledged_count, acknowledgment_rate_pct, outstanding_count}), overall_acknowledgment_rate, policies_below_threshold (policies with <80% acknowledgment).

**DB Models queried:** HRPolicy, PolicyAcknowledgment, Employee

**Acceptance Criteria:**
- [ ] Only published policies (status=published) are included
- [ ] Acknowledgment rate = acknowledged_count / total_active_employees * 100 (scoped to department if filtered)
- [ ] Outstanding count = total_active_employees - acknowledged_count
- [ ] Policies below 80% acknowledgment are flagged as needing attention
- [ ] If a department is specified, only employees in that department are checked
- [ ] No employee names -- only counts and rates
- [ ] All queries filter by tenant_id

**Priority:** P1
**Dependencies:** HRPolicy model, PolicyAcknowledgment model, Employee model
**Saudi-specific:** Labor law mandated policies (e.g., leave policy, workplace conduct) should be highlighted if their acknowledgment rate is below threshold.

---

**Story A3-05: Custom Report Generator**
> As an HR director, I want to ask for a custom report combining any metrics over a specific date range so I can answer ad-hoc questions from executives.

**Tool:** `generate_custom_report`

**What it does:** Accepts a list of metric categories, internally calls the corresponding analytics tools, and assembles a unified report with a report ID, timestamp, and Hijri date.

**Inputs:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| metrics | array of enum: headcount, saudization, turnover, budget, salary, leave, recruitment, attendance, payroll, compliance, gosi, policy_acknowledgment | Yes | Which metrics to include |
| department_id | string (UUID) | No | Filter to one department |
| start_date | string (YYYY-MM-DD) | No | Start date (default: start of current year) |
| end_date | string (YYYY-MM-DD) | No | End date (default: today) |

**Output:** JSON with: report_id, generated_at, generated_at_hijri, period, scope, sections (one per requested metric containing summary data).

**DB Models queried:** All models (delegates to individual tool functions)

**Acceptance Criteria:**
- [ ] Each requested metric section internally calls the corresponding analytics function (reuse A1/A2/A3 tool logic)
- [ ] Report includes a generated report_id and timestamp
- [ ] If a metric has no data, its section includes a "no_data" flag rather than failing the whole report
- [ ] Maximum 5 metrics per report request (to avoid timeout)
- [ ] Response is structured with clear section breaks so the LLM can format it as a comprehensive report
- [ ] Compliance and analytics metrics can be combined in a single report (this is the key advantage of merging Sarah and Norah)

**Priority:** P2
**Dependencies:** All A1, A2, and A3 tools
**Saudi-specific:** Report header includes Hijri date alongside Gregorian date for formal report use.

---

### A3 Coverage Matrix

| Capability | Story | Status |
|-----------|-------|--------|
| Attrition prediction / risk scoring | A3-01 | Covered |
| Budget forecasting & scenario planning | A3-02 | Covered |
| GOSI compliance audit | A3-03 | Covered |
| Policy acknowledgment governance | A3-04 | Covered |
| Custom ad-hoc reporting (analytics + compliance combined) | A3-05 | Covered |

**Total A3 tools: 5** (get_attrition_risk, get_budget_forecast, get_gosi_compliance, get_policy_acknowledgment_status, generate_custom_report)

---

## Full Tool Summary

| # | Tool Name | Phase | Replaces Stub? | Priority | Domain |
|---|-----------|-------|----------------|----------|--------|
| 1 | get_headcount_summary | A1 | No (new) | P0 | Analytics |
| 2 | get_saudization_status | A1 | No (new) | P0 | Analytics + Compliance |
| 3 | get_turnover_metrics | A1 | No (new) | P0 | Analytics |
| 4 | get_department_budget | A1 | Yes (Norah stub) | P0 | Analytics |
| 5 | get_salary_distribution | A1 | No (new) | P1 | Analytics |
| 6 | get_workforce_overview | A1 | Yes (Norah get_workforce_metrics) | P0 | Analytics |
| 7 | get_compliance_status | A1 | Yes (Sarah check_compliance_status) | P0 | Compliance |
| 8 | get_recruitment_analytics | A2 | No (new) | P1 | Analytics |
| 9 | get_leave_analytics | A2 | No (new) | P1 | Analytics |
| 10 | get_attendance_analytics | A2 | No (new) | P1 | Analytics |
| 11 | get_onboarding_analytics | A2 | No (new) | P2 | Analytics |
| 12 | get_payroll_summary | A2 | Yes (Norah generate_cost_report) | P1 | Analytics |
| 13 | get_attrition_risk | A3 | No (new) | P2 | Analytics |
| 14 | get_budget_forecast | A3 | No (new) | P2 | Analytics |
| 15 | get_gosi_compliance | A3 | No (new) | P1 | Compliance |
| 16 | get_policy_acknowledgment_status | A3 | No (new) | P1 | Compliance |
| 17 | generate_custom_report | A3 | No (new) | P2 | Both |

**Total: 17 tools** (4 stubs replaced, 13 new, 1 Sarah stub dropped [create_compliance_alert -- write operation], 1 Sarah stub absorbed into A3-05 [get_regulation_updates -- folded into compliance_status])

**Note on Sarah's dropped tools:**
- `create_compliance_alert` -- This is a write operation. Ahmad is read-only. Alert creation should be handled by an admin API or a future compliance-write agent.
- `get_regulation_updates` -- The concept of "regulation updates" is folded into `get_compliance_status` (A1-07) via the active_alerts field and upcoming_deadlines. If a dedicated regulation feed is needed in the future, it can be added as an A4 tool.

---

## Cross-Agent Dependencies

| Ahmad Tool | Depends On Agent/Data | Direction |
|-----------|----------------------|-----------|
| get_recruitment_analytics | Mohammad's pipeline data (JobPosting, Candidate, Interview) | Read-only |
| get_leave_analytics | Deema's leave data (LeaveRequest, LeaveBalance) | Read-only |
| get_onboarding_analytics | Waleed's onboarding data (OnboardingAssignment) | Read-only |
| get_budget_forecast | Mohammad's open positions (JobPosting) for scenario planning | Read-only |
| get_attrition_risk | Deema's leave + attendance data | Read-only |
| get_compliance_status | ComplianceRecord/Alert (written by admin or future compliance agent) | Read-only |
| get_policy_acknowledgment_status | HRPolicy + PolicyAcknowledgment (managed by Yara or admin) | Read-only |

Ahmad is a **read-only consumer** of all other agents' data. He never writes to any table. This makes him safe to implement in parallel with other agents since there are no write conflicts.

---

## Implementation Notes

### Agent Registration
When implementing Ahmad, the following changes are needed:
1. Create `/backend/app/agents/ahmad.py` with class `AhmadAgent(BaseAgent)`
2. Remove or deprecate `norah.py` and `sarah.py` (or keep them as aliases that redirect to Ahmad)
3. Update the agent registry to register Ahmad instead of Norah and Sarah
4. Map Ahmad's name/name_ar: "Ahmad" / "احمد"

### Query Patterns
All tools should follow the pattern established in Deema's implementation:
```python
from sqlalchemy import select, func
# Always filter by tenant_id
stmt = select(Employee).where(Employee.tenant_id == self.tenant_id)
result = await self.db.execute(stmt)
```

### Response Formatting
Ahmad's responses should be optimized for executive consumption:
- Lead with the headline metric (the one number that answers the question)
- Use clean JSON structures that the LLM can convert to readable tables
- Include both raw numbers and formatted strings (e.g., `"value": 342, "display": "342 employees"`)
- Percentages always include one decimal (e.g., 30.0, not 30)
- Currency amounts in SAR with thousand separators in display strings
- Trend indicators: include `change_pct` and `direction` ("up", "down", "flat") fields
- Risk labels: "green", "yellow", "red" where applicable
- When compliance and analytics data intersect, always surface the compliance angle (e.g., "headcount is 100, Saudization is 28%, which is 2% above the green_low threshold -- buffer is thin")

### Privacy
- Ahmad should NEVER return individual employee names, IDs, or salaries in analytics results
- All data is aggregated to department level or above
- Exception: the requesting user's own data (handled by Deema, not Ahmad)

### Performance
- For large tenants, analytics queries should use SQL aggregation (func.count, func.sum, func.avg) rather than loading all records into Python
- Consider adding database indexes on (tenant_id, department_id) for Employee and Payslip if query performance is slow
- The generate_custom_report tool should run metric queries in parallel where possible

### Testing
Each tool needs:
1. Unit test with seeded test data (at least 50 employees across 3 departments, mix of Saudi/non-Saudi, various statuses)
2. Multi-tenant isolation test (two tenants, verify no cross-contamination)
3. Edge case tests: empty tenant, single employee, all terminated, no payslips, no NitaqatConfig, no ComplianceRecords
4. Compliance-specific tests: overdue deadline detection, GOSI registration gap detection, Nitaqat band boundary edge cases

---

## Estimated Effort

| Phase | Stories | Tools | Estimated Sessions |
|-------|---------|-------|--------------------|
| A1 | 8 | 7 | 3-4 sessions |
| A2 | 5 | 5 | 2-3 sessions |
| A3 | 5 | 5 | 3-4 sessions |
| **Total** | **18** | **17** | **8-11 sessions** |

---

## Catalog Coverage Summary

| Catalog Role | Status After Ahmad Complete |
|-------------|----------------------------|
| People Analytics Agent | Covered by A1 + A2 |
| Predictive Workforce Intelligence Agent | Covered by A3-01, A3-02 |
| Workforce Budget & Planning Agent | Covered by A1-04, A2-05, A3-02 |
| HR ROI & Financial Analytics Agent | Covered by A3-05 (custom report) |
| Compliance Monitoring (from Sarah) | Covered by A1-07, A3-03, A3-04 |
| Regulatory Updates (from Sarah) | Absorbed into A1-07 (compliance_status) |
| Compliance Alert Creation (from Sarah) | **Dropped** -- Ahmad is read-only; alert creation moves to admin API |

All four Analytics & Finance catalog roles plus the Compliance monitoring role are addressed across the three phases. The merge consolidates 6 stub tools (3 Norah + 3 Sarah) into a unified 17-tool agent that serves the CHRO use case end-to-end.

---

## Migration Checklist

- [ ] Create `ahmad.py` agent file
- [ ] Update agent registry (replace norah + sarah with ahmad)
- [ ] Update frontend agent selector (name, avatar, description)
- [ ] Update system prompt references from "Norah" and "Sarah" to "Ahmad"
- [ ] Update any cross-agent routing rules that reference norah or sarah
- [ ] Preserve conversation history -- existing norah/sarah conversations should be attributed to ahmad
- [ ] Update API docs and agent catalog
