# Sprint 7 User Stories

**Author:** Tariq (Product Owner)
**Date:** 2026-03-28
**Sprint Duration:** 1 week
**Tracks:** Ahmad A2 Cross-Domain Analytics (5 tools) + Conversational UX Foundation (3 features)

---

## Track 1: Ahmad A2 -- Cross-Domain Analytics

### Epic: A2 -- Cross-Domain Analytics

Ahmad's A1 phase delivered 7 tools against Employee, Department, NitaqatConfig, ComplianceRecord/Alert, Payslip, and DeployedAgent models. A2 extends Ahmad into Mohammad's recruitment data, Deema's leave data, attendance records, onboarding assignments, and payroll cost summaries. All A2 tools follow the same patterns established in A1: tenant isolation, k-anonymity (MIN_GROUP_SIZE=5), JSON output, no individual names.

---

### Story A2-01: Recruitment Funnel Analytics

**ID:** S7-A2-01
**Title:** Recruitment Funnel Analytics Tool

> As an HR director, I want to see our recruitment pipeline metrics -- funnel conversion rates, time-to-fill, pipeline status, and average AI match scores -- so that I can identify bottlenecks in our hiring process and optimize conversion.

**Acceptance Criteria:**

- [ ] A new tool `get_recruitment_analytics` is added to `AhmadAgent.get_tools()` with parameters: `department_id` (optional UUID), `start_date` (optional, default 6 months ago), `end_date` (optional, default today)
- [ ] The tool queries `JobPosting`, `Candidate`, and `Interview` tables using the same tenant-isolation pattern as A1 tools (`JobPosting.tenant_id == self.tenant_id`)
- [ ] Funnel stages follow the `CandidateStage` enum order: applied -> screened -> shortlisted -> interview_scheduled -> interviewed -> offer_sent -> hired
- [ ] Conversion rate at each stage is computed as `count_at_stage / count_at_previous_stage * 100`, rounded to 1 decimal
- [ ] Candidates with stage `rejected` or `withdrawn` are excluded from the funnel pipeline counts but reported separately as `rejected_count` and `withdrawn_count`
- [ ] `open_positions` counts `JobPosting` records with `status == PostingStatus.open` for the tenant
- [ ] `avg_time_to_fill_days` is computed as the average number of days between `JobPosting.created_at` and the earliest `Candidate.created_at` where `stage == CandidateStage.hired` for the same posting, limited to postings within the date range
- [ ] `avg_ai_match_score` averages `Candidate.ai_match_score` where not NULL, for candidates within the date range
- [ ] When `department_id` is provided, all queries additionally filter `JobPosting.department_id == department_id`
- [ ] If no recruitment data exists for the period, the tool returns `{"message": "No recruitment data available for this period", "open_positions": 0}` rather than empty arrays or zeros
- [ ] Tenant isolation is enforced via `JobPosting.tenant_id` on all queries; `Candidate` isolation is through the `JobPosting` join since Candidate has no `tenant_id`
- [ ] No candidate names, emails, or phone numbers are included in the output -- only aggregate counts and averages
- [ ] The tool handles the `Interview` model for interview completion stats: count of completed interviews (`InterviewStatus.completed`) and average `overall_score`

**Data Dependencies:**
- `JobPosting` model (`/backend/app/models/candidate.py`) -- fields: `id`, `tenant_id`, `department_id`, `status`, `created_at`, `salary_min_sar`, `salary_max_sar`
- `Candidate` model (`/backend/app/models/candidate.py`) -- fields: `id`, `job_posting_id`, `stage`, `ai_match_score`, `created_at`
- `Interview` model (`/backend/app/models/interview.py`) -- fields: `id`, `tenant_id`, `candidate_id`, `job_posting_id`, `status`, `overall_score`, `completed_at`

**Edge Cases:**
- JobPosting exists but has zero candidates: show the posting in open_positions, funnel shows 0 at all stages
- Multiple candidates reach `hired` for the same posting: time-to-fill uses the earliest hire
- `start_date` > `end_date`: return validation error
- Posting has candidates in the date range but was created before `start_date`: include (filter is on candidate.created_at)
- Division by zero in conversion rate when a stage has 0 candidates: report 0% and note the gap

**Saudi-specific:**
- Positions that are Saudization-mandatory (determined by cross-referencing with NitaqatConfig requirements) should be flaggable in a future iteration but are out of scope for A2-01
- No Hajj-season hiring freeze logic needed at the analytics level

**Priority:** P1
**Dependencies:** A1 tools complete (done), Candidate/JobPosting/Interview models (exist)

---

### Story A2-02: Leave Usage Analytics

**ID:** S7-A2-02
**Title:** Leave Usage Analytics Tool

> As an HR director, I want to see leave usage patterns -- total days taken by type, department comparisons, monthly distribution, and utilization rates -- so that I can plan coverage and identify absence trends.

**Acceptance Criteria:**

- [ ] A new tool `get_leave_analytics` is added to `AhmadAgent.get_tools()` with parameters: `department_id` (optional UUID), `year` (optional integer, default current year), `leave_type` (optional string matching `LeaveType` enum)
- [ ] The tool queries `LeaveRequest`, `LeaveBalance`, `Employee`, and `Department` tables
- [ ] Only `LeaveRequest` records with `status == LeaveStatus.approved` are counted in usage totals
- [ ] `total_leave_days_taken` is the sum of `LeaveRequest.business_days` for approved requests in the given year
- [ ] `by_type` returns an array of `{leave_type, total_days, request_count}` sorted by `total_days` descending
- [ ] `by_department` returns an array of `{department_name, total_days, employee_count, avg_days_per_employee}` -- the `avg_days_per_employee` normalizes for team size to enable fair comparison
- [ ] `monthly_pattern` returns all 12 months (January through December), each with `{month, month_name, days}`, using 0 for months with no leave data
- [ ] `utilization_rate` is computed from `LeaveBalance` as `SUM(used_days) / SUM(total_days) * 100` for the given year, filtered by the `LeaveType` if specified
- [ ] `pending_requests_count` includes all `LeaveRequest` records with `status == LeaveStatus.pending` (regardless of year filter) for operational awareness
- [ ] When `leave_type` is provided, all aggregations filter to that specific leave type
- [ ] Tenant isolation is enforced by joining through `Employee.tenant_id == self.tenant_id` (neither `LeaveRequest` nor `LeaveBalance` has a direct `tenant_id`)
- [ ] If the year is the current year and fewer than 3 months have data, the response includes a note: `"partial_year": true`
- [ ] k-anonymity: if a department has fewer than `MIN_GROUP_SIZE` (5) employees, its leave data is rolled into an "Other" category rather than shown individually

**Data Dependencies:**
- `LeaveRequest` model (`/backend/app/models/leave.py`) -- fields: `employee_id`, `leave_type`, `start_date`, `end_date`, `business_days`, `status`
- `LeaveBalance` model (`/backend/app/models/leave.py`) -- fields: `employee_id`, `leave_type`, `year`, `total_days`, `used_days`
- `Employee` model (`/backend/app/models/employee.py`) -- fields: `id`, `tenant_id`, `department_id`
- `Department` model (`/backend/app/models/employee.py`) -- fields: `id`, `name`

**Edge Cases:**
- Employee has leave requests spanning two years (start_date in December, end_date in January): attribute to the year of `start_date` to match existing Deema behavior
- `year` is in the future: return `{"message": "No leave data available for future year YYYY"}`
- A leave type has zero balance allocated (total_days=0): skip from utilization rate to avoid division by zero
- Employee terminated mid-year: their approved leave before termination still counts in analytics

**Saudi-specific:**
- Hajj leave (`LeaveType.hajj`) usage should be highlighted separately in the response since it is a one-time entitlement under Saudi Labor Law Article 47 (10 days, once during employment)
- Ramadan period (varies by Hijri calendar, typically months 8-9 of Hijri year) absence patterns are valuable -- the tool should tag months that overlap with Ramadan if possible (future enhancement note)
- Eid al-Fitr and Eid al-Adha holidays may create spikes in leave requests immediately before/after; the monthly pattern will naturally surface this

**Priority:** P1
**Dependencies:** A1 tools complete (done), LeaveRequest/LeaveBalance models (exist, used by Deema)

---

### Story A2-03: Attendance and Overtime Analytics

**ID:** S7-A2-03
**Title:** Attendance and Overtime Analytics Tool

> As a department manager, I want to see attendance rates, late arrival rates, absence rates, and overtime trends so that I can identify workload imbalances and attendance problems.

**Acceptance Criteria:**

- [ ] A new tool `get_attendance_analytics` is added to `AhmadAgent.get_tools()` with parameters: `department_id` (optional UUID), `start_date` (optional, default first day of current month), `end_date` (optional, default today)
- [ ] The tool queries `AttendanceRecord`, `WorkSchedule`, `Employee`, and `Department` tables
- [ ] `attendance_rate_pct` = count of records with `status` in (`present`, `late`, `half_day`) / total working-day records * 100
- [ ] `late_rate_pct` = count of records with `status == AttendanceStatus.late` / total working-day records * 100
- [ ] `absent_rate_pct` = count of records with `status == AttendanceStatus.absent` / total working-day records * 100
- [ ] Records with `status` in (`weekend`, `holiday`, `on_leave`) are excluded from rate denominators -- they are non-working days
- [ ] `total_overtime_hours` sums `AttendanceRecord.overtime_hours` across all employees and dates in range
- [ ] `avg_overtime_per_employee` = `total_overtime_hours` / distinct employee count with attendance records in the range
- [ ] `department_comparison` returns an array of `{department_name, attendance_rate_pct, late_rate_pct, overtime_hours}` ranked by `attendance_rate_pct` descending
- [ ] `daily_pattern` returns average attendance rate per day of week, using ISO day numbers mapped to labels: 0=Sunday through 4=Thursday for the standard Saudi work week (Friday/Saturday excluded as weekend)
- [ ] `top_overtime_departments` lists the 3 departments with highest total overtime hours
- [ ] Tenant isolation via `AttendanceRecord.tenant_id == self.tenant_id`
- [ ] k-anonymity: departments with fewer than MIN_GROUP_SIZE employees are aggregated into "Other"
- [ ] No individual employee attendance records are returned -- only department-level aggregates

**Data Dependencies:**
- `AttendanceRecord` model (`/backend/app/models/attendance.py`) -- fields: `tenant_id`, `employee_id`, `date`, `status`, `overtime_hours`, `check_in`, `check_out`
- `AttendanceStatus` enum: `present`, `absent`, `late`, `half_day`, `on_leave`, `holiday`, `weekend`
- `WorkSchedule` model (`/backend/app/models/attendance.py`) -- fields: `tenant_id`, `work_days` (CSV ints), `work_start`, `work_end`, `late_threshold_minutes`
- `Employee`, `Department` models

**Edge Cases:**
- No attendance records exist for the date range: return `{"message": "No attendance records found for this period"}`
- Employee has no check_in/check_out but has a status record (manual entry via `source="manual"`): still counted
- Date range spans a public holiday: those records have `status=holiday` and are already excluded from rate denominators
- `start_date` == `end_date` (single day query): valid, compute for that one day
- An employee has multiple records for the same date: the unique constraint `uq_attendance_employee_date` prevents this at the DB level

**Saudi-specific:**
- Saudi weekend is Friday-Saturday (`work_days` default "0,1,2,3,4" maps to Sun-Thu). The `daily_pattern` output should use day names appropriate to Saudi context: Sunday, Monday, Tuesday, Wednesday, Thursday
- During Ramadan, working hours are reduced to 6 hours/day by Saudi Labor Law Article 98. Overtime calculations during Ramadan should note this if `WorkSchedule` has a Ramadan schedule active (the `work_end` would be earlier). The tool should include a `ramadan_note` if the date range includes Ramadan-schedule days
- Overtime exceeding 720 hours/year per employee is a Saudi Labor Law violation (Article 107) -- the tool should flag if any department is on pace to exceed this annualized threshold

**Priority:** P1
**Dependencies:** A1 tools complete (done), AttendanceRecord/WorkSchedule models (exist)

---

### Story A2-04: Onboarding Completion Analytics

**ID:** S7-A2-04
**Title:** Onboarding Completion Analytics Tool

> As an HR director, I want to see onboarding metrics -- completion rates, average time to complete, bottleneck steps, and overdue items -- so that I can improve the new hire experience and ensure compliance steps are done on time.

**Acceptance Criteria:**

- [ ] A new tool `get_onboarding_analytics` is added to `AhmadAgent.get_tools()` with parameters: `start_date` (optional, default 6 months ago), `end_date` (optional, default today)
- [ ] The tool queries `OnboardingAssignment`, `OnboardingStepAssignment`, and `OnboardingTemplateStep` tables
- [ ] `total_assignments` counts all `OnboardingAssignment` records for the tenant where `started_at` falls within the date range
- [ ] `completed_count` counts assignments with `status == OnboardingAssignmentStatus.completed`
- [ ] `in_progress_count` counts assignments with `status == OnboardingAssignmentStatus.in_progress`
- [ ] `completion_rate_pct` = `completed_count / total_assignments * 100`, rounded to 1 decimal
- [ ] `avg_days_to_complete` is the average of `(completed_at - started_at)` in days for completed assignments, rounded to 1 decimal
- [ ] `bottleneck_steps` identifies the 3 `OnboardingStepAssignment` template steps with the lowest completion rate (completed / total for that step across all assignments), including the step name from `OnboardingTemplateStep`
- [ ] `overdue_count` counts `OnboardingStepAssignment` records where `status == OnboardingStepStatus.pending` AND `due_date < now()`
- [ ] `overdue_steps` lists the top 5 overdue steps with `{step_name, overdue_count, avg_days_overdue}`
- [ ] Tenant isolation via `OnboardingAssignment.tenant_id == self.tenant_id`
- [ ] Cancelled assignments (`status == OnboardingAssignmentStatus.cancelled`) are excluded from all metrics
- [ ] If no onboarding data exists, return `{"message": "No onboarding assignments found for this period"}`

**Data Dependencies:**
- `OnboardingAssignment` model (`/backend/app/models/onboarding.py`) -- fields: `tenant_id`, `employee_id`, `template_id`, `status`, `started_at`, `completed_at`
- `OnboardingStepAssignment` model (`/backend/app/models/onboarding.py`) -- fields: `assignment_id`, `template_step_id`, `status`, `due_date`, `completed_at`, `order`
- `OnboardingTemplateStep` model (`/backend/app/models/onboarding.py`) -- fields: `id`, `template_id`, `name`, `name_ar`, `step_type`, `is_required`, `due_days_after_hire`
- `OnboardingAssignmentStatus` enum: `in_progress`, `completed`, `cancelled`
- `OnboardingStepStatus` enum: `pending`, `in_progress`, `completed`, `skipped`

**Edge Cases:**
- Assignment has no `completed_at` despite `status==completed`: skip from avg_days calculation and log warning
- All steps for an assignment are `skipped`: the assignment itself may still be `in_progress` -- do not count as completed
- `due_date` is NULL for a step: that step cannot be overdue, exclude from overdue calculations
- Template step was deleted after assignments were created: join gracefully handles missing template step (use outer join or handle None)
- Date range captures zero completed assignments: `avg_days_to_complete` should be `null` not 0

**Saudi-specific:**
- GOSI registration is a legal requirement that must be completed within the first month of employment. The tool should specifically flag the GOSI registration step completion rate if a step with `auto_trigger` containing "gosi" exists -- include it as `gosi_registration_completion_rate` in the response
- Iqama (residency permit) processing for non-Saudi employees is a common onboarding bottleneck -- if such a step exists, it should surface in bottleneck_steps naturally

**Priority:** P2
**Dependencies:** A1 tools complete (done), Onboarding models (exist, used by Waleed)

---

### Story A2-05: Payroll Cost Summary

**ID:** S7-A2-05
**Title:** Payroll Cost Summary Tool

> As a CFO, I want to see total payroll costs by month, including breakdowns by department and cost category (basic, housing, transport, GOSI), so that I can track our largest expense and identify cost trends.

**Acceptance Criteria:**

- [ ] A new tool `get_payroll_summary` is added to `AhmadAgent.get_tools()` with parameters: `department_id` (optional UUID), `start_month` (required, format "YYYY-MM"), `end_month` (required, format "YYYY-MM")
- [ ] The tool queries `Payslip`, `Employee`, and `Department` tables
- [ ] `total_gross` sums `Payslip.gross_salary` across all employees and months in the range
- [ ] `total_deductions` sums `Payslip.total_deductions`
- [ ] `total_net` sums `Payslip.net_salary`
- [ ] `category_breakdown` returns sums for each payslip column: `basic_salary`, `housing_allowance`, `transport_allowance`, `other_allowances`, `gosi_employee`, `absent_deduction`, `other_deductions`
- [ ] `monthly_trend` returns an array of `{year, month, gross, deductions, net, headcount}` ordered chronologically, one entry per month in the range
- [ ] `department_breakdown` returns an array of `{department_name, gross, headcount, avg_cost_per_employee}` sorted by `gross` descending
- [ ] `avg_cost_per_employee` = `total_gross / COUNT(DISTINCT employee_id in payslips)`
- [ ] `headcount_in_payroll` = `COUNT(DISTINCT Payslip.employee_id)` across all months in range
- [ ] When `department_id` is provided, all queries additionally filter through `Employee.department_id == department_id` (via Payslip -> Employee join)
- [ ] Tenant isolation via `Payslip.tenant_id == self.tenant_id`
- [ ] Month range parsing: "2026-01" maps to `year=2026, month=1`. If `start_month` > `end_month`, return validation error
- [ ] All monetary values are in SAR (integer, no decimals, matching Payslip model)
- [ ] If no payslips exist for the range, return `{"message": "No payroll data available for the specified period"}`

**Data Dependencies:**
- `Payslip` model (`/backend/app/models/payslip.py`) -- fields: `tenant_id`, `employee_id`, `year`, `month`, `basic_salary`, `housing_allowance`, `transport_allowance`, `other_allowances`, `gosi_employee`, `absent_deduction`, `other_deductions`, `gross_salary`, `total_deductions`, `net_salary`
- `Employee` model -- fields: `id`, `department_id`, `is_saudi`
- `Department` model -- fields: `id`, `name`

**Edge Cases:**
- Employee transferred departments mid-period: their payslips attribute to whatever department they were in at the time (via current `Employee.department_id`). This is a known approximation; historical department tracking is out of scope
- `start_month` == `end_month` (single month query): valid, returns one-month summary
- Employee has payslip in month but was terminated before month-end: the payslip record still counts (final settlement)
- A month in the range has zero payslips (e.g., new company, payroll not yet run): include that month in `monthly_trend` with all zeros rather than omitting it
- Extremely large payroll (1000+ employees): the query groups at DB level, no per-row Python processing needed

**Saudi-specific:**
- GOSI deduction rates: employer contributes 11.75% (9.75% pension + 2% SANED) for Saudi employees; 2% for non-Saudi employees. The tool should include a `gosi_breakdown` section that separates Saudi vs non-Saudi GOSI totals by joining with `Employee.is_saudi`
- WPS (Wage Protection System) compliance requires that salaries be transferred through approved banks. The payroll summary implicitly supports WPS auditing by providing per-month totals that can be reconciled against bank transfers
- All amounts are in SAR. The tool should include `currency: "SAR"` in the response for clarity

**Priority:** P1
**Dependencies:** A1 tools complete (done), Payslip model (exists, used by A1-04 get_department_budget)

---

### Story A2-06: Ahmad A2 Tool Registration and Orchestrator Keywords

**ID:** S7-A2-06
**Title:** Register A2 Tools and Update Orchestrator Keywords

> As the system, Ahmad's A2 tools must be registered in `get_tools()` and the orchestrator keywords must be updated so that user messages about recruitment analytics, leave analytics, attendance, onboarding metrics, and payroll summaries route correctly to Ahmad.

**Acceptance Criteria:**

- [ ] `AhmadAgent.get_tools()` returns 12 tools total (7 A1 + 5 A2)
- [ ] `handle_tool_call()` dispatches all 5 new tool names to their respective private methods
- [ ] Each A2 tool's `input_schema` matches the parameters defined in stories A2-01 through A2-05
- [ ] The orchestrator's `INTENT_KEYWORDS["ahmad"]` list includes the new A2-specific keywords: `"recruitment analytics"`, `"leave analytics"`, `"attendance analytics"`, `"onboarding analytics"`, `"payroll summary"`, `"funnel"`, `"time to fill"`, `"overtime"`, `"absence rate"`, `"payroll cost"`, and Arabic equivalents: `"تحليل التوظيف"`, `"تحليل الإجازات"`, `"تحليل الحضور"`, `"تأهيل الموظفين"`, `"ملخص الرواتب"`
- [ ] No keyword conflicts with other agents: "recruitment" alone still routes to Mohammad (for recruitment actions), but "recruitment analytics" routes to Ahmad (for reporting). "leave" alone still routes to Deema, but "leave analytics" routes to Ahmad
- [ ] All 5 new tool methods are `async` and accept `(self, tool_input: dict) -> str` following the A1 pattern
- [ ] All 5 new tool methods return `json.dumps(...)` result, consistent with A1 tools
- [ ] Error handling follows the same pattern as A1: individual tool errors return `{"error": "..."}` and are logged

**Priority:** P0 (blocks all other A2 stories)
**Dependencies:** A1 implementation complete

---

### A2 Coverage Matrix

| Capability (from catalog/plan) | Story | Status |
|-------------------------------|-------|--------|
| Recruitment funnel conversion rates | S7-A2-01 | Covered |
| Time-to-fill metrics | S7-A2-01 | Covered |
| Pipeline status (open positions) | S7-A2-01 | Covered |
| AI match score analytics | S7-A2-01 | Covered |
| Leave usage by type | S7-A2-02 | Covered |
| Leave department comparison | S7-A2-02 | Covered |
| Leave seasonal/monthly patterns | S7-A2-02 | Covered |
| Leave utilization rate | S7-A2-02 | Covered |
| Attendance rate analytics | S7-A2-03 | Covered |
| Late arrival rate | S7-A2-03 | Covered |
| Overtime trends | S7-A2-03 | Covered |
| Day-of-week attendance pattern | S7-A2-03 | Covered |
| Onboarding completion rates | S7-A2-04 | Covered |
| Onboarding bottleneck steps | S7-A2-04 | Covered |
| Overdue onboarding items | S7-A2-04 | Covered |
| Monthly payroll cost trends | S7-A2-05 | Covered |
| GOSI breakdown (Saudi vs non-Saudi) | S7-A2-05 | Covered |
| Department cost comparison | S7-A2-05 | Covered |
| Tool registration & routing | S7-A2-06 | Covered |

---

## Track 2: Conversational UX Foundation

### Epic: CUX -- Conversational UX Foundation

Three features that improve the chat experience: contextual suggestions on load, follow-up chips after agent responses, and a role-based quick actions bar. These are independent of any specific agent and apply across all agents.

---

### Story CUX-01: Context-Aware Smart Suggestions API

**ID:** S7-CUX-01
**Title:** Context-Aware Smart Suggestions Endpoint

> As an employee opening the chat UI, I want to see 3-5 personalized suggestions based on my role, the time of day, and any pending items, so that I can quickly take action without needing to know what to ask.

**Acceptance Criteria:**

- [ ] A new endpoint `GET /api/v1/suggestions` is created, accepting query parameter `employee_id` (UUID)
- [ ] The endpoint requires authentication (uses `get_chat_employee` dependency, same as chat endpoint)
- [ ] The endpoint returns a JSON array of 3-5 suggestion objects, each with: `text_en` (string), `text_ar` (string), `agent` (string -- the target agent), `message` (string -- the pre-formed message to send)
- [ ] Suggestions are rule-based (no ML), using the following signals:
  - **Time of day (AST, UTC+3):** Morning (6-12) suggests attendance/check-in related items; Afternoon (12-17) suggests leave/balance items; Evening (17+) suggests next-day prep items
  - **Employee role:** `hr_admin` and `executive` roles see Ahmad analytics suggestions; `manager` roles see team-related suggestions (Waleed); regular `employee` roles see Deema self-service suggestions
  - **Pending leave requests:** If employee has `LeaveRequest` with `status==pending`, include "Check leave request status" suggestion
  - **Pending onboarding steps:** If employee has in-progress `OnboardingAssignment`, include "View onboarding progress" suggestion
  - **Upcoming leave:** If employee has approved leave starting within 7 days, include "View upcoming leave details"
  - **Pay period:** If current date is between 25th-31st of the month, include "View latest payslip"
- [ ] Every suggestion has both English and Arabic text
- [ ] Suggestions are deduplicated -- no two suggestions have the same `message`
- [ ] The endpoint respects rate limiting (reuse `check_chat_rate_limit`)
- [ ] If the employee has no contextual signals, fall back to a default set appropriate for their role
- [ ] Response time target: under 200ms (queries should be lightweight)

**Data Dependencies:**
- `Employee` model -- fields: `id`, `role` (or title/position for role inference), `preferred_language`
- `LeaveRequest` model -- for pending/upcoming checks
- `OnboardingAssignment` model -- for in-progress checks
- Current date/time in AST (UTC+3)

**Edge Cases:**
- Employee has no leave balances, no onboarding, no pending items: return role-based defaults only
- Employee's preferred language is Arabic: `text_ar` should be listed first in the array (for UI to pick primary display)
- Employee is brand new (first day): prioritize onboarding suggestions
- Weekend (Friday/Saturday): suppress attendance-related suggestions, prioritize informational ones
- Employee is on leave: suppress "check-in" type suggestions

**Saudi-specific:**
- Time zone is always AST (Arabia Standard Time, UTC+3) regardless of server timezone
- Saudi weekend is Friday-Saturday; time-based suggestions should account for this (no "check attendance" suggestions on Friday)
- During Ramadan, working hours shift; morning suggestions should adjust if a Ramadan schedule is active
- Bilingual output is mandatory -- every suggestion includes both `text_en` and `text_ar`

**Priority:** P1
**Dependencies:** Auth system (exists), Employee model (exists), LeaveRequest model (exists)

---

### Story CUX-02: Follow-Up Chips in Agent Responses

**ID:** S7-CUX-02
**Title:** Follow-Up Suggestion Chips in ChatResponse

> As an employee who just received an agent response, I want to see 2-3 follow-up action suggestions as clickable chips below the response, so that I can continue the conversation naturally without having to formulate the next question.

**Acceptance Criteria:**

- [ ] The `ChatResponse` Pydantic model in `/backend/app/api/chat.py` is extended with a new field: `suggestions: list[str] = []`
- [ ] The field is optional and defaults to an empty list for backward compatibility
- [ ] `BaseAgent` (in `/backend/app/agents/base.py`) gains a new helper method `_generate_follow_ups(self, tool_name: str, tool_result: dict, language: str) -> list[str]` that returns 2-3 contextual follow-up suggestions
- [ ] Each agent can override `_generate_follow_ups` to provide domain-specific suggestions
- [ ] The orchestrator populates `ChatResponse.suggestions` from the agent's follow-up method after generating the main response
- [ ] Suggestions are in the employee's preferred language (if `language == "ar"`, suggestions are in Arabic; otherwise English)
- [ ] Each suggestion is a short natural-language phrase (under 50 characters) that can be sent directly as the next chat message
- [ ] Ahmad's follow-ups after analytics tools suggest drill-downs: e.g., after `get_headcount_summary` -> ["Show Saudization status", "Show turnover metrics", "Break down by department"]
- [ ] Deema's follow-ups after leave balance -> ["Request annual leave", "Show leave policy", "Check my payslip"]
- [ ] The existing client-side `extractSuggestions` function in `chat.html` already parses numbered suggestions from agent response text. The new `suggestions` field in `ChatResponse` should be the **preferred source** -- if `suggestions` is non-empty in the API response, the frontend uses it directly instead of parsing from text
- [ ] Frontend `chat.html` is updated: after rendering an agent message, if `data.suggestions` array is non-empty, render suggestion chips from that array (same UI as current `msg-suggestions` div)

**Data Dependencies:**
- `ChatResponse` model in `/backend/app/api/chat.py`
- `BaseAgent` class in `/backend/app/agents/base.py`
- `chat.html` frontend suggestion rendering (lines ~2030-2040)

**Edge Cases:**
- Agent response is an error message: return empty suggestions (do not suggest follow-ups after errors)
- Agent redirected to another agent: suggestions should be in the context of the new agent, not the original
- Conversation is escalated: no suggestions (human is handling)
- Agent response did not use any tool (pure conversational response): provide generic suggestions based on agent domain
- `suggestions` field missing from API response (older clients): frontend falls back to text parsing (backward compatible)

**Saudi-specific:**
- Arabic suggestions should be natural phrases, not word-for-word translations: e.g., "اعرض رصيد إجازاتي" not "عرض رصيد الإجازة الخاص بي"
- Suggestions involving Saudization or GOSI should use the common Arabic terms: "نطاقات" for Nitaqat, "التأمينات" for GOSI

**Priority:** P1
**Dependencies:** BaseAgent (exists), ChatResponse model (exists), chat.html (exists)

---

### Story CUX-03: Quick Actions Bar

**ID:** S7-CUX-03
**Title:** Role-Based Quick Actions Bar

> As an employee, I want to see a persistent row of 4-5 quick action buttons above the text input, personalized to my role, so that I can perform common tasks with a single tap.

**Acceptance Criteria:**

- [ ] The existing quick actions bar in `chat.html` (line ~1489, currently hardcoded with 4 Deema-focused buttons) is replaced with a dynamic, role-based implementation
- [ ] A new endpoint `GET /api/v1/quick-actions?employee_id=...` returns the appropriate quick actions for the authenticated employee's role
- [ ] The endpoint returns a JSON array of 4-5 action objects: `{id, label_en, label_ar, icon, message, agent}`
- [ ] Role-based defaults:
  - **employee:** "Leave Balance" (Deema), "Request Leave" (Deema), "My Info" (Deema), "Company Policy" (Deema), "My Payslip" (Deema)
  - **manager:** "Team Overview" (Waleed), "Pending Approvals" (Waleed), "Leave Balance" (Deema), "Department Budget" (Ahmad), "Team Attendance" (Ahmad)
  - **hr_admin:** "Workforce Overview" (Ahmad), "Compliance Status" (Ahmad), "Open Positions" (Mohammad), "Pending Requests" (Deema), "Onboarding Status" (Ahmad)
  - **executive:** "Executive Summary" (Ahmad), "Saudization Status" (Ahmad), "Budget Overview" (Ahmad), "Turnover Report" (Ahmad), "Recruitment Pipeline" (Ahmad)
- [ ] Each action has a `message` field containing the pre-formed chat message that is sent when the button is tapped
- [ ] Each action has an `agent` field so the UI can send `req.agent` along with the message for direct routing
- [ ] The frontend renders quick actions dynamically from the API response instead of using hardcoded HTML
- [ ] Quick actions bar is visible when no conversation is active (welcome screen) and after a conversation is resolved
- [ ] Quick actions bar hides once the user starts typing or the first message is sent (current behavior preserved)
- [ ] Actions are bilingual: the UI displays `label_en` or `label_ar` based on the employee's preferred language
- [ ] Tapping a quick action calls `sendQuickMessage(action.message)` with the agent pre-set (existing function pattern)
- [ ] The endpoint requires authentication and enforces tenant isolation

**Data Dependencies:**
- `Employee` model -- fields: `id`, `role` (currently the system uses `job_title` or a role field; if no explicit role field exists, derive from employee metadata)
- Note: The current `Employee` model may not have an explicit `role` field for "employee/manager/hr_admin/executive". If this is the case, the initial implementation can use a simple heuristic: check if employee has any `reports_to` relationships (manager), check `job_title` for keywords like "director", "CEO", "VP" (executive), or check a department name for "HR" (hr_admin). A dedicated role field can be added in a future sprint.

**Edge Cases:**
- Employee role cannot be determined: fall back to "employee" defaults
- Employee has a custom role not in the four categories: fall back to "employee" defaults
- Quick actions endpoint returns an error: frontend should gracefully fall back to hardcoded defaults (never show an empty bar)
- Employee is mid-onboarding: add "Onboarding Progress" as the first quick action regardless of role

**Saudi-specific:**
- Icons should be culturally appropriate (no alcohol, pork, or culturally insensitive imagery -- current icons use neutral emojis which is fine)
- Arabic labels should be natural and concise: "رصيد الإجازات" not "التحقق من رصيد الإجازات المتبقي لديك"
- Manager role should see Saudization-related actions if their department is in a Nitaqat risk zone (future enhancement, not required for initial implementation)

**Priority:** P2
**Dependencies:** Auth system (exists), Employee model (exists), chat.html quick actions UI (exists but hardcoded)

---

### CUX Coverage Matrix

| Capability | Story | Status |
|-----------|-------|--------|
| Context-aware suggestions on load | S7-CUX-01 | Covered |
| Time-of-day signal | S7-CUX-01 | Covered |
| Role-based signal | S7-CUX-01 | Covered |
| Pending items signal | S7-CUX-01 | Covered |
| Bilingual suggestions | S7-CUX-01 | Covered |
| Follow-up chips in ChatResponse | S7-CUX-02 | Covered |
| BaseAgent follow-up helper | S7-CUX-02 | Covered |
| Per-agent follow-up overrides | S7-CUX-02 | Covered |
| Frontend chip rendering from API | S7-CUX-02 | Covered |
| Persistent quick actions bar | S7-CUX-03 | Covered |
| Role-based action sets | S7-CUX-03 | Covered |
| Dynamic API-driven rendering | S7-CUX-03 | Covered |
| Bilingual action labels | S7-CUX-03 | Covered |

---

## Sprint 7 Summary

| Story ID | Title | Track | Priority | Est. Complexity |
|----------|-------|-------|----------|----------------|
| S7-A2-06 | Tool Registration & Keywords | Ahmad A2 | P0 | Small |
| S7-A2-01 | Recruitment Funnel Analytics | Ahmad A2 | P1 | Medium |
| S7-A2-02 | Leave Usage Analytics | Ahmad A2 | P1 | Medium |
| S7-A2-03 | Attendance & Overtime Analytics | Ahmad A2 | P1 | Medium |
| S7-A2-04 | Onboarding Completion Analytics | Ahmad A2 | P2 | Medium |
| S7-A2-05 | Payroll Cost Summary | Ahmad A2 | P1 | Medium |
| S7-CUX-01 | Smart Suggestions API | UX Foundation | P1 | Medium |
| S7-CUX-02 | Follow-Up Chips | UX Foundation | P1 | Small-Medium |
| S7-CUX-03 | Quick Actions Bar | UX Foundation | P2 | Small-Medium |

**Implementation order recommendation:**
1. S7-A2-06 (P0, unblocks all A2 tools)
2. S7-CUX-02 (P1, small scope, touches BaseAgent which A2 tools will use)
3. S7-A2-02 + S7-A2-03 (P1, can be parallelized -- independent data domains)
4. S7-A2-01 + S7-A2-05 (P1, can be parallelized)
5. S7-CUX-01 (P1, independent of agent tools)
6. S7-A2-04 + S7-CUX-03 (P2, lowest priority)

**Cross-agent dependencies:**
- A2 tools read from models owned by other agents (Mohammad: JobPosting/Candidate, Deema: LeaveRequest/LeaveBalance, Waleed: OnboardingAssignment) but are read-only. No write conflicts.
- CUX-02 modifies BaseAgent which is the parent class of all agents. Changes must be backward-compatible (default empty list).
- CUX-01 and CUX-03 create new API endpoints that are independent of existing endpoints.
