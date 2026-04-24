# Yara Agent Factory Enhancements — Visibility, Data Sources, Knowledge, Overlap Detection

**Author:** Tariq (PO) | **Date:** 2026-03-29
**Context:** CTO feedback — agents created by Yara need proper visibility controls, data source bindings, knowledge base assignments, and overlap prevention.

---

## Gap Analysis

### What Yara's Agent Factory does today (Y2: 6 tools)
- `design_agent` — Claude generates agent spec (personality, tools, scope, escalation)
- `create_agent` — saves to `deployed_agents` table with status=draft
- `activate_agent` — status → active, agent becomes routable
- `configure_agent_tools` — update tool definitions
- `set_escalation_rules` — define escalation conditions
- `list_deployed_agents` — query by department/status

### What's missing

| Gap | Current State | Problem |
|-----|--------------|---------|
| **Visibility** | Every active agent is visible to ALL employees in the department. No access control. | A finance dept agent handling executive compensation should NOT be visible to junior staff. |
| **Data Sources** | `scope_boundaries.data_access` is a text list (e.g., "invoices, purchase orders"). Not enforced. | An agent could be asked about data it shouldn't access. No actual DB-level data binding. |
| **Knowledge Base** | Agents use the global RAG retriever (all HR policies). No per-agent knowledge. | A compliance agent needs specific regulations. An IT support agent needs IT docs, not HR policies. |
| **Overlap Detection** | `create_agent` and `design_agent` never check existing agents. | User could create 3 "Invoice Processor" agents in the same department. Wastes resources, confuses employees. |

---

## Enhancement 1: Agent Visibility & Access Control

### Data Model Changes

**Add to `deployed_agents` table:**
```
visibility: Enum('department', 'role_based', 'specific_users', 'organization')
  - department (default): visible to all members of the agent's department
  - role_based: visible only to employees with specific roles
  - specific_users: visible only to listed employee IDs
  - organization: visible to all employees across all departments

allowed_roles: JSONB (nullable)
  - e.g., ["manager", "hr_admin", "c_suite"]
  - Only used when visibility = 'role_based'

allowed_users: JSONB (nullable)
  - e.g., ["uuid-1", "uuid-2"]
  - Only used when visibility = 'specific_users'
```

### Affected Code

1. **`design_agent`** — prompt should ask Claude to suggest a visibility level based on the role
2. **`create_agent`** — accept `visibility`, `allowed_roles`, `allowed_users` params
3. **Teams API** — `GET /teams/{dept_id}/members` must filter AI agents by visibility rules:
   - Check requesting employee's role against `allowed_roles`
   - Check requesting employee's ID against `allowed_users`
   - Department-scoped agents shown to all dept members
   - Org-wide agents shown to everyone
4. **Orchestrator** — when routing to `dept:{uuid}`, verify the employee has visibility access
5. **New tool: `set_agent_visibility`** — update visibility settings for a deployed agent

### User Stories

**UV-01: Set visibility when creating agent**
> As Yara designing an agent, when generating the spec, I should suggest a visibility level based on the agent's role and data sensitivity.

Acceptance Criteria:
- [ ] `design_agent` output includes `"visibility": "role_based"` for agents handling sensitive data (payroll, compensation, legal)
- [ ] `design_agent` output includes `"visibility": "department"` for general-purpose dept agents
- [ ] `create_agent` accepts and stores `visibility`, `allowed_roles`, `allowed_users`
- [ ] Default visibility is `department` if not specified

**UV-02: Filter agents by visibility in Teams API**
> As an employee viewing my team, I should only see AI agents I have access to.

Acceptance Criteria:
- [ ] Given an agent with `visibility=role_based` and `allowed_roles=["manager"]`, when a regular employee views the team, then the agent is NOT shown
- [ ] Given the same agent, when a manager views the team, then the agent IS shown
- [ ] Given an agent with `visibility=specific_users`, when an unlisted employee views the team, then the agent is NOT shown
- [ ] Given an agent with `visibility=organization`, when any employee views any team, then the agent IS shown in the originating department

**UV-03: Set agent visibility tool**
> As an HR admin talking to Yara, I want to change who can see and use a deployed agent.

Tool definition:
```json
{
  "name": "set_agent_visibility",
  "description": "Set who can see and interact with a deployed AI agent.",
  "input_schema": {
    "type": "object",
    "properties": {
      "agent_id": {"type": "string"},
      "visibility": {"type": "string", "enum": ["department", "role_based", "specific_users", "organization"]},
      "allowed_roles": {"type": "array", "items": {"type": "string"}},
      "allowed_users": {"type": "array", "items": {"type": "string"}}
    },
    "required": ["agent_id", "visibility"]
  }
}
```

---

## Enhancement 2: Data Source Binding

### Concept

Each deployed agent should have explicit data source bindings — which DB tables/models it can query. The DynamicAgent runtime currently has 3 standard tools (search_knowledge_base, escalate_to_human, lookup_employee). We need a configurable data source layer.

### Data Model Changes

**Add to `deployed_agents` table:**
```
data_sources: JSONB (nullable)
  - List of data source bindings the agent can access
  - e.g., [
      {"type": "employees", "scope": "department", "fields": ["name", "job_title", "email"]},
      {"type": "attendance", "scope": "department"},
      {"type": "leave_requests", "scope": "department"},
      {"type": "invoices", "scope": "department", "note": "custom domain table"},
    ]
```

### Available Data Source Types (map to existing models)

| Source Type | Model | Sensitive? | Default Scope |
|-------------|-------|-----------|---------------|
| `employees` | Employee | Yes (salary) | department |
| `attendance` | AttendanceRecord | No | department |
| `leave_requests` | LeaveRequest | No | department |
| `leave_balances` | LeaveBalance | No | department |
| `documents` | EmployeeDocument | Yes | own_only |
| `payslips` | Payslip | Yes | own_only |
| `compliance` | ComplianceRecord | No | organization |
| `onboarding` | OnboardingAssignment | No | department |
| `candidates` | Candidate | No | organization |
| `job_postings` | JobPosting | No | organization |
| `tickets` | Ticket | No | department |

### Affected Code

1. **`design_agent`** — Claude suggests data sources based on role/tasks
2. **`create_agent`** — accept and store `data_sources`
3. **DynamicAgent** — `_lookup_employee` and future data tools check `data_sources` config before querying. If a data source is not in the list, the agent refuses.
4. **New tool: `configure_data_sources`** — update data source bindings

### User Stories

**DS-01: Suggest data sources during design**
> As Yara designing an Invoice Processor agent, the spec should include data sources like "invoices", "employees" (for lookup), but NOT "payslips" or "leave_requests".

Acceptance Criteria:
- [ ] `design_agent` output includes `"data_sources"` list based on the role and tasks
- [ ] Sensitive sources (payslips, salary fields) are only suggested when the role explicitly needs them
- [ ] Each source includes a `scope` (department, organization, own_only)

**DS-02: Enforce data source boundaries in DynamicAgent**
> As the system, when an agent tries to access data not in its `data_sources` list, the query should be refused.

Acceptance Criteria:
- [ ] Given an agent with `data_sources: ["employees", "attendance"]`, when asked about leave balances, then the agent responds "I don't have access to leave data. Please ask Deema."
- [ ] Given an agent with employee data scoped to "department", when looking up an employee in another department, then the result is empty

**DS-03: Configure data sources tool**
```json
{
  "name": "configure_data_sources",
  "description": "Set which data sources a deployed AI agent can access and at what scope.",
  "input_schema": {
    "type": "object",
    "properties": {
      "agent_id": {"type": "string"},
      "data_sources": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "type": {"type": "string"},
            "scope": {"type": "string", "enum": ["own_only", "department", "organization"]},
            "fields": {"type": "array", "items": {"type": "string"}, "description": "Optional field-level restriction"}
          },
          "required": ["type", "scope"]
        }
      }
    },
    "required": ["agent_id", "data_sources"]
  }
}
```

---

## Enhancement 3: Knowledge Base Assignment

### Concept

Instead of all agents sharing one global RAG, each deployed agent should have its own knowledge scope — specific policies, docs, or custom knowledge files attached to it.

### Data Model Changes

**New table: `agent_knowledge_sources`**
```
id: UUID (PK)
agent_id: UUID (FK deployed_agents)
tenant_id: UUID (FK tenants)
source_type: Enum('hr_policy', 'document', 'custom_text', 'url')
source_id: UUID (nullable) — FK to hr_policies or documents table
title: String(500)
content_summary: Text — for display
embedding_ids: JSONB — list of vector IDs in pgvector for this source
is_active: Boolean (default True)
created_at: DateTime
```

**Add to `deployed_agents` table:**
```
knowledge_scope: Enum('global', 'assigned_only', 'department_policies', 'none')
  - global: agent searches all policies (current behavior)
  - assigned_only: agent only searches its assigned knowledge sources
  - department_policies: agent searches policies tagged to its department
  - none: agent has no RAG — pure tool-based
```

### Affected Code

1. **`design_agent`** — Claude suggests knowledge scope and recommends which existing policies to attach
2. **`create_agent`** — accept `knowledge_scope` param
3. **DynamicAgent._search_knowledge_base** — filter RAG search by the agent's knowledge sources instead of searching everything
4. **New tool: `assign_knowledge`** — attach policies/docs to an agent
5. **New tool: `list_agent_knowledge`** — see what knowledge an agent has

### User Stories

**KB-01: Assign knowledge during creation**
> As Yara creating a Compliance Auditor agent, I should be able to attach specific regulations and policies to it.

Acceptance Criteria:
- [ ] `create_agent` accepts `knowledge_scope` param
- [ ] After creation, `assign_knowledge` can attach HR policies by ID
- [ ] The agent's RAG search is scoped to only its assigned knowledge

**KB-02: Agent-scoped RAG search**
> As a DynamicAgent searching its knowledge base, I should only search my assigned sources, not the entire policy database.

Acceptance Criteria:
- [ ] Given an agent with `knowledge_scope=assigned_only` and 3 assigned policies, when `search_knowledge_base` runs, then only those 3 policies are searched
- [ ] Given an agent with `knowledge_scope=global`, when searching, then all policies are searched (current behavior preserved)
- [ ] Given an agent with `knowledge_scope=none`, when the user asks a knowledge question, then the agent says "I don't have a knowledge base configured. Please ask Deema for policy questions."

**KB-03: Assign knowledge tool**
```json
{
  "name": "assign_knowledge",
  "description": "Attach knowledge sources (policies, documents, custom text) to a deployed AI agent's knowledge base.",
  "input_schema": {
    "type": "object",
    "properties": {
      "agent_id": {"type": "string"},
      "sources": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "source_type": {"type": "string", "enum": ["hr_policy", "document", "custom_text"]},
            "source_id": {"type": "string", "description": "UUID of existing HR policy or document. Required for hr_policy/document types."},
            "title": {"type": "string", "description": "Title for custom_text sources."},
            "content": {"type": "string", "description": "Content for custom_text sources."}
          },
          "required": ["source_type"]
        }
      }
    },
    "required": ["agent_id", "sources"]
  }
}
```

**KB-04: List agent knowledge tool**
```json
{
  "name": "list_agent_knowledge",
  "description": "List all knowledge sources assigned to a deployed AI agent.",
  "input_schema": {
    "type": "object",
    "properties": {
      "agent_id": {"type": "string"}
    },
    "required": ["agent_id"]
  }
}
```

---

## Enhancement 4: Overlap & Duplication Detection

### Concept

Before creating a new agent, Yara should check:
1. Is there already an active/draft agent with a similar role in the same department?
2. Does the new agent's scope overlap with an existing super agent (Deema, Waleed, Mohammad, Ahmad)?
3. Does the new agent's tool set overlap significantly with another deployed agent?

### Implementation

**No schema changes needed** — this is logic in `design_agent` and `create_agent`.

### Detection Rules

1. **Same-department role similarity:** Query `deployed_agents` WHERE `department_id` matches AND `status` IN (draft, active, testing). Compare `role_title` using fuzzy matching (Levenshtein or Claude comparison).

2. **Super agent overlap:** Check if the new agent's tasks description contains keywords that map to existing super agents:
   - Leave/salary/policy/benefits → overlaps with Deema
   - Recruitment/candidates/interviews → overlaps with Mohammad
   - Onboarding/team management → overlaps with Waleed
   - Compliance/analytics/budget → overlaps with Ahmad
   - Agent factory/workforce planning → overlaps with Yara herself

3. **Tool overlap:** Compare the new agent's proposed tools with existing deployed agents' tools in the same department. Flag if >50% tool name similarity.

### User Stories

**OD-01: Check overlap before design**
> As Yara designing a new agent, I should automatically check for existing agents with similar roles and warn the user.

Acceptance Criteria:
- [ ] `design_agent` queries existing deployed agents in the same department
- [ ] If a similar role exists (fuzzy match on role_title), the response includes a warning: "An agent with a similar role already exists: [name] ([role]). Consider updating that agent instead of creating a new one."
- [ ] The warning does NOT block creation — it's advisory
- [ ] The warning includes the existing agent's ID for reference

**OD-02: Check super agent overlap**
> As Yara designing an agent whose tasks overlap with a super agent, I should warn that the super agent already handles these tasks.

Acceptance Criteria:
- [ ] If the tasks_description contains keywords matching a super agent's domain, the response includes: "Note: [task] is already handled by [Super Agent Name]. The new agent should focus on department-specific tasks that go beyond what [Super Agent Name] offers."
- [ ] The overlap check covers all 5 super agents: Deema, Waleed, Mohammad, Ahmad, Yara
- [ ] The warning suggests how to differentiate (e.g., "Deema handles general leave policies — your agent could handle department-specific approval workflows")

**OD-03: Block exact duplicates on create**
> As the system, when someone tries to create an agent with the exact same name AND department as an existing active agent, block it.

Acceptance Criteria:
- [ ] `create_agent` checks for existing agents with `name` = new name AND `department_id` = same dept AND `status` IN (draft, active, testing)
- [ ] If found, return error: "An agent named [name] already exists in this department (status: [status]). Use a different name or update the existing agent."
- [ ] Archived agents do NOT block creation

---

## Summary: New Tools for Yara

| # | Tool | Epic | Priority |
|---|------|------|----------|
| Y2-07 | `set_agent_visibility` | Visibility | P1 |
| Y2-08 | `configure_data_sources` | Data Sources | P1 |
| Y2-09 | `assign_knowledge` | Knowledge Base | P1 |
| Y2-10 | `list_agent_knowledge` | Knowledge Base | P2 |

**Enhanced existing tools (no new tool count):**
- `design_agent` — adds overlap detection, suggests visibility/data sources/knowledge
- `create_agent` — accepts visibility, data_sources, knowledge_scope; blocks exact duplicates

**New DB model:**
- `agent_knowledge_sources` table

**Schema changes to `deployed_agents`:**
- Add: `visibility`, `allowed_roles`, `allowed_users`, `data_sources`, `knowledge_scope`

**Estimated effort:** 1 sprint (fits into Sprint 8 alongside RBAC, or can be its own focused sprint)

---

## Sprint Fit

These enhancements logically pair with **Sprint 8 (RBAC)** since visibility controls are an extension of access control. Alternatively, they can be a standalone sprint between 8 and 9.

Recommended approach:
- **Sprint 8a:** RBAC + Agent Visibility (UV-01, UV-02, UV-03)
- **Sprint 8b:** Data Sources + Knowledge + Overlap (DS-01 through KB-04, OD-01 through OD-03)

This keeps Sprint 8 focused on "who can access what" across the entire platform.
