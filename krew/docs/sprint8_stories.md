# Sprint 8 User Stories

**Author:** Tariq (Product Owner)
**Date:** 2026-03-30
**Sprint Duration:** 1 week
**Tracks:**
1. Ahmad A3 -- Predictive Analytics (5 tools)
2. Dynamic Quick Actions (per-agent switching)
3. Knowledge Management Module (data model, ingestion, scoped RAG, admin API, upload UI)
4. Ahmad English-only responses

---

## Track 1: Ahmad A3 -- Predictive Analytics

### Epic: A3 -- Predictive & Advanced Analytics

Ahmad's A1 delivered 7 core HR metrics tools. A2 delivered 5 cross-domain analytics tools (recruitment, leave, attendance, onboarding, payroll). A3 adds 5 predictive and advanced tools: attrition risk scoring, budget forecasting, GOSI compliance auditing, policy acknowledgment tracking, and natural-language custom reports. All A3 tools follow the same patterns established in A1/A2: tenant isolation via `self.tenant_id`, k-anonymity (`MIN_GROUP_SIZE=5`), JSON output, no individual names in aggregated results. Tools are added to `AhmadAgent.get_tools()` in `/backend/app/agents/ahmad.py` and dispatched via `handle_tool_call()`.

---

### Story A3-01: Attrition Risk Prediction

**ID:** S8-A3-01
**Title:** Predict Employee/Department Attrition Risk

> As a CHRO, I want to see flight-risk scores for departments and optionally individual employees so that I can prioritize retention interventions before losing key talent.

**Tool Definition:**

```json
{
  "name": "predict_attrition_risk",
  "description": "Score employees or departments on attrition (flight) risk using tenure, salary position relative to market/band, leave patterns, attendance trends, and time-since-last-promotion. Returns risk tiers (high/medium/low) with contributing factors. PRIVACY: Individual-level results require manager/HR role; department-level is always aggregated.",
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

**Acceptance Criteria:**

- [ ] The tool is added to `AhmadAgent.get_tools()` and dispatched in `handle_tool_call()`
- [ ] Risk score is computed as a weighted composite (0-100) from these signals, all queried from existing models:
  - **Tenure risk** (30% weight): Employees with < 1 year or > 5 years tenure score higher (new hires and stale tenures). Queried from `Employee.hire_date`
  - **Salary position** (25% weight): Compare `Employee.salary` to the department median. Employees below the 25th percentile in their department score higher
  - **Leave pattern** (20% weight): Unusual spike in sick leave over last 3 months vs. prior 9 months (query `LeaveRequest` where `leave_type == LeaveType.sick` and `status == approved`). A 2x+ spike raises the score
  - **Attendance trend** (15% weight): Increasing late arrivals or absences over last 3 months vs. prior period (query `AttendanceRecord` for `status == late` or `status == absent`)
  - **Stagnation** (10% weight): Time since last job title change or salary adjustment. If no change in 24+ months, score increases. Derived from `Employee.updated_at` as a proxy (future: promotion history table)
- [ ] Department-level output includes: `department_name`, `department_id`, `avg_risk_score`, `risk_tier` (high/medium/low), `headcount`, `high_risk_count`, `top_risk_factors` (list of the top 2 contributing factors)
- [ ] When `include_individuals == true`, individual output includes: `employee_id`, `risk_score`, `risk_tier`, `factors` (dict of factor name to sub-score). Employee names are included ONLY for the requesting employee's direct reports (validated via `Employee.manager_id == requesting_employee_id`)
- [ ] k-anonymity: departments with fewer than `MIN_GROUP_SIZE` (5) employees are excluded from department-level results and flagged as `"too_small_to_report"`
- [ ] Risk tiers: high >= 70, medium >= 40, low < 40
- [ ] Tenant isolation enforced on all queries via `Employee.tenant_id == self.tenant_id`
- [ ] If no employees match the filter, return `{"message": "No employees found for the given criteria"}`
- [ ] Follow-up suggestions added to `_generate_suggestions()`: "Turnover metrics", "Salary distribution", "Workforce overview"

**Edge Cases:**
- New employee (< 30 days): skip leave/attendance signals, score based on salary position and department baseline only
- Department with all employees below median salary: normalize within department, do not flag entire department as high-risk
- Employee with zero leave or attendance records: score those factors as neutral (50th percentile)

**Saudi-specific:**
- Probation period (first 90 days per Saudi Labor Law Article 53): flag probation employees separately as they have different termination risk dynamics
- Ramadan period: exclude Ramadan months from attendance trend analysis since working hours are reduced (6 hours/day per Saudi Labor Law Article 98)

**Priority:** P0
**Dependencies:** A1 + A2 tools complete, Employee/LeaveRequest/AttendanceRecord models exist

---

### Story A3-02: Budget Forecasting

**ID:** S8-A3-02
**Title:** Payroll Budget Forecasting Tool

> As a CHRO, I want to project payroll costs forward 3, 6, and 12 months under different growth scenarios so that I can plan headcount budgets and flag cost overruns early.

**Tool Definition:**

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

**Acceptance Criteria:**

- [ ] The tool is added to `AhmadAgent.get_tools()` and dispatched in `handle_tool_call()`
- [ ] **Current baseline** is computed from active employees (`Employee.status == EmployeeStatus.active`): `SUM(Employee.salary)` as monthly gross payroll
- [ ] **GOSI employer contribution** is computed per Saudi Labor Law:
  - Saudi employees: 12% of salary (employer share for annuities + SANED)
  - Non-Saudi employees: 2% of salary (occupational hazards only)
  - Nationality determined by `Employee.is_saudi` boolean
- [ ] **Monthly cost** = gross payroll + GOSI employer contributions
- [ ] **Forecast formula** for month M: `baseline_monthly_cost * (1 + monthly_growth_rate) ^ M`, where `monthly_growth_rate = annual_growth / 12`
- [ ] Output includes a `forecast` array with one entry per month: `{month_number, month_label (e.g. "Apr 2026"), projected_headcount, projected_monthly_cost_sar, projected_gosi_sar, projected_total_sar}`
- [ ] When no `growth_scenario` is specified, return all three scenarios (flat, moderate, aggressive) as separate objects
- [ ] `summary` object includes: `current_monthly_cost_sar`, `current_headcount`, `current_saudi_pct`, `projected_end_cost_sar`, `total_period_cost_sar`, `cost_increase_pct`
- [ ] k-anonymity: if a department has fewer than `MIN_GROUP_SIZE` employees, return `"department_too_small"` error
- [ ] Tenant isolation enforced via `Employee.tenant_id == self.tenant_id`
- [ ] Follow-up suggestions: "Department budget", "Headcount summary", "Salary distribution"

**Edge Cases:**
- Department with only non-Saudi employees: GOSI calculation uses 2% rate only
- `custom_growth_pct` provided without `growth_scenario == "custom"`: ignore `custom_growth_pct`
- Negative growth scenario: not supported, return validation error if `custom_growth_pct < 0`

**Saudi-specific:**
- GOSI rates: 12% employer for Saudis (9.75% annuity + 1% SANED + 1.25% occupational), 2% employer for non-Saudis (occupational hazards). These rates are current as of 2026
- Annual salary increments during Hajj/Eid bonus periods are not modeled (future enhancement)
- Saudization cost impact: if current saudi_pct is below Nitaqat threshold, note that hiring to comply will skew costs (Saudi salaries typically higher)

**Priority:** P0
**Dependencies:** A1 `get_department_budget` pattern, Employee model with `salary` and `is_saudi` fields

---

### Story A3-03: GOSI Compliance Audit

**ID:** S8-A3-03
**Title:** GOSI Contribution Compliance Audit Tool

> As a CHRO, I want to cross-check GOSI contributions recorded in payslips against actual employee salary data so that I can flag discrepancies before GOSI audits catch them.

**Tool Definition:**

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

**Acceptance Criteria:**

- [ ] The tool is added to `AhmadAgent.get_tools()` and dispatched in `handle_tool_call()`
- [ ] For each active employee with a payslip in the target month, compute:
  - **Expected employer GOSI**: Saudi employees = `salary * 0.12`, Non-Saudi = `salary * 0.02`
  - **Expected employee GOSI**: Saudi employees = `salary * 0.10`, Non-Saudi = `0`
  - **Actual GOSI**: read from `Payslip.gosi_deduction` (employee share) and compute employer share from `Payslip.employer_gosi` if the field exists, otherwise derive from total deductions
- [ ] A discrepancy is flagged when `abs(actual - expected) / expected > tolerance_pct / 100`
- [ ] Output `summary` includes: `total_employees_audited`, `compliant_count`, `minor_discrepancy_count`, `major_discrepancy_count`, `total_expected_employer_gosi_sar`, `total_actual_employer_gosi_sar`, `total_variance_sar`
- [ ] Output `discrepancies` array includes per-flagged-employee: `employee_id`, `department_name`, `nationality_type` (saudi/non_saudi), `salary_sar`, `expected_gosi_sar`, `actual_gosi_sar`, `variance_sar`, `variance_pct`, `severity` (minor/major)
- [ ] **Privacy note:** Individual employee names are included in discrepancy results since this is an audit tool used by HR/CHRO only. Employee IDs are always included.
- [ ] If no payslips exist for the target month, return `{"message": "No payslip data found for [month]. Ensure payroll has been processed."}`
- [ ] Tenant isolation enforced on all queries
- [ ] Follow-up suggestions: "Payroll summary", "Compliance status", "Workforce overview"

**Edge Cases:**
- Employee salary changed mid-month: use the salary recorded in the payslip (`Payslip.basic_salary`) as the source of truth, not `Employee.salary`
- Employee terminated mid-month: include in audit if payslip exists for that month
- Payslip exists but GOSI fields are NULL: flag as `"missing_gosi_data"` severity

**Saudi-specific:**
- GOSI contribution ceiling: as of 2026, the maximum monthly salary subject to GOSI is SAR 45,000. Contributions above this ceiling should be capped in the expected calculation
- Non-Saudi employees are not subject to annuity (9.75%) or SANED (1%), only occupational hazards (2% employer, 0% employee)
- GOSI registration is mandatory within 15 days of employment start (Article 17, GOSI Law)

**Priority:** P0
**Dependencies:** Payslip model (`/backend/app/models/payslip.py`), Employee model with `is_saudi` and `salary`

---

### Story A3-04: Policy Acknowledgment Tracking

**ID:** S8-A3-04
**Title:** Policy Acknowledgment Compliance Tracking Tool

> As a CHRO, I want to see which policies employees have and have not acknowledged, with compliance rates by department, so that I can enforce mandatory policy reviews and stay audit-ready.

**Tool Definition:**

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

**Acceptance Criteria:**

- [ ] The tool is added to `AhmadAgent.get_tools()` and dispatched in `handle_tool_call()`
- [ ] Queries `HRPolicy` (from `/backend/app/models/hr_policy.py`) joined with `PolicyAcknowledgment` and `Employee`
- [ ] Only `HRPolicy` records with `status == PolicyStatus.published` are included
- [ ] For each published policy, compute:
  - `total_active_employees`: count of `Employee.status == active` in scope
  - `acknowledged_count`: count of `PolicyAcknowledgment` records for this policy
  - `not_acknowledged_count`: `total_active_employees - acknowledged_count`
  - `compliance_rate_pct`: `acknowledged_count / total_active_employees * 100`
- [ ] Output `policies` array with per-policy: `policy_id`, `title`, `title_ar`, `category`, `effective_date`, `compliance_rate_pct`, `acknowledged_count`, `not_acknowledged_count`
- [ ] Output `by_department` array with per-department: `department_name`, `department_id`, `total_policies`, `avg_compliance_rate_pct`, `lowest_compliance_policy` (title + rate)
- [ ] Output `summary`: `total_published_policies`, `org_wide_compliance_rate_pct`, `fully_compliant_policies_count` (100% acknowledged), `critical_gaps` (policies with < 50% compliance)
- [ ] When `policy_id` is specified, also return `non_compliant_employees` list with `employee_id` and `department_name` (no names, to protect privacy in aggregated mode). If requester has HR role, include employee name.
- [ ] k-anonymity: departments with fewer than `MIN_GROUP_SIZE` employees are grouped under "Other"
- [ ] Tenant isolation enforced via `HRPolicy.tenant_id` and `Employee.tenant_id`
- [ ] Follow-up suggestions: "Compliance status", "Workforce overview", "Headcount summary"

**Edge Cases:**
- New policy (published today): 0% compliance is expected, do not flag as critical
- Employee with no PolicyAcknowledgment records: counts as not acknowledged for all policies
- Archived policy: excluded from compliance tracking
- Policy with `effective_date` in the future: exclude from compliance calculations (not yet in effect)

**Saudi-specific:**
- Mandatory policies under Saudi Labor Law (e.g., workplace safety per Article 121, working hours per Article 98) should be highlighted with a `mandatory` flag if the category is `safety` or `conduct`
- Ramadan working hours policy acknowledgment may have seasonal urgency -- flag if unacknowledged within 30 days of Ramadan start

**Priority:** P1
**Dependencies:** `HRPolicy` and `PolicyAcknowledgment` models exist in `/backend/app/models/hr_policy.py`

---

### Story A3-05: Natural Language Custom Report Generator

**ID:** S8-A3-05
**Title:** Natural Language Custom Report Tool

> As a CHRO, I want to ask for any HR report in natural language (e.g., "Show me all departments where Saudization is below 30% and turnover exceeded 15% this year") and get a structured result, so that I can get answers without knowing which specific tool to call.

**Tool Definition:**

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

**Acceptance Criteria:**

- [ ] The tool is added to `AhmadAgent.get_tools()` and dispatched in `handle_tool_call()`
- [ ] The tool does NOT execute raw SQL. Instead, it maps the natural language query to a combination of existing Ahmad tools internally:
  - Parse the query to identify which data domains are referenced (headcount, saudization, turnover, salary, leave, attendance, onboarding, recruitment, payroll, compliance)
  - Call the corresponding `handle_tool_call()` methods internally (e.g., if query mentions "turnover", call `get_turnover_metrics`; if it mentions "saudization", call `get_saudization_status`)
  - Combine and filter the results based on the query conditions
- [ ] Supported query patterns include:
  - Filtering: "departments where X > threshold" (e.g., turnover > 15%)
  - Comparison: "compare X across departments" (e.g., leave usage)
  - Trend: "monthly trend of X" (e.g., headcount over time)
  - Ranking: "top/bottom N departments by X" (e.g., top 3 by Saudization)
  - Cross-reference: "departments with high X and low Y" (multi-metric)
- [ ] Output `report` object includes: `title` (auto-generated from query), `generated_at`, `data` (structured results), `summary` (2-3 sentence narrative), `data_sources_used` (list of tools invoked)
- [ ] When `format == "table"`, the `data` field contains `columns` (array of header strings) and `rows` (array of row arrays)
- [ ] When `format == "summary"`, the `data` field contains a `narrative` string with inline numbers
- [ ] When `export == true`, the `csv_text` field contains the data formatted as CSV with headers
- [ ] If the query references data Ahmad does not have access to, return: `{"message": "I cannot generate a report on [topic]. This is handled by [appropriate agent name]."}`
- [ ] k-anonymity enforced on all results: departments with fewer than `MIN_GROUP_SIZE` employees are excluded
- [ ] Tenant isolation enforced on all underlying tool calls
- [ ] Follow-up suggestions: dynamically generated based on the data domains used in the report

**Edge Cases:**
- Ambiguous query (e.g., "show me everything"): return a workforce overview as the default report
- Query references a department that does not exist: return `{"message": "Department not found"}`
- Query asks for individual employee data: refuse and explain privacy constraints
- Query combines 4+ data domains: execute all relevant tools but warn about report complexity

**Saudi-specific:**
- Queries mentioning "Saudization", "Nitaqat", "GOSI", "WPS" should map to the correct compliance/saudization tools
- Arabic natural language queries are supported (e.g., "اعرض الأقسام اللي نسبة السعودة فيها أقل من 30%")

**Priority:** P1
**Dependencies:** All A1 + A2 tools must be functional since this tool orchestrates them

---

## Track 2: Dynamic Quick Actions (Per-Agent)

### Epic: CUX-04 -- Agent-Aware Quick Actions

Currently, `GET /api/v1/suggestions/quick-actions` returns actions based on the employee's role only. The actions are role-static -- they do not change when the user switches to a different agent in the sidebar. This track makes the quick actions bar context-aware: when the user clicks on Mohammad in the sidebar, the action bar shows recruitment-relevant actions; when they click on Deema, it shows leave/policy actions.

---

### Story CUX-04-01: Backend -- Agent-Scoped Quick Actions Endpoint

**ID:** S8-CUX-04-01
**Title:** Add `agent` Query Parameter to Quick Actions API

> As the frontend, I want to pass the currently selected agent name to the quick actions endpoint so that the backend returns actions relevant to that specific agent.

**Acceptance Criteria:**

- [ ] `GET /api/v1/suggestions/quick-actions` accepts a new optional query parameter: `agent` (string, one of: `deema`, `waleed`, `mohammad`, `ahmad`, `yara`)
- [ ] When `agent` is provided, the response contains only actions where `action.agent == agent` (from the existing role-based action lists) PLUS a new set of agent-specific actions defined below
- [ ] When `agent` is omitted, the current behavior is preserved (role-based actions, no filtering)
- [ ] New agent-specific action sets are defined as constants in `suggestions.py`:

**Deema actions:**
| label_en | label_ar | message | icon | category |
|----------|----------|---------|------|----------|
| Leave Balance | رصيد الإجازات | What is my leave balance? | calendar | self_service |
| Request Leave | طلب إجازة | I want to request a vacation | beach | self_service |
| My Info | معلوماتي | Show me my employee information | person | self_service |
| Company Policy | سياسة الشركة | What is the company leave policy? | document | self_service |
| My Payslip | كشف الراتب | Show my latest payslip | money | self_service |

**Ahmad actions:**
| label_en | label_ar | message | icon | category |
|----------|----------|---------|------|----------|
| Workforce Overview | نظرة عامة | Give me a workforce overview | chart | analytics |
| Saudization Status | وضع السعودة | Show Saudization status | flag | analytics |
| Turnover Report | تقرير الدوران | Show turnover metrics | trending | analytics |
| Budget Forecast | توقعات الميزانية | Forecast payroll budget for next 6 months | money | analytics |
| Attrition Risk | مخاطر التسرب | Show attrition risk analysis | warning | analytics |

**Mohammad actions:**
| label_en | label_ar | message | icon | category |
|----------|----------|---------|------|----------|
| Open Positions | الشواغر المفتوحة | Show open positions | briefcase | recruitment |
| Candidate Pipeline | خط المرشحين | Show recruitment pipeline | funnel | recruitment |
| Schedule Interview | جدولة مقابلة | Schedule an interview | calendar | recruitment |
| Post New Job | نشر وظيفة | Create a new job posting | plus | recruitment |
| Recruitment Analytics | تحليلات التوظيف | Show recruitment analytics | chart | analytics |

**Waleed actions:**
| label_en | label_ar | message | icon | category |
|----------|----------|---------|------|----------|
| Onboarding Status | حالة التأهيل | Show my onboarding progress | rocket | self_service |
| Team Overview | نظرة على الفريق | Show my team overview | people | team |
| Pending Approvals | الموافقات المعلقة | Show pending leave requests for my team | check | team |
| New Hire Checklist | قائمة الموظف الجديد | Show onboarding checklist | list | onboarding |
| Team Attendance | حضور الفريق | Show team attendance | clock | team |

**Yara actions:**
| label_en | label_ar | message | icon | category |
|----------|----------|---------|------|----------|
| Create Agent | إنشاء وكيل | I want to create a new AI agent | plus | factory |
| List Agents | عرض الوكلاء | List all deployed agents | list | factory |
| Design Agent | تصميم وكيل | Design an agent for my department | design | factory |
| Agent Analytics | تحليلات الوكلاء | Show agent usage analytics | chart | analytics |
| Workforce Plan | خطة القوى العاملة | Create a workforce plan | plan | factory |

- [ ] The response continues to respect the employee's role: an employee-role user seeing Mohammad's actions will not see "Post New Job" (that requires HR admin/manager)
- [ ] Maximum of 6 actions returned, sorted by category relevance to the agent
- [ ] Response model remains `QuickActionsResponse` (no breaking changes)

**Priority:** P0
**Dependencies:** Existing quick actions infrastructure in `/backend/app/api/suggestions.py`

---

### Story CUX-04-02: Frontend -- Pass Selected Agent to Quick Actions

**ID:** S8-CUX-04-02
**Title:** Update Chat UI to Send Agent Context with Quick Actions Request

> As a user, when I select a different agent in the sidebar, I want the quick actions bar to update immediately with actions relevant to that agent, so that I always see contextually useful shortcuts.

**Acceptance Criteria:**

- [ ] In `/backend/static/chat.html`, the `loadQuickActions()` function is updated to include the `?agent=` query parameter using the current `selectedAgent` variable
- [ ] The fetch call changes from:
  `fetch('/api/v1/suggestions/quick-actions', {...})`
  to:
  `fetch('/api/v1/suggestions/quick-actions?agent=' + selectedAgent, {...})`
- [ ] `loadQuickActions()` is called inside `startNewConversation(agentName)` AFTER `selectedAgent` is set (this already happens at line ~2515 of chat.html -- verify the call order is correct)
- [ ] `loadQuickActions()` is called inside `resumeConversation(conversationId, agentName)` AFTER `selectedAgent` is updated
- [ ] When the user clicks a quick action button, the `selectedAgent` is NOT changed by the button click (it should already be set to the correct agent since the actions are agent-scoped)
- [ ] The quick action buttons animate smoothly when switching agents (use CSS transition on the container, e.g., fade-out old actions, fade-in new actions over 200ms)
- [ ] The fallback actions in `_renderFallbackQuickActions()` remain unchanged (generic Deema actions for offline/error state)
- [ ] The quick actions bar is hidden during agent switch transition and shown after new actions load (prevent flicker of stale actions)

**Priority:** P0
**Dependencies:** S8-CUX-04-01 (backend agent parameter)

---

### Story CUX-04-03: Suggestion Chips Also Agent-Aware

**ID:** S8-CUX-04-03
**Title:** Filter Smart Suggestions by Active Agent

> As a user, I want the suggestion chips above the input field to prioritize suggestions relevant to my currently selected agent, so that the entire UI feels context-aware.

**Acceptance Criteria:**

- [ ] `GET /api/v1/suggestions` accepts a new optional query parameter: `agent` (string)
- [ ] When `agent` is provided, suggestions with `agent_target == agent` are boosted in priority (priority value decreased by 1, minimum 1)
- [ ] Suggestions for other agents are still included but appear lower in the list
- [ ] The frontend passes `selectedAgent` to the suggestions endpoint the same way as quick actions
- [ ] Maximum suggestion count remains 6
- [ ] The current rule functions (`_rule_pending_leaves`, `_rule_time_based`, etc.) continue to work unchanged -- the agent filter is applied as a post-processing sort boost, not a filter

**Priority:** P2
**Dependencies:** S8-CUX-04-01

---

## Track 3: Knowledge Management Module

### Epic: KM -- Knowledge Management System

Build a knowledge management system that stores documents and policies, chunks and embeds them via pgvector, and provides per-agent scoped RAG search. This extends the existing `policies`/`policy_chunks` tables (in `/backend/app/models/policy.py`) with a more flexible `knowledge_sources` abstraction, and ties into Yara's `assign_knowledge` tool (designed in `/docs/yara_factory_enhancements.md`).

---

### Story KM-01: Knowledge Sources Data Model

**ID:** S8-KM-01
**Title:** Create `knowledge_sources` Table and Model

> As the system, I need a `knowledge_sources` table to store metadata about any document, policy, or custom text that can be assigned to agents for RAG search, so that knowledge can be managed independently of the existing `policies` table.

**Acceptance Criteria:**

- [ ] A new SQLAlchemy model `KnowledgeSource` is created in `/backend/app/models/knowledge_source.py` with these columns:

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK, default uuid4 | Primary key |
| `tenant_id` | UUID | FK tenants.id, NOT NULL | Tenant isolation |
| `title` | String(500) | NOT NULL | Document title (EN) |
| `title_ar` | String(500) | nullable | Document title (AR) |
| `source_type` | Enum | NOT NULL | One of: `policy`, `document`, `markdown`, `custom_text`, `url` |
| `category` | String(100) | nullable | Free-form category tag (e.g., "leave", "gosi", "onboarding") |
| `content_text` | Text | nullable | Raw text content (for custom_text type) |
| `file_path` | String(1000) | nullable | Path to uploaded file (for document/markdown) |
| `url` | String(2000) | nullable | Source URL (for url type) |
| `source_policy_id` | UUID | FK hr_policies.id, nullable | Link to existing HRPolicy (for policy type) |
| `chunk_count` | Integer | default 0 | Number of embedded chunks |
| `embedding_status` | Enum | default 'pending' | One of: `pending`, `processing`, `complete`, `failed` |
| `is_active` | Boolean | default True | Soft delete |
| `metadata_json` | JSONB | nullable | Flexible metadata (author, version, tags, language) |
| `created_by` | UUID | FK employees.id, nullable | Who uploaded it |
| `created_at` | DateTime | default utcnow | Timestamp |
| `updated_at` | DateTime | default utcnow, onupdate utcnow | Timestamp |

- [ ] A new SQLAlchemy model `KnowledgeChunk` is created in the same file with these columns:

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK, default uuid4 | Primary key |
| `source_id` | UUID | FK knowledge_sources.id, NOT NULL | Parent source |
| `tenant_id` | UUID | FK tenants.id, NOT NULL | Tenant isolation (denormalized for query perf) |
| `chunk_index` | Integer | NOT NULL | Order within source |
| `content` | Text | NOT NULL | Chunk text |
| `token_count` | Integer | default 0 | Token count for the chunk |
| `embedding` | Vector(1536) | nullable | pgvector embedding (OpenAI text-embedding-3-small) |
| `created_at` | DateTime | default utcnow | Timestamp |

- [ ] A new SQLAlchemy model `AgentKnowledgeAssignment` is created for the many-to-many relationship between deployed agents and knowledge sources:

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK, default uuid4 | Primary key |
| `agent_id` | UUID | FK deployed_agents.id, NOT NULL | The agent |
| `source_id` | UUID | FK knowledge_sources.id, NOT NULL | The knowledge source |
| `tenant_id` | UUID | FK tenants.id, NOT NULL | Tenant isolation |
| `assigned_at` | DateTime | default utcnow | When assigned |
| `assigned_by` | UUID | FK employees.id, nullable | Who assigned it |

- [ ] Unique constraint on (`agent_id`, `source_id`) in `AgentKnowledgeAssignment` to prevent duplicate assignments
- [ ] Indexes: `ix_knowledge_sources_tenant_type` on `(tenant_id, source_type)`, `ix_knowledge_chunks_source` on `(source_id)`, `ix_agent_knowledge_tenant_agent` on `(tenant_id, agent_id)`
- [ ] Alembic migration is generated and tested
- [ ] Model is registered in `/backend/app/models/__init__.py`

**Priority:** P0
**Dependencies:** Existing `policies` and `policy_chunks` tables as pattern reference, `deployed_agents` table for FK

---

### Story KM-02: Markdown Ingestion Pipeline

**ID:** S8-KM-02
**Title:** Markdown File Ingestion and Embedding Pipeline

> As an admin, I want to upload a Markdown file (from an Obsidian vault or manual upload) and have it automatically chunked, embedded, and stored in pgvector, so that agents can search it via RAG.

**Acceptance Criteria:**

- [ ] A new service module `/backend/app/services/knowledge_ingestion.py` is created with a function:
  ```python
  async def ingest_markdown(
      db: AsyncSession,
      tenant_id: UUID,
      source_id: UUID,
      content: str,  # raw markdown text
      chunk_size: int = 800,  # tokens per chunk
      chunk_overlap: int = 100,  # overlap tokens between chunks
  ) -> int:  # returns number of chunks created
  ```
- [ ] The function performs these steps in order:
  1. Parse the Markdown content, preserving heading structure for context
  2. Split into chunks using a token-aware splitter (respect paragraph and heading boundaries, do not split mid-sentence)
  3. For each chunk, prepend the nearest parent heading(s) as context (e.g., "## Leave Policy > ### Annual Leave > [chunk text]")
  4. Generate embeddings via OpenAI `text-embedding-3-small` (same model as existing `/backend/app/rag/ingest.py`)
  5. Batch insert `KnowledgeChunk` records with embeddings
  6. Update `KnowledgeSource.chunk_count` and set `embedding_status = 'complete'`
- [ ] If embedding fails (API error, rate limit), set `embedding_status = 'failed'` and log the error. Do not leave partial chunks -- the operation is atomic (rollback on failure)
- [ ] The function reuses the existing embedding client pattern from `/backend/app/rag/retriever.py` (`_get_httpx_client()`)
- [ ] Chunking respects bilingual content: Arabic text and English text in the same document are chunked together (do not split by language)
- [ ] The token counter uses `tiktoken` with the `cl100k_base` encoding (same as OpenAI embeddings)
- [ ] A convenience function `ingest_file(db, tenant_id, source_id, file_path)` reads a `.md` file from disk and calls `ingest_markdown()`
- [ ] Existing `policies` table data is NOT migrated in this story -- that is a separate migration story

**Edge Cases:**
- Empty Markdown file: create the `KnowledgeSource` with `chunk_count = 0` and `embedding_status = 'complete'`
- Very large file (> 500 chunks): process in batches of 50 to avoid memory issues with embedding API calls
- Markdown with images/links: strip image references, preserve link text

**Priority:** P0
**Dependencies:** S8-KM-01 (knowledge_sources model), OpenAI API key configured

---

### Story KM-03: Per-Agent Knowledge Scoping (Agent-Scoped RAG)

**ID:** S8-KM-03
**Title:** Agent-Scoped RAG Search Using Knowledge Assignments

> As the system, when an agent searches its knowledge base, it should only search the knowledge sources assigned to it (via `AgentKnowledgeAssignment`), not the entire global knowledge base, so that agents give focused, relevant answers.

**Acceptance Criteria:**

- [ ] A new retriever class `ScopedKnowledgeRetriever` is created in `/backend/app/rag/scoped_retriever.py` with this interface:
  ```python
  class ScopedKnowledgeRetriever:
      def __init__(self, db: AsyncSession, tenant_id: UUID, agent_id: UUID | None = None):
          ...
      async def search(self, query: str, top_k: int = 5) -> list[dict]:
          # Returns list of {content, source_title, source_id, similarity_score}
          ...
  ```
- [ ] When `agent_id` is provided:
  - Query `AgentKnowledgeAssignment` to get the list of `source_id` values assigned to this agent
  - Search `KnowledgeChunk` using pgvector cosine similarity, filtered to only chunks belonging to assigned sources
  - SQL: `SELECT ... FROM knowledge_chunks kc JOIN agent_knowledge_assignments aka ON kc.source_id = aka.source_id WHERE aka.agent_id = :agent_id AND kc.tenant_id = :tenant_id ORDER BY kc.embedding <=> :query_embedding LIMIT :top_k`
- [ ] When `agent_id` is None (or the agent has no assignments):
  - Fall back to searching ALL active `KnowledgeChunk` records for the tenant (global search)
  - This preserves backward compatibility for super agents like Deema that use global knowledge
- [ ] The existing `PolicyRetriever` in `/backend/app/rag/retriever.py` is NOT modified -- it continues to work for the `policies`/`policy_chunks` tables. The new `ScopedKnowledgeRetriever` operates on the `knowledge_sources`/`knowledge_chunks` tables
- [ ] Each result includes `source_title`, `source_type`, and `chunk_index` for attribution
- [ ] Results are filtered to only `KnowledgeSource.is_active == True`
- [ ] The retriever uses the same embedding function as the existing `PolicyRetriever._get_embedding()`

**Priority:** P0
**Dependencies:** S8-KM-01 (data model), S8-KM-02 (ingested chunks to search)

---

### Story KM-04: Admin API Endpoints for Knowledge Management

**ID:** S8-KM-04
**Title:** CRUD API for Knowledge Sources and Agent Assignment

> As an admin, I want API endpoints to create, list, update, and delete knowledge sources, upload documents, and assign/unassign knowledge sources to agents, so that I can manage the knowledge base programmatically.

**Acceptance Criteria:**

- [ ] A new API router is created at `/backend/app/api/knowledge.py` with prefix `/knowledge`
- [ ] Endpoints:

**Knowledge Source CRUD:**

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/knowledge/sources` | Create a knowledge source (title, source_type, content/file, category, metadata) |
| `GET` | `/knowledge/sources` | List all knowledge sources for the tenant. Supports `?source_type=`, `?category=`, `?status=` filters |
| `GET` | `/knowledge/sources/{source_id}` | Get a single knowledge source with chunk count and assignment count |
| `PATCH` | `/knowledge/sources/{source_id}` | Update title, category, metadata, is_active |
| `DELETE` | `/knowledge/sources/{source_id}` | Soft delete (set is_active=False), do not delete chunks |

**Document Upload:**

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/knowledge/sources/{source_id}/upload` | Upload a Markdown file. Triggers `ingest_markdown()` pipeline. Accepts `multipart/form-data` with a single file field |
| `POST` | `/knowledge/sources/{source_id}/ingest-text` | Ingest raw text content (for custom_text type). Accepts JSON body `{"content": "..."}` |

**Agent Assignment:**

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/knowledge/sources/{source_id}/assign` | Assign to an agent. Body: `{"agent_id": "uuid"}` |
| `DELETE` | `/knowledge/sources/{source_id}/assign/{agent_id}` | Unassign from an agent |
| `GET` | `/knowledge/agents/{agent_id}/sources` | List all knowledge sources assigned to an agent |

- [ ] All endpoints enforce tenant isolation via the auth middleware (`get_chat_employee` or admin auth)
- [ ] The `POST /sources` endpoint validates `source_type` and required fields per type:
  - `policy`: requires `source_policy_id`
  - `custom_text`: requires `content_text` in body
  - `markdown`: no content required at creation (uploaded separately via `/upload`)
  - `document`: no content required at creation (uploaded separately)
  - `url`: requires `url` field
- [ ] The upload endpoint validates file extension (`.md` only for now) and max file size (5MB)
- [ ] The upload endpoint triggers the ingestion pipeline asynchronously (return 202 Accepted, client polls `GET /sources/{id}` to check `embedding_status`)
- [ ] All list endpoints support pagination: `?page=1&page_size=20` with response including `total`, `page`, `page_size`
- [ ] Response models use Pydantic schemas defined in the same file or a dedicated schemas module
- [ ] Router is registered in the main app at `/api/v1/knowledge`

**Priority:** P0
**Dependencies:** S8-KM-01 (model), S8-KM-02 (ingestion pipeline), S8-KM-03 (scoped retriever for assignment validation)

---

### Story KM-05: Knowledge Management Module — Standalone Interface

**ID:** S8-KM-05
**Title:** Standalone Knowledge Management Page with AI-Assisted Capture and Voice Input

> As an admin/co-founder, I want a dedicated Knowledge Management page (separate from chat) where I can capture knowledge via voice, text, or file upload, and have AI automatically structure, categorize, and assign it to the right agents.

**Design Philosophy:**
This is NOT an admin CRUD form. It is an **AI-assisted knowledge capture interface** — the user speaks or types unstructured information, and the system structures it. It lives as its own module in the platform navigation, alongside Chat and Teams.

**Acceptance Criteria:**

- [ ] A new HTML page is created at `/backend/static/knowledge.html` (standalone module, same design system as `chat.html`)

**1. Navigation — Knowledge is a top-level module**
- [ ] The main sidebar in `chat.html` gets a new navigation section: `💬 Chat | 👥 Teams | 📚 Knowledge`
- [ ] Clicking "📚 Knowledge" navigates to `/knowledge.html`
- [ ] The knowledge page has its own sidebar showing: recent entries, categories, agents

**2. AI-Assisted Knowledge Capture (primary input)**
- [ ] A prominent input area at the top with:
  - **Text input** — large textarea with placeholder: "Type or speak to add knowledge..."
  - **🎙️ Voice button** — hold-to-record, uses Web Speech API (SpeechRecognition) for browser-native STT as MVP. Transcribed text appears in the textarea.
  - **📎 Upload button** — accepts `.md`, `.txt`, `.pdf` files (drag-drop or file picker)
- [ ] After the user submits text/voice input, the system calls an **AI structuring endpoint** (`POST /api/v1/knowledge/capture`) that:
  - Extracts: title, category, scope, relevant agents
  - Returns a structured preview card for the user to confirm/edit
  - Example: user says "engineering new hires get 3 month probation not 6 starting next quarter" → AI returns:
    ```
    📋 Engineering Probation Period
    ├ Category: HR Policy
    ├ Scope: Engineering dept, new hires
    ├ Effective: Q3 2026
    ├ Assign to: Deema, Waleed
    └ Content: [structured version of what user said]
    ```
- [ ] The user can **edit** the structured preview (title, category, agent assignment) before confirming
- [ ] On confirm, the system creates the `KnowledgeSource`, ingests/embeds it, and assigns to agents
- [ ] The AI structuring uses Claude (same Anthropic client as agents) with a focused prompt for knowledge extraction

**3. Knowledge Library (browse/search)**
- [ ] Below the capture area, a searchable list of all knowledge entries
- [ ] Each entry shows: title, category tag, source type icon (🎙️ voice, ✍️ text, 📄 file), assigned agents, date
- [ ] Search bar with full-text search across titles and content
- [ ] Filter by: category, source type, assigned agent, date range
- [ ] Click an entry to expand: full content, edit, re-assign agents, delete

**4. Agent Assignment**
- [ ] Each knowledge entry shows which agents can use it (chips/badges)
- [ ] Click to open assignment panel: list of all agents with toggle switches
- [ ] Changes saved immediately via API

**5. Voice Capture Details**
- [ ] Uses the browser's built-in `SpeechRecognition` API (Chrome/Edge) as MVP — no server-side STT needed yet
- [ ] Supports Arabic and English speech (set `recognition.lang` based on selected language)
- [ ] Visual feedback: pulsing mic icon while recording, waveform or timer
- [ ] Transcribed text is editable before submission
- [ ] Future sprint (Sprint 9): upgrade to Whisper server-side STT for better accuracy and cross-browser support

- [ ] The page uses the same design system as `chat.html` (Inter font, CSS variables, light/dark mode)
- [ ] The page requires authentication (same `authToken` pattern)
- [ ] Bilingual labels (Arabic/English) following `selectedLanguage` pattern
- [ ] The page is functional end-to-end — capture via voice/text/upload, AI structures, confirm, browse, assign

**New API Endpoint for AI Capture:**
```
POST /api/v1/knowledge/capture
Body: { "content": "raw text from voice/typing", "language": "en"|"ar" }
Response: {
  "suggested_title": "Engineering Probation Period",
  "suggested_category": "hr_policy",
  "suggested_agents": ["deema", "waleed"],
  "structured_content": "...",
  "confidence": 0.92
}
```

**Priority:** P1
**Dependencies:** S8-KM-04 (API endpoints), S8-KM-02 (ingestion pipeline)

---

### Story KM-06: Migrate Existing Policies to Knowledge Sources

**ID:** S8-KM-06
**Title:** Migration Script for Existing Policy Data

> As the system, I want a one-time migration script that copies existing `policies`/`policy_chunks` data into the new `knowledge_sources`/`knowledge_chunks` tables, so that agents can use the new scoped RAG system with existing content.

**Acceptance Criteria:**

- [ ] A migration script is created at `/backend/scripts/migrate_policies_to_knowledge.py`
- [ ] For each active `Policy` record in the `policies` table:
  1. Create a `KnowledgeSource` with `source_type = 'policy'`, title from `Policy.title`, category from `Policy.category`
  2. Copy all associated `PolicyChunk` records to `KnowledgeChunk` records, preserving `content`, `chunk_index`, `embedding`, and `token_count`
  3. Set `embedding_status = 'complete'` and `chunk_count` to the actual chunk count
- [ ] The script is idempotent: running it twice does not create duplicates (check by `title` + `tenant_id` + `source_type`)
- [ ] The script logs progress: "Migrated policy [title] with [N] chunks"
- [ ] The original `policies` and `policy_chunks` tables are NOT modified or deleted
- [ ] The script can be run as: `python -m scripts.migrate_policies_to_knowledge`

**Priority:** P2
**Dependencies:** S8-KM-01 (target model), existing policies data

---

## Track 4: Ahmad English-Only Responses

### Epic: AHM-LANG -- Ahmad English-Only Response Mode

---

### Story AHM-LANG-01: Ahmad System Prompt English Enforcement

**ID:** S8-AHM-LANG-01
**Title:** Force Ahmad to Respond in English Regardless of User Language

> As the CTO, I want Ahmad to always respond in English even when users message in Arabic, so that analytics reports are consistent and professional for executive consumption.

**Acceptance Criteria:**

- [ ] In `/backend/app/agents/ahmad.py`, the `_get_scope_rules()` method is updated to include an explicit language instruction at the top of the scope rules:
  ```
  "LANGUAGE RULE: You MUST always respond in English, regardless of the language the user writes in. "
  "If the user writes in Arabic, understand their request but respond entirely in English. "
  "Do not mix Arabic and English in your responses. "
  "Exception: When quoting Arabic terms of art (e.g., نطاقات for Nitaqat, التأمينات الاجتماعية for GOSI), "
  "include the Arabic term in parentheses after the English term for clarity."
  ```
- [ ] The `personality` field is updated to remove the phrase "You are bilingual and switch naturally between Arabic and English" and replace it with "You always respond in English for consistency in executive reporting. You understand Arabic queries fluently."
- [ ] The Arabic glossary section in `_get_scope_rules()` is preserved (Ahmad needs to understand Arabic input) but a note is added: "Use these terms to understand Arabic queries. Always respond in English."
- [ ] Ahmad's `_generate_suggestions()` method continues to return both Arabic and English suggestion text (the UI uses these, not Ahmad's response language)
- [ ] The follow-up suggestions from A3 tools also include both `text_ar` and `text_en` as before
- [ ] Testing: when a user sends "اعطني ملخص القوى العاملة" (give me workforce overview), Ahmad responds in English with the workforce overview data
- [ ] Testing: when a user sends "What is our Saudization status?", Ahmad responds in English (no change from current behavior)

**Priority:** P1
**Dependencies:** None -- this is a prompt-only change to ahmad.py

---

## Coverage Matrix

### Track 1: Ahmad A3 -- Predictive Analytics

| Capability | Story ID | Status |
|------------|----------|--------|
| Attrition risk scoring (tenure, salary, leave, attendance) | S8-A3-01 | Covered |
| Budget forecasting (3/6/12 months, growth scenarios, GOSI) | S8-A3-02 | Covered |
| GOSI compliance audit (payslip cross-check, discrepancy flagging) | S8-A3-03 | Covered |
| Policy acknowledgment tracking (compliance rates, department breakdown) | S8-A3-04 | Covered |
| Natural language custom reports (query parsing, multi-tool orchestration) | S8-A3-05 | Covered |
| Follow-up suggestions for A3 tools | All A3 stories | Covered |
| k-anonymity for all A3 tools | All A3 stories | Covered |

### Track 2: Dynamic Quick Actions

| Capability | Story ID | Status |
|------------|----------|--------|
| Backend: agent query parameter on quick-actions endpoint | S8-CUX-04-01 | Covered |
| Backend: per-agent action definitions (all 5 agents) | S8-CUX-04-01 | Covered |
| Frontend: pass selectedAgent to quick-actions fetch | S8-CUX-04-02 | Covered |
| Frontend: reload actions on agent switch | S8-CUX-04-02 | Covered |
| Frontend: smooth transition animation | S8-CUX-04-02 | Covered |
| Suggestion chips agent-aware boost | S8-CUX-04-03 | Covered |

### Track 3: Knowledge Management

| Capability | Story ID | Status |
|------------|----------|--------|
| `knowledge_sources` table | S8-KM-01 | Covered |
| `knowledge_chunks` table with pgvector | S8-KM-01 | Covered |
| `agent_knowledge_assignments` table | S8-KM-01 | Covered |
| Markdown ingestion pipeline (parse, chunk, embed) | S8-KM-02 | Covered |
| Agent-scoped RAG retriever | S8-KM-03 | Covered |
| Global fallback for unscoped agents | S8-KM-03 | Covered |
| Admin CRUD API for knowledge sources | S8-KM-04 | Covered |
| File upload endpoint (Markdown) | S8-KM-04 | Covered |
| Agent assignment/unassignment API | S8-KM-04 | Covered |
| Admin upload UI (HTML page) | S8-KM-05 | Covered |
| Migration of existing policies data | S8-KM-06 | Covered |
| Yara `assign_knowledge` tool integration | -- | Gap (deferred to Yara Y3 sprint) |
| Yara `list_agent_knowledge` tool integration | -- | Gap (deferred to Yara Y3 sprint) |
| PDF/DOCX ingestion | -- | Gap (future: only Markdown supported in S8) |

### Track 4: Ahmad English-Only

| Capability | Story ID | Status |
|------------|----------|--------|
| System prompt English enforcement | S8-AHM-LANG-01 | Covered |
| Personality update | S8-AHM-LANG-01 | Covered |
| Arabic input understanding preserved | S8-AHM-LANG-01 | Covered |
| Suggestion chips remain bilingual | S8-AHM-LANG-01 | Covered |

---

## Sprint 8 Priority Summary

| Priority | Stories | Track |
|----------|---------|-------|
| **P0** | S8-A3-01 (attrition), S8-A3-02 (budget forecast), S8-A3-03 (GOSI audit) | Ahmad A3 |
| **P0** | S8-CUX-04-01 (backend), S8-CUX-04-02 (frontend) | Quick Actions |
| **P0** | S8-KM-01 (model), S8-KM-02 (ingestion), S8-KM-03 (scoped RAG), S8-KM-04 (API) | Knowledge Mgmt |
| **P1** | S8-A3-04 (policy acks), S8-A3-05 (custom reports) | Ahmad A3 |
| **P1** | S8-KM-05 (upload UI), S8-AHM-LANG-01 (English-only) | KM + Ahmad |
| **P2** | S8-CUX-04-03 (suggestion chips), S8-KM-06 (migration) | Quick Actions + KM |

---

## Cross-Agent Dependencies

| Dependency | From | To | Notes |
|------------|------|----|-------|
| Ahmad A3 tools use existing A1/A2 data queries | Ahmad A3 | Ahmad A1/A2 | No code changes to A1/A2 needed |
| `generate_custom_report` orchestrates all Ahmad tools | S8-A3-05 | All Ahmad tools | A3-05 should be implemented last |
| Quick actions reference all 5 agents | S8-CUX-04-01 | All agents | Agent-specific messages must match each agent's tool capabilities |
| Knowledge scoped RAG feeds into Yara's `assign_knowledge` | S8-KM-03 | Yara Y3 | Yara integration is deferred but model is ready |
| Admin Knowledge API will be used by Yara's factory tools | S8-KM-04 | Yara Y3 | API design should anticipate Yara's programmatic usage |
| `audit_gosi_compliance` needs Payslip GOSI fields | S8-A3-03 | Payslip model | Verify `Payslip` model has `gosi_deduction` field; add if missing |
| `get_policy_acknowledgments` needs HRPolicy + PolicyAcknowledgment | S8-A3-04 | hr_policy model | Both models already exist |
