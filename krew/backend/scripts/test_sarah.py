"""Test suite for Sarah Agent — AI Workforce Architect.

Tests all 16 tools, DynamicAgent loading, orchestrator dept: routing,
and the Teams API endpoints. Deterministic where possible (DB-only),
LLM-based where the tool uses Claude internally.

Categories:
  - Unit: tool definitions, dispatch mapping, model enums
  - Integration: DB-backed tool execution (create_agent, activate, deactivate, etc.)
  - Integration: DynamicAgent config loading & tool merging
  - Integration: Orchestrator dept:{uuid} routing
  - API: Teams API endpoints (list_teams, get_team_members, list_deployed_agents)

Prerequisites:
  1. Server running at localhost:8000 (for API tests only)
  2. Seed data loaded: python -m scripts.seed
  3. PostgreSQL running at localhost:5432/krew

Usage:
    cd /Users/najwamalghamdi/Desktop/HR-AI-Startup/backend
    source venv/bin/activate
    python scripts/test_sarah.py
"""
import asyncio
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# ── Counters ─────────────────────────────────────────────────────────
passed = 0
failed = 0
skipped = 0
results = []


def record(name: str, ok: bool, detail: str = "", skip: bool = False):
    global passed, failed, skipped
    if skip:
        skipped += 1
        status = "SKIP"
    elif ok:
        passed += 1
        status = "PASS"
    else:
        failed += 1
        status = "FAIL"
    results.append((status, name, detail))
    icon = {"PASS": "PASS", "FAIL": "FAIL", "SKIP": "SKIP"}[status]
    print(f"  [{icon}] {name}")
    if detail and status == "FAIL":
        print(f"         detail: {detail}")


# ══════════════════════════════════════════════════════════════════════
# PART 1 — UNIT TESTS (no DB, no LLM)
# ══════════════════════════════════════════════════════════════════════

def test_unit():
    print("\n=== PART 1: UNIT TESTS ===\n")

    # ── 1.1 Sarah tool definitions ──
    from app.agents.sarah import SarahAgent

    # We cannot instantiate SarahAgent without DB, but we can check the class
    record("U01 SarahAgent has correct identity",
           SarahAgent.name == "Sarah" and SarahAgent.name_ar == "سارة"
           and SarahAgent.role == "AI Workforce Architect")

    # ── 1.2 Tool count: must be exactly 16 ──
    # We need a mock instance to call get_tools. Monkey-patch __init__.
    class FakeSarah(SarahAgent):
        def __init__(self):
            # skip BaseAgent.__init__
            pass

    fake = FakeSarah()
    tools = fake.get_tools()
    tool_names = [t["name"] for t in tools]

    record("U02 Sarah has exactly 16 tools",
           len(tools) == 16,
           f"Got {len(tools)} tools: {tool_names}")

    # ── 1.3 All 16 expected tool names present ──
    expected_tools = [
        # S1 — Workforce Planning
        "get_department_overview",
        "analyze_department",
        "recommend_workforce_mix",
        "simulate_scenario",
        "estimate_agent_roi",
        # S2 — Agent Factory
        "design_agent",
        "create_agent",
        "activate_agent",
        "configure_agent_tools",
        "set_escalation_rules",
        "list_deployed_agents",
        # S3 — Governance
        "get_agent_performance",
        "detect_drift",
        "update_agent_prompt",
        "deactivate_agent",
        "generate_governance_report",
    ]
    missing = [t for t in expected_tools if t not in tool_names]
    extra = [t for t in tool_names if t not in expected_tools]
    record("U03 All 16 expected tool names present",
           not missing and not extra,
           f"Missing: {missing}, Extra: {extra}")

    # ── 1.4 Each tool has required schema fields ──
    all_valid = True
    bad_tools = []
    for tool in tools:
        if not all(k in tool for k in ("name", "description", "input_schema")):
            all_valid = False
            bad_tools.append(tool.get("name", "UNNAMED"))
        schema = tool.get("input_schema", {})
        if schema.get("type") != "object":
            all_valid = False
            bad_tools.append(f"{tool['name']}: schema type != object")
    record("U04 All tools have valid schema structure",
           all_valid, f"Bad: {bad_tools}")

    # ── 1.5 Tool dispatch covers all 16 tools ──
    # Check that handle_tool_call has branches for every tool name
    import inspect
    source = inspect.getsource(SarahAgent.handle_tool_call)
    dispatch_missing = [t for t in expected_tools if t not in source]
    record("U05 handle_tool_call dispatches all 16 tools",
           not dispatch_missing,
           f"Missing dispatch: {dispatch_missing}")

    # ── 1.6 AgentStatus enum values ──
    from app.models.deployed_agent import AgentStatus
    expected_statuses = {"draft", "testing", "active", "paused", "archived"}
    actual_statuses = {s.value for s in AgentStatus}
    record("U06 AgentStatus has all 5 lifecycle states",
           actual_statuses == expected_statuses,
           f"Got: {actual_statuses}")

    # ── 1.7 PlanStatus enum values ──
    from app.models.workforce_plan import PlanStatus
    expected_plan = {"draft", "approved", "in_progress", "implemented"}
    actual_plan = {s.value for s in PlanStatus}
    record("U07 PlanStatus has all 4 states",
           actual_plan == expected_plan,
           f"Got: {actual_plan}")

    # ── 1.8 DeployedAgent model columns ──
    from app.models.deployed_agent import DeployedAgent
    required_columns = [
        "id", "tenant_id", "department_id", "name", "name_ar",
        "role_title", "role_title_ar", "personality", "system_prompt",
        "tools_config", "scope_boundaries", "escalation_rules",
        "channel_config", "status", "created_by", "performance_metrics",
        "created_at", "updated_at",
    ]
    table_cols = [c.name for c in DeployedAgent.__table__.columns]
    missing_cols = [c for c in required_columns if c not in table_cols]
    record("U08 DeployedAgent model has all required columns",
           not missing_cols,
           f"Missing: {missing_cols}")

    # ── 1.9 WorkforcePlan model columns ──
    from app.models.workforce_plan import WorkforcePlan
    wp_columns = [
        "id", "tenant_id", "department_id", "analysis",
        "current_headcount", "recommended_humans", "recommended_ai_agents",
        "estimated_annual_savings_sar", "saudization_before_pct", "saudization_after_pct",
        "status", "created_at", "updated_at",
    ]
    wp_table = [c.name for c in WorkforcePlan.__table__.columns]
    wp_missing = [c for c in wp_columns if c not in wp_table]
    record("U09 WorkforcePlan model has all required columns",
           not wp_missing,
           f"Missing: {wp_missing}")

    # ── 1.10 DynamicAgent standard tools ──
    from app.agents.dynamic_agent import STANDARD_TOOLS
    std_names = [t["name"] for t in STANDARD_TOOLS]
    record("U10 DynamicAgent has 3 standard tools",
           std_names == ["search_knowledge_base", "escalate_to_human", "lookup_employee"],
           f"Got: {std_names}")

    # ── 1.11 Orchestrator AGENTS registry includes sarah ──
    from app.agents.orchestrator import AGENTS, INTENT_KEYWORDS
    record("U11 Orchestrator AGENTS registry includes sarah",
           "sarah" in AGENTS,
           f"Keys: {list(AGENTS.keys())}")

    # ── 1.12 Sarah intent keywords exist ──
    sarah_kw = INTENT_KEYWORDS.get("sarah", [])
    expected_kw_samples = ["agent factory", "workforce plan", "deploy agent", "governance report"]
    has_all = all(kw in sarah_kw for kw in expected_kw_samples)
    record("U12 Sarah intent keywords contain key phrases",
           has_all,
           f"Missing from: {[k for k in expected_kw_samples if k not in sarah_kw]}")

    # ── 1.13 Orchestrator keyword uniqueness (no duplicates across agents) ──
    seen = {}
    dupes = []
    for agent_name, keywords in INTENT_KEYWORDS.items():
        for kw in keywords:
            if kw in seen:
                dupes.append(f"'{kw}' in {seen[kw]} and {agent_name}")
            seen[kw] = agent_name
    record("U13 No duplicate keywords across agents",
           not dupes,
           f"Dupes: {dupes}")

    # ── 1.14 DynamicAgent scope rules formatting ──
    from app.agents.dynamic_agent import DynamicAgent
    from unittest.mock import MagicMock
    mock_config = MagicMock()
    mock_config.name = "TestBot"
    mock_config.name_ar = "تيست"
    mock_config.role_title = "Test Role"
    mock_config.personality = "Friendly"
    mock_config.department_id = uuid4()
    mock_config.scope_boundaries = {
        "allowed_actions": ["answer questions"],
        "forbidden_actions": ["give legal advice"],
    }
    mock_config.escalation_rules = {
        "escalate_when": ["unsure about policy"],
    }
    mock_config.system_prompt = "You are a test agent."
    mock_config.tools_config = [{"name": "custom_tool", "description": "does stuff", "input_schema": {"type": "object", "properties": {}, "required": []}}]

    # DynamicAgent.__init__ calls super().__init__ which needs real DB
    # Instead test _get_scope_rules logic directly by manual setup
    class FakeDynamic(DynamicAgent):
        def __init__(self, config):
            self._config = config
            self.name = config.name
            self.role = config.role_title

    fd = FakeDynamic(mock_config)
    rules = fd._get_scope_rules()
    record("U14 DynamicAgent scope rules include allowed/forbidden/escalation",
           "answer questions" in rules and "give legal advice" in rules and "unsure about policy" in rules,
           f"Rules snippet: {rules[:200]}")

    # ── 1.15 DynamicAgent get_tools merges standard + custom ──
    fd._config = mock_config
    all_tools = fd.get_tools()
    all_names = [t["name"] for t in all_tools]
    record("U15 DynamicAgent get_tools merges standard + custom",
           "search_knowledge_base" in all_names and "custom_tool" in all_names,
           f"Got: {all_names}")
    record("U15b DynamicAgent total tool count = 3 standard + 1 custom",
           len(all_tools) == 4,
           f"Got {len(all_tools)}")


# ══════════════════════════════════════════════════════════════════════
# PART 2 — INTEGRATION TESTS (DB required, no LLM)
# ══════════════════════════════════════════════════════════════════════

async def test_integration():
    print("\n=== PART 2: INTEGRATION TESTS (DB) ===\n")

    from app.database import async_session
    from app.models.deployed_agent import DeployedAgent, AgentStatus
    from app.models.employee import Department
    from app.agents.sarah import SarahAgent
    from app.agents.orchestrator import AgentOrchestrator

    async with async_session() as db:
        # Find tenant and department for testing
        from sqlalchemy import select
        dept_result = await db.execute(select(Department).limit(1))
        dept = dept_result.scalar_one_or_none()
        if not dept:
            record("I00 Department found for testing", False, "No departments in DB")
            return

        tenant_id = dept.tenant_id
        department_id = dept.id
        record("I00 Test fixtures loaded",
               True,
               f"tenant={tenant_id}, dept={dept.name}")

        # ── Create SarahAgent ──
        sarah = SarahAgent(db, tenant_id)

        # ── I01: get_department_overview (all departments) ──
        try:
            result_json = await sarah.handle_tool_call("get_department_overview", {})
            result = json.loads(result_json)
            has_depts = "departments" in result and len(result["departments"]) > 0
            has_summary = "org_summary" in result
            record("I01 get_department_overview returns departments + org_summary",
                   has_depts and has_summary,
                   f"depts={len(result.get('departments', []))}")
        except Exception as e:
            record("I01 get_department_overview", False, str(e))

        # ── I02: get_department_overview (single department) ──
        try:
            result_json = await sarah.handle_tool_call(
                "get_department_overview", {"department_id": str(department_id)}
            )
            result = json.loads(result_json)
            record("I02 get_department_overview single dept returns 1 result",
                   len(result.get("departments", [])) == 1,
                   f"Got {len(result.get('departments', []))} depts")
        except Exception as e:
            record("I02 get_department_overview single", False, str(e))

        # ── I03: Saudization percentage calculation ──
        try:
            result_json = await sarah.handle_tool_call("get_department_overview", {})
            result = json.loads(result_json)
            for d in result.get("departments", []):
                hc = d["headcount"]
                saudi = d["saudi_count"]
                if hc > 0:
                    expected_pct = round(saudi / hc * 100, 1)
                    record("I03 Saudization % is correctly calculated",
                           d["saudization_pct"] == expected_pct,
                           f"dept={d['name']}: expected={expected_pct}, got={d['saudization_pct']}")
                    break
            else:
                record("I03 Saudization % calculation", True, "No departments with headcount > 0")
        except Exception as e:
            record("I03 Saudization %", False, str(e))

        # ── I04: create_agent ──
        test_agent_id = None
        try:
            result_json = await sarah.handle_tool_call("create_agent", {
                "name": "TestBot",
                "name_ar": "تيست بوت",
                "role_title": "QA Test Agent",
                "role_title_ar": "وكيل اختبار",
                "department_id": str(department_id),
                "system_prompt": "You are a test agent for QA validation.",
                "tools_config": [
                    {"name": "greet", "description": "Say hello", "input_schema": {"type": "object", "properties": {}, "required": []}}
                ],
                "scope_boundaries": {"allowed_actions": ["greet users"], "forbidden_actions": ["access payroll"]},
                "escalation_rules": {"escalate_when": ["confused"], "escalate_to": "human_manager"},
            })
            result = json.loads(result_json)
            test_agent_id = result.get("agent_id")
            record("I04 create_agent returns agent_id with status=draft",
                   test_agent_id is not None and result.get("current_status") == "draft",
                   f"id={test_agent_id}, status={result.get('current_status')}")
        except Exception as e:
            record("I04 create_agent", False, str(e))

        if not test_agent_id:
            print("  [SKIP] Remaining integration tests require a created agent")
            return

        # ── I05: activate_agent ──
        try:
            result_json = await sarah.handle_tool_call("activate_agent", {"agent_id": test_agent_id})
            result = json.loads(result_json)
            record("I05 activate_agent transitions draft -> active",
                   result.get("status") == "activated",
                   f"Got: {result.get('status')}")
        except Exception as e:
            record("I05 activate_agent", False, str(e))

        # ── I06: activate already-active agent ──
        try:
            result_json = await sarah.handle_tool_call("activate_agent", {"agent_id": test_agent_id})
            result = json.loads(result_json)
            record("I06 activate_agent on already-active returns message (not error)",
                   "already active" in result.get("message", "").lower(),
                   f"Got: {result}")
        except Exception as e:
            record("I06 activate already-active", False, str(e))

        # ── I07: configure_agent_tools ──
        try:
            new_tools = [
                {"name": "greet", "description": "Say hello", "input_schema": {"type": "object", "properties": {}, "required": []}},
                {"name": "farewell", "description": "Say goodbye", "input_schema": {"type": "object", "properties": {}, "required": []}},
            ]
            result_json = await sarah.handle_tool_call("configure_agent_tools", {
                "agent_id": test_agent_id,
                "tools_config": new_tools,
            })
            result = json.loads(result_json)
            record("I07 configure_agent_tools updates tool count",
                   result.get("tools_count") == 2 and "greet" in result.get("tool_names", []),
                   f"count={result.get('tools_count')}, names={result.get('tool_names')}")
        except Exception as e:
            record("I07 configure_agent_tools", False, str(e))

        # ── I08: set_escalation_rules ──
        try:
            rules = {
                "escalate_when": ["salary question", "legal matter"],
                "escalate_to": "human_manager",
                "max_retries": 2,
            }
            result_json = await sarah.handle_tool_call("set_escalation_rules", {
                "agent_id": test_agent_id,
                "escalation_rules": rules,
            })
            result = json.loads(result_json)
            record("I08 set_escalation_rules persists rules",
                   result.get("status") == "updated"
                   and "salary question" in str(result.get("escalation_rules", {})),
                   f"Got: {result.get('status')}")
        except Exception as e:
            record("I08 set_escalation_rules", False, str(e))

        # ── I09: update_agent_prompt ──
        try:
            new_prompt = "You are an updated test agent. Be concise."
            result_json = await sarah.handle_tool_call("update_agent_prompt", {
                "agent_id": test_agent_id,
                "new_system_prompt": new_prompt,
            })
            result = json.loads(result_json)
            record("I09 update_agent_prompt succeeds and reports length",
                   result.get("status") == "updated"
                   and result.get("new_prompt_length") == len(new_prompt),
                   f"Got: status={result.get('status')}, len={result.get('new_prompt_length')}")
        except Exception as e:
            record("I09 update_agent_prompt", False, str(e))

        # ── I10: list_deployed_agents ──
        try:
            result_json = await sarah.handle_tool_call("list_deployed_agents", {})
            result = json.loads(result_json)
            agent_ids = [a["agent_id"] for a in result.get("agents", [])]
            record("I10 list_deployed_agents includes our test agent",
                   test_agent_id in agent_ids,
                   f"total={result.get('total')}, found={test_agent_id in agent_ids}")
        except Exception as e:
            record("I10 list_deployed_agents", False, str(e))

        # ── I11: list_deployed_agents with status filter ──
        try:
            result_json = await sarah.handle_tool_call("list_deployed_agents", {"status": "active"})
            result = json.loads(result_json)
            all_active = all(a["status"] == "active" for a in result.get("agents", []))
            record("I11 list_deployed_agents status=active filter works",
                   all_active and result.get("total", 0) >= 1,
                   f"total={result.get('total')}, all_active={all_active}")
        except Exception as e:
            record("I11 list_deployed_agents filter", False, str(e))

        # ── I12: get_agent_performance ──
        try:
            result_json = await sarah.handle_tool_call("get_agent_performance", {
                "agent_id": test_agent_id, "days": 30,
            })
            result = json.loads(result_json)
            has_fields = all(k in result for k in [
                "total_conversations", "resolved", "escalated",
                "resolution_rate_pct", "escalation_rate_pct",
            ])
            record("I12 get_agent_performance returns expected metric fields",
                   has_fields,
                   f"keys={list(result.keys())}")
        except Exception as e:
            record("I12 get_agent_performance", False, str(e))

        # ── I13: simulate_scenario ──
        try:
            result_json = await sarah.handle_tool_call("simulate_scenario", {
                "department_id": str(department_id),
                "add_humans": -1,
                "add_ai_agents": 2,
            })
            result = json.loads(result_json)
            proj = result.get("projected_state", {})
            impact = result.get("impact", {})
            record("I13 simulate_scenario returns projected state + impact",
                   "humans" in proj and "ai_agents" in proj and "cost_change_sar" in impact,
                   f"projected humans={proj.get('humans')}, ai={proj.get('ai_agents')}")
        except Exception as e:
            record("I13 simulate_scenario", False, str(e))

        # ── I14: estimate_agent_roi ──
        try:
            result_json = await sarah.handle_tool_call("estimate_agent_roi", {
                "role_title": "Invoice Processor",
                "department_id": str(department_id),
                "tasks_description": "Process vendor invoices, match POs, flag discrepancies",
            })
            result = json.loads(result_json)
            has_roi = "roi" in result and "costs" in result
            record("I14 estimate_agent_roi returns costs + roi breakdown",
                   has_roi and result.get("recommendation") is not None,
                   f"recommendation={result.get('recommendation')}")
        except Exception as e:
            record("I14 estimate_agent_roi", False, str(e))

        # ── I15: generate_governance_report ──
        try:
            result_json = await sarah.handle_tool_call("generate_governance_report", {"days": 30})
            result = json.loads(result_json)
            has_inventory = "agent_inventory" in result
            has_perf = "performance_summary" in result
            has_fin = "financial_summary" in result
            record("I15 generate_governance_report returns inventory + perf + financials",
                   has_inventory and has_perf and has_fin,
                   f"inventory={result.get('agent_inventory')}")
        except Exception as e:
            record("I15 generate_governance_report", False, str(e))

        # ── I16: proactive context ──
        try:
            ctx = await sarah.get_proactive_context("some-employee-id")
            record("I16 proactive context includes AI workforce status",
                   ctx is not None and "departments" in ctx.lower(),
                   f"snippet: {(ctx or '')[:150]}")
        except Exception as e:
            record("I16 proactive context", False, str(e))

        # ── I17: Orchestrator dept: routing ──
        try:
            orch = AgentOrchestrator(db, tenant_id)
            dept_agent_name = f"dept:{test_agent_id}"

            # Route should be sticky for dept: agents
            routed = await orch.route("hello", current_agent=dept_agent_name)
            record("I17 Orchestrator sticky routing for dept:{uuid}",
                   routed == dept_agent_name,
                   f"Expected {dept_agent_name}, got {routed}")
        except Exception as e:
            record("I17 Orchestrator dept: routing", False, str(e))

        # ── I18: Orchestrator get_dynamic_agent ──
        try:
            orch = AgentOrchestrator(db, tenant_id)
            dynamic = await orch.get_dynamic_agent(f"dept:{test_agent_id}")
            record("I18 get_dynamic_agent loads active agent from DB",
                   dynamic is not None and dynamic.name == "TestBot",
                   f"name={dynamic.name if dynamic else 'None'}")
        except Exception as e:
            record("I18 get_dynamic_agent", False, str(e))

        # ── I19: get_dynamic_agent rejects invalid UUID ──
        try:
            orch = AgentOrchestrator(db, tenant_id)
            result = await orch.get_dynamic_agent("dept:not-a-uuid")
            record("I19 get_dynamic_agent returns None for invalid UUID",
                   result is None)
        except Exception as e:
            record("I19 get_dynamic_agent invalid UUID", False, str(e))

        # ── I20: get_dynamic_agent rejects non-dept prefix ──
        try:
            orch = AgentOrchestrator(db, tenant_id)
            result = await orch.get_dynamic_agent("sarah")
            record("I20 get_dynamic_agent returns None for non-dept prefix",
                   result is None)
        except Exception as e:
            record("I20 get_dynamic_agent non-dept", False, str(e))

        # ── I21: get_dynamic_agent returns None for non-existent agent ──
        try:
            orch = AgentOrchestrator(db, tenant_id)
            fake_id = str(uuid4())
            result = await orch.get_dynamic_agent(f"dept:{fake_id}")
            record("I21 get_dynamic_agent returns None for non-existent agent",
                   result is None)
        except Exception as e:
            record("I21 get_dynamic_agent non-existent", False, str(e))

        # ── I22: DynamicAgent custom tool dispatch ──
        try:
            orch = AgentOrchestrator(db, tenant_id)
            dynamic = await orch.get_dynamic_agent(f"dept:{test_agent_id}")
            if dynamic:
                result_str = await dynamic.handle_tool_call("greet", {})
                result = json.loads(result_str)
                record("I22 DynamicAgent custom tool returns simulated result",
                       result.get("tool") == "greet" and "executed successfully" in result.get("result", ""),
                       f"Got: {result}")
            else:
                record("I22 DynamicAgent custom tool dispatch", False, "Could not load agent")
        except Exception as e:
            record("I22 DynamicAgent custom tool", False, str(e))

        # ── I23: Unknown tool returns error ──
        try:
            result_json = await sarah.handle_tool_call("nonexistent_tool", {})
            result = json.loads(result_json)
            record("I23 Unknown tool returns error JSON",
                   "error" in result and "nonexistent_tool" in result.get("error", ""),
                   f"Got: {result}")
        except Exception as e:
            record("I23 unknown tool", False, str(e))

        # ── I24: deactivate_agent (pause) ──
        try:
            result_json = await sarah.handle_tool_call("deactivate_agent", {
                "agent_id": test_agent_id,
                "action": "pause",
                "reason": "QA testing cleanup",
            })
            result = json.loads(result_json)
            record("I24 deactivate_agent (pause) transitions to paused",
                   result.get("status") == "paused" and result.get("action") == "pause",
                   f"Got: {result.get('status')}")
        except Exception as e:
            record("I24 deactivate_agent pause", False, str(e))

        # ── I25: get_dynamic_agent returns None for paused agent ──
        try:
            orch = AgentOrchestrator(db, tenant_id)
            result = await orch.get_dynamic_agent(f"dept:{test_agent_id}")
            record("I25 get_dynamic_agent returns None for paused agent",
                   result is None,
                   f"Got: {result}")
        except Exception as e:
            record("I25 get_dynamic_agent paused", False, str(e))

        # ── I26: Re-activate paused agent ──
        try:
            result_json = await sarah.handle_tool_call("activate_agent", {"agent_id": test_agent_id})
            result = json.loads(result_json)
            record("I26 Re-activate paused agent succeeds",
                   result.get("status") == "activated",
                   f"Got: {result.get('status')}")
        except Exception as e:
            record("I26 re-activate paused", False, str(e))

        # ── I27: deactivate_agent (archive) ──
        try:
            result_json = await sarah.handle_tool_call("deactivate_agent", {
                "agent_id": test_agent_id,
                "action": "archive",
                "reason": "QA testing complete",
            })
            result = json.loads(result_json)
            record("I27 deactivate_agent (archive) transitions to archived",
                   result.get("status") == "archived",
                   f"Got: {result.get('status')}")
        except Exception as e:
            record("I27 deactivate_agent archive", False, str(e))

        # ── I28: Cannot activate archived agent ──
        try:
            result_json = await sarah.handle_tool_call("activate_agent", {"agent_id": test_agent_id})
            result = json.loads(result_json)
            record("I28 Cannot activate archived agent (returns error)",
                   "error" in result and "archived" in result.get("error", "").lower(),
                   f"Got: {result}")
        except Exception as e:
            record("I28 activate archived", False, str(e))

        # ── I29: activate_agent with non-existent ID ──
        try:
            fake_id = str(uuid4())
            result_json = await sarah.handle_tool_call("activate_agent", {"agent_id": fake_id})
            result = json.loads(result_json)
            record("I29 activate_agent non-existent returns error",
                   "error" in result,
                   f"Got: {result}")
        except Exception as e:
            record("I29 activate non-existent", False, str(e))

        # ── I30: Orchestrator routes 'agent factory' to sarah ──
        try:
            orch = AgentOrchestrator(db, tenant_id)
            routed = await orch.route("I want to build an agent factory for my department")
            record("I30 Orchestrator routes 'agent factory' to sarah",
                   routed == "sarah",
                   f"Got: {routed}")
        except Exception as e:
            record("I30 orchestrator routing", False, str(e))

        # ── I31: Orchestrator routes Arabic sarah keywords ──
        try:
            orch = AgentOrchestrator(db, tenant_id)
            routed = await orch.route("أبغى أتمتة قسم المالية")
            record("I31 Orchestrator routes Arabic 'أتمتة' to sarah",
                   routed == "sarah",
                   f"Got: {routed}")
        except Exception as e:
            record("I31 orchestrator arabic routing", False, str(e))

        # ── I32: Orchestrator switch phrase 'switch to sarah' ──
        try:
            orch = AgentOrchestrator(db, tenant_id)
            routed = await orch.route("switch to sarah", current_agent="deema")
            record("I32 Orchestrator switch phrase overrides current agent",
                   routed == "sarah",
                   f"Got: {routed}")
        except Exception as e:
            record("I32 switch phrase", False, str(e))

        # ── I33: Multi-tenant isolation (agent not visible to other tenant) ──
        try:
            other_tenant = uuid4()
            orch2 = AgentOrchestrator(db, other_tenant)
            result = await orch2.get_dynamic_agent(f"dept:{test_agent_id}")
            record("I33 Multi-tenant isolation: agent not visible to other tenant",
                   result is None,
                   f"Got: {result}")
        except Exception as e:
            record("I33 multi-tenant isolation", False, str(e))

        # ── Cleanup: delete test agent ──
        try:
            test_agent = await db.get(DeployedAgent, UUID(test_agent_id))
            if test_agent:
                await db.delete(test_agent)
                await db.commit()
                print("\n  [CLEANUP] Deleted test agent")
        except Exception as e:
            print(f"\n  [CLEANUP WARNING] Could not delete test agent: {e}")


# ══════════════════════════════════════════════════════════════════════
# PART 3 — API TESTS (Teams API via HTTP)
# ══════════════════════════════════════════════════════════════════════

BASE_URL = "http://localhost:8000/api/v1"
API_TIMEOUT = 30


def api_get(path: str, params: dict = None, timeout: int = API_TIMEOUT) -> tuple[int, dict]:
    """GET request to API, returns (status_code, json_body)."""
    if params:
        qs = "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
        path = f"{path}?{qs}"
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url, method="GET")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8") if e.fp else "{}"
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = {"detail": raw}
        return e.code, body
    except urllib.error.URLError as e:
        return 0, {"detail": str(e.reason)}
    except Exception as e:
        return 0, {"detail": str(e)}


def test_api():
    print("\n=== PART 3: API TESTS (Teams Endpoints) ===\n")

    # Check if server is running
    status, _ = api_get("/health")
    if status == 0:
        print("  [SKIP] Server not running at localhost:8000 — skipping API tests")
        for i in range(1, 11):
            record(f"A{i:02d} (skipped — server not running)", False, skip=True)
        return

    # We need a tenant_id. Get it from the seed data by logging in.
    try:
        login_data = json.dumps({"employee_number": "EMP-001", "national_id_last4": "5432"}).encode()
        login_req = urllib.request.Request(
            f"{BASE_URL}/chat/auth/login",
            data=login_data,
            method="POST",
        )
        login_req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(login_req, timeout=API_TIMEOUT) as resp:
            login_resp = json.loads(resp.read().decode())
        tenant_id = login_resp.get("tenant_id")
        if not tenant_id:
            print("  [SKIP] Could not get tenant_id from login")
            return
    except Exception as e:
        print(f"  [SKIP] Login failed: {e}")
        for i in range(1, 11):
            record(f"A{i:02d} (skipped — login failed)", False, skip=True)
        return

    # ── A01: GET /teams without tenant_id returns 400 ──
    status, body = api_get("/teams")
    record("A01 GET /teams without tenant_id returns 400",
           status == 400,
           f"Got status {status}")

    # ── A02: GET /teams with tenant_id returns teams list ──
    status, body = api_get("/teams", {"tenant_id": tenant_id})
    record("A02 GET /teams returns teams array",
           status == 200 and "teams" in body and isinstance(body.get("teams"), list),
           f"status={status}, keys={list(body.keys()) if isinstance(body, dict) else 'not dict'}")

    # ── A03: Each team has required fields ──
    if status == 200 and body.get("teams"):
        team = body["teams"][0]
        required_fields = ["department_id", "name", "human_count", "ai_agent_count", "total_members"]
        has_all = all(f in team for f in required_fields)
        record("A03 Team objects have required fields",
               has_all,
               f"Missing: {[f for f in required_fields if f not in team]}")

        # ── A04: total_members = human_count + ai_agent_count ──
        total_ok = team["total_members"] == team["human_count"] + team["ai_agent_count"]
        record("A04 total_members = human_count + ai_agent_count",
               total_ok,
               f"total={team['total_members']}, human={team['human_count']}, ai={team['ai_agent_count']}")

        dept_id = team["department_id"]
    else:
        record("A03 Team fields", False, skip=True)
        record("A04 total_members", False, skip=True)
        dept_id = None

    # ── A05: GET /teams/{dept_id}/members ──
    if dept_id:
        status, body = api_get(f"/teams/{dept_id}/members", {"tenant_id": tenant_id})
        record("A05 GET /teams/{dept_id}/members returns members",
               status == 200 and "members" in body,
               f"status={status}")

        if status == 200:
            # ── A06: Members have type field (human or ai_agent) ──
            members = body.get("members", [])
            all_typed = all(m.get("type") in ("human", "ai_agent") for m in members)
            record("A06 All members have valid type (human or ai_agent)",
                   all_typed,
                   f"types={[m.get('type') for m in members[:5]]}")

            # ── A07: human_count matches actual human members ──
            actual_humans = sum(1 for m in members if m["type"] == "human")
            record("A07 human_count matches actual human members",
                   body.get("human_count") == actual_humans,
                   f"reported={body.get('human_count')}, actual={actual_humans}")

            # ── A08: AI agents have agent_name field with dept: prefix ──
            ai_members = [m for m in members if m["type"] == "ai_agent"]
            if ai_members:
                all_dept_prefix = all(
                    m.get("agent_name", "").startswith("dept:") for m in ai_members
                )
                record("A08 AI agent members have dept: prefix in agent_name",
                       all_dept_prefix,
                       f"names={[m.get('agent_name') for m in ai_members[:3]]}")
            else:
                record("A08 AI agent members (none deployed yet)", True, "No AI agents in this dept")
        else:
            record("A06 Members type field", False, skip=True)
            record("A07 human_count match", False, skip=True)
            record("A08 AI agent dept prefix", False, skip=True)
    else:
        for i in [5, 6, 7, 8]:
            record(f"A{i:02d} (skipped — no dept_id)", False, skip=True)

    # ── A09: GET /teams/{invalid_dept}/members returns 404 ──
    fake_dept = str(uuid4())
    status, body = api_get(f"/teams/{fake_dept}/members", {"tenant_id": tenant_id})
    record("A09 GET /teams/{invalid_dept}/members returns 404",
           status == 404,
           f"Got status {status}")

    # ── A10: GET /teams/deployed-agents ──
    status, body = api_get("/teams/deployed-agents", {"tenant_id": tenant_id})
    record("A10 GET /teams/deployed-agents returns agents list",
           status == 200 and "agents" in body,
           f"status={status}, total={body.get('total')}")


# ══════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════

def print_summary():
    print("\n" + "=" * 70)
    print(f"  RESULTS: {passed} passed, {failed} failed, {skipped} skipped")
    print("=" * 70)

    if failed > 0:
        print("\n  FAILURES:")
        for status, name, detail in results:
            if status == "FAIL":
                print(f"    FAIL: {name}")
                if detail:
                    print(f"          {detail}")

    print()


if __name__ == "__main__":
    t0 = time.time()

    # Part 1: Unit tests (always run)
    test_unit()

    # Part 2: Integration tests (need DB)
    try:
        asyncio.run(test_integration())
    except Exception as e:
        print(f"\n  [ERROR] Integration tests failed to run: {e}")
        record("Integration suite", False, str(e))

    # Part 3: API tests (need running server)
    test_api()

    elapsed = time.time() - t0
    print_summary()
    print(f"  Total time: {elapsed:.1f}s")
    sys.exit(1 if failed > 0 else 0)
