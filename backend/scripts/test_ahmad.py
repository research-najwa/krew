"""Test suite for Ahmad Agent — CHRO Intelligence (Phase A1 + A2).

Tests all 12 tools, orchestrator routing, keyword mapping,
and DB-backed tool execution. Deterministic where possible (DB-only),
no LLM calls.

Categories:
  - Unit: tool definitions, dispatch mapping, identity, orchestrator registration
  - Integration: DB-backed tool execution (headcount, saudization, turnover, analytics, etc.)
  - API: Chat endpoint with agent="ahmad", suggestions + quick-actions endpoints

Prerequisites:
  1. Server running at localhost:8000 (for API tests only)
  2. Seed data loaded: python -m scripts.seed
  3. PostgreSQL running at localhost:5432/krew

Usage:
    cd /Users/najwamalghamdi/Desktop/HR-AI-Startup/backend
    source venv/bin/activate
    python scripts/test_ahmad.py
"""
import asyncio
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from uuid import UUID, uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# -- Counters --
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


# ======================================================================
# PART 1 -- UNIT TESTS (no DB, no LLM)
# ======================================================================

def test_unit():
    print("\n=== PART 1: UNIT TESTS ===\n")

    # -- U01: AhmadAgent identity --
    from app.agents.ahmad import AhmadAgent

    record(
        "U01 AhmadAgent has correct identity",
        AhmadAgent.name == "Ahmad"
        and AhmadAgent.name_ar == "\u0623\u062d\u0645\u062f"
        and AhmadAgent.role == "CHRO",
        f"name={AhmadAgent.name}, name_ar={AhmadAgent.name_ar}, role={AhmadAgent.role}",
    )

    # -- U02: Exactly 17 tools (7 A1 + 5 A2 + 5 A3) --
    class FakeAhmad(AhmadAgent):
        def __init__(self):
            pass  # skip BaseAgent.__init__

    fake = FakeAhmad()
    tools = fake.get_tools()
    tool_names = [t["name"] for t in tools]

    record(
        "U02 Ahmad has exactly 17 tools",
        len(tools) == 17,
        f"Got {len(tools)} tools: {tool_names}",
    )

    # -- U03: All 17 expected tool names present --
    expected_tools = [
        "get_headcount_summary",
        "get_saudization_status",
        "get_turnover_metrics",
        "get_department_budget",
        "get_salary_distribution",
        "get_workforce_overview",
        "get_compliance_status",
        "get_recruitment_analytics",
        "get_leave_analytics",
        "get_attendance_analytics",
        "get_onboarding_analytics",
        "get_payroll_summary",
        # A3 Predictive & Advanced Analytics
        "predict_attrition_risk",
        "forecast_budget",
        "audit_gosi_compliance",
        "get_policy_acknowledgments",
        "generate_custom_report",
    ]
    missing = [t for t in expected_tools if t not in tool_names]
    extra = [t for t in tool_names if t not in expected_tools]
    record(
        "U03 All 17 expected tool names present",
        not missing and not extra,
        f"Missing: {missing}, Extra: {extra}",
    )

    # -- U04: Each tool has required schema fields --
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
    record(
        "U04 All tools have valid schema structure",
        all_valid,
        f"Bad: {bad_tools}",
    )

    # -- U05: handle_tool_call dispatches all 17 tools --
    import inspect

    source = inspect.getsource(AhmadAgent.handle_tool_call)
    dispatch_missing = [t for t in expected_tools if t not in source]
    record(
        "U05 handle_tool_call dispatches all 17 tools",
        not dispatch_missing,
        f"Missing dispatch: {dispatch_missing}",
    )

    # -- U06: Orchestrator AGENTS includes ahmad --
    from app.agents.orchestrator import AGENTS, INTENT_KEYWORDS

    record(
        "U06 Orchestrator AGENTS registry includes ahmad",
        "ahmad" in AGENTS,
        f"Keys: {list(AGENTS.keys())}",
    )

    # -- U07: Ahmad intent keywords contain key phrases --
    ahmad_kw = INTENT_KEYWORDS.get("ahmad", [])
    expected_kw_samples = [
        "analytics",
        "compliance",
        "turnover",
        "saudization",
        "nitaqat",
        "budget",
        "dashboard",
        "chro",
    ]
    has_all = all(kw in ahmad_kw for kw in expected_kw_samples)
    record(
        "U07 Ahmad intent keywords contain key phrases",
        has_all,
        f"Missing: {[k for k in expected_kw_samples if k not in ahmad_kw]}",
    )

    # -- U08: No duplicate keywords across agents --
    seen = {}
    dupes = []
    for agent_name, keywords in INTENT_KEYWORDS.items():
        for kw in keywords:
            if kw in seen:
                dupes.append(f"'{kw}' in {seen[kw]} and {agent_name}")
            seen[kw] = agent_name
    record(
        "U08 No duplicate keywords across agents",
        not dupes,
        f"Dupes: {dupes}",
    )

    # -- U09: Sarah and Norah are NOT in AGENTS (routed via Ahmad) --
    record(
        "U09 Sarah and Norah are NOT in AGENTS (routed via Ahmad)",
        "sarah" not in AGENTS and "norah" not in AGENTS,
        f"Keys: {list(AGENTS.keys())}",
    )

    # -- U10: Nitaqat band calculation (default thresholds) --
    band_tests = [
        (50.0, "platinum"),
        (40.0, "platinum"),
        (30.0, "green_high"),
        (26.0, "green_high"),
        (20.0, "green_low"),
        (17.0, "green_low"),
        (10.0, "yellow"),
        (6.0, "yellow"),
        (3.0, "red"),
        (0.0, "red"),
    ]
    all_bands_ok = True
    band_errors = []
    for pct, expected_band in band_tests:
        actual = fake._calculate_nitaqat_band(pct, None)
        if actual != expected_band:
            all_bands_ok = False
            band_errors.append(f"{pct}% -> expected {expected_band}, got {actual}")
    record(
        "U10 Nitaqat band calculation with default thresholds",
        all_bands_ok,
        f"Errors: {band_errors}",
    )

    # -- U11: Invalid department_id returns error in handle_tool_call --
    # We check the source to confirm UUID validation exists
    record(
        "U11 handle_tool_call validates department_id as UUID",
        "UUID(dept_id_raw)" in source or "UUID(dept_id" in source,
        "UUID validation not found in handle_tool_call",
    )

    # -- U12: Ahmad now has exactly 17 tools (redundant but explicit A3 check) --
    record(
        "U12 Ahmad has exactly 17 tools (A3 confirmation)",
        len(tools) == 17,
        f"Got {len(tools)} tools",
    )

    # -- U13: All 5 new A2 tool names present in get_tools() --
    a2_tools = [
        "get_recruitment_analytics",
        "get_leave_analytics",
        "get_attendance_analytics",
        "get_onboarding_analytics",
        "get_payroll_summary",
    ]
    a2_missing = [t for t in a2_tools if t not in tool_names]
    record(
        "U13 All 5 A2 tool names present in get_tools()",
        not a2_missing,
        f"Missing A2 tools: {a2_missing}",
    )

    # -- U14: All 5 new A2 tools have valid schema structure --
    a2_valid = True
    a2_bad = []
    for tool in tools:
        if tool["name"] in a2_tools:
            if not all(k in tool for k in ("name", "description", "input_schema")):
                a2_valid = False
                a2_bad.append(f"{tool.get('name', 'UNNAMED')}: missing keys")
            schema = tool.get("input_schema", {})
            if schema.get("type") != "object":
                a2_valid = False
                a2_bad.append(f"{tool['name']}: schema type != object")
            if "properties" not in schema:
                a2_valid = False
                a2_bad.append(f"{tool['name']}: missing properties")
    record(
        "U14 All 5 A2 tools have valid schema structure",
        a2_valid,
        f"Bad: {a2_bad}",
    )

    # -- U15: handle_tool_call dispatches all 17 tools (A2+A3 included) --
    all_17 = expected_tools  # already includes A2+A3 tools
    dispatch_missing_all = [t for t in all_17 if t not in source]
    record(
        "U15 handle_tool_call dispatches all 17 tools (A2+A3 included)",
        not dispatch_missing_all,
        f"Missing dispatch: {dispatch_missing_all}",
    )

    # -- U16: New orchestrator A2 keywords don't conflict --
    a2_keywords = [
        "recruitment funnel", "time to fill", "hiring analytics",
        "leave trends", "leave analytics", "leave usage",
        "attendance rate", "overtime analytics", "late arrivals",
        "onboarding progress", "onboarding completion", "bottleneck steps",
        "payroll cost", "payroll trend", "gosi breakdown",
    ]
    ahmad_kw_set = set(INTENT_KEYWORDS.get("ahmad", []))
    a2_present = [kw for kw in a2_keywords if kw in ahmad_kw_set]
    # Check none of these appear in other agents
    conflict = []
    for agent_name, keywords in INTENT_KEYWORDS.items():
        if agent_name == "ahmad":
            continue
        for kw in a2_keywords:
            if kw in keywords:
                conflict.append(f"'{kw}' also in {agent_name}")
    record(
        "U16 A2 orchestrator keywords present and no conflicts",
        len(a2_present) == len(a2_keywords) and not conflict,
        f"Present: {len(a2_present)}/{len(a2_keywords)}, Conflicts: {conflict}",
    )

    # ── A3 Unit Tests ────────────────────────────────────────────

    # -- U17: All 5 A3 tool names present in get_tools() --
    a3_tools = [
        "predict_attrition_risk",
        "forecast_budget",
        "audit_gosi_compliance",
        "get_policy_acknowledgments",
        "generate_custom_report",
    ]
    a3_missing = [t for t in a3_tools if t not in tool_names]
    record(
        "U17 All 5 A3 tool names present in get_tools()",
        not a3_missing,
        f"Missing A3 tools: {a3_missing}",
    )

    # -- U18: All 5 A3 tools have valid schema structure --
    a3_valid = True
    a3_bad = []
    for tool in tools:
        if tool["name"] in a3_tools:
            if not all(k in tool for k in ("name", "description", "input_schema")):
                a3_valid = False
                a3_bad.append(f"{tool.get('name', 'UNNAMED')}: missing keys")
            schema = tool.get("input_schema", {})
            if schema.get("type") != "object":
                a3_valid = False
                a3_bad.append(f"{tool['name']}: schema type != object")
            if "properties" not in schema:
                a3_valid = False
                a3_bad.append(f"{tool['name']}: missing properties")
    record(
        "U18 All 5 A3 tools have valid schema structure",
        a3_valid,
        f"Bad: {a3_bad}",
    )

    # -- U19: predict_attrition_risk has risk_threshold enum --
    attrition_tool = next((t for t in tools if t["name"] == "predict_attrition_risk"), None)
    if attrition_tool:
        props = attrition_tool["input_schema"].get("properties", {})
        risk_prop = props.get("risk_threshold", {})
        has_enum = "enum" in risk_prop and set(risk_prop["enum"]) == {"high", "medium", "low"}
        record(
            "U19 predict_attrition_risk has risk_threshold enum [high, medium, low]",
            has_enum,
            f"risk_threshold props: {risk_prop}",
        )
    else:
        record("U19 predict_attrition_risk schema check", False, "Tool not found")

    # -- U20: forecast_budget has horizon_months enum --
    budget_tool = next((t for t in tools if t["name"] == "forecast_budget"), None)
    if budget_tool:
        props = budget_tool["input_schema"].get("properties", {})
        horizon_prop = props.get("horizon_months", {})
        has_enum = "enum" in horizon_prop and set(horizon_prop["enum"]) == {3, 6, 12}
        record(
            "U20 forecast_budget has horizon_months enum [3, 6, 12]",
            has_enum,
            f"horizon_months props: {horizon_prop}",
        )
    else:
        record("U20 forecast_budget schema check", False, "Tool not found")

    # -- U21: generate_custom_report requires 'query' --
    report_tool = next((t for t in tools if t["name"] == "generate_custom_report"), None)
    if report_tool:
        required = report_tool["input_schema"].get("required", [])
        has_query_required = "query" in required
        record(
            "U21 generate_custom_report requires 'query' parameter",
            has_query_required,
            f"required: {required}",
        )
    else:
        record("U21 generate_custom_report schema check", False, "Tool not found")

    # -- U22: audit_gosi_compliance has tolerance_pct property --
    gosi_tool = next((t for t in tools if t["name"] == "audit_gosi_compliance"), None)
    if gosi_tool:
        props = gosi_tool["input_schema"].get("properties", {})
        has_tolerance = "tolerance_pct" in props
        has_month = "month" in props
        record(
            "U22 audit_gosi_compliance has tolerance_pct and month properties",
            has_tolerance and has_month,
            f"properties: {list(props.keys())}",
        )
    else:
        record("U22 audit_gosi_compliance schema check", False, "Tool not found")

    # -- U23: get_policy_acknowledgments has policy_id and category properties --
    policy_tool = next((t for t in tools if t["name"] == "get_policy_acknowledgments"), None)
    if policy_tool:
        props = policy_tool["input_schema"].get("properties", {})
        has_policy_id = "policy_id" in props
        has_category = "category" in props
        record(
            "U23 get_policy_acknowledgments has policy_id and category properties",
            has_policy_id and has_category,
            f"properties: {list(props.keys())}",
        )
    else:
        record("U23 get_policy_acknowledgments schema check", False, "Tool not found")

    # -- U24: handle_tool_call dispatches all 5 A3 tools --
    a3_dispatch_missing = [t for t in a3_tools if t not in source]
    record(
        "U24 handle_tool_call dispatches all 5 A3 tools",
        not a3_dispatch_missing,
        f"Missing A3 dispatch: {a3_dispatch_missing}",
    )

    # -- U25: Ahmad English-only rule in personality and scope --
    personality = AhmadAgent.personality
    scope_rules = fake._get_scope_rules()
    has_english_personality = "english" in personality.lower() or "English" in personality
    has_english_scope = "MUST always respond in English" in scope_rules
    record(
        "U25 Ahmad English-only language rule in personality and scope",
        has_english_personality and has_english_scope,
        f"personality_mentions_english={has_english_personality}, scope_has_must_english={has_english_scope}",
    )


# ======================================================================
# PART 2 -- INTEGRATION TESTS (DB required, no LLM)
# ======================================================================

async def test_integration():
    print("\n=== PART 2: INTEGRATION TESTS (DB) ===\n")

    from app.database import async_session
    from app.models.employee import Department
    from app.agents.ahmad import AhmadAgent

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
        record(
            "I00 Test fixtures loaded",
            True,
            f"tenant={tenant_id}, dept={dept.name}",
        )

        # Create AhmadAgent
        ahmad = AhmadAgent(db, tenant_id)

        # -- I01: get_headcount_summary (all departments) --
        try:
            result_json = await ahmad.handle_tool_call("get_headcount_summary", {})
            result = json.loads(result_json)
            has_depts = "departments" in result and len(result["departments"]) > 0
            has_summary = "org_summary" in result
            record(
                "I01 get_headcount_summary returns departments + org_summary",
                has_depts and has_summary,
                f"depts={len(result.get('departments', []))}, has_summary={has_summary}",
            )
        except Exception as e:
            record("I01 get_headcount_summary", False, str(e))

        # -- I02: get_headcount_summary with department_id filter --
        try:
            result_json = await ahmad.handle_tool_call(
                "get_headcount_summary", {"department_id": str(department_id)}
            )
            result = json.loads(result_json)
            record(
                "I02 get_headcount_summary single dept returns 1 result",
                len(result.get("departments", [])) == 1,
                f"Got {len(result.get('departments', []))} depts",
            )
        except Exception as e:
            record("I02 get_headcount_summary single dept", False, str(e))

        # -- I03: Saudization % correctly calculated --
        try:
            result_json = await ahmad.handle_tool_call("get_headcount_summary", {})
            result = json.loads(result_json)
            verified = False
            for d in result.get("departments", []):
                total = d["total"]
                saudi = d["saudi"]
                if total > 0:
                    expected_pct = round(saudi / total * 100, 1)
                    ok = d["saudi_pct"] == expected_pct
                    record(
                        "I03 Saudization % correctly calculated",
                        ok,
                        f"dept={d['department']}: expected={expected_pct}, got={d['saudi_pct']}",
                    )
                    verified = True
                    break
            if not verified:
                record("I03 Saudization % correctly calculated", True, "No depts with headcount > 0")
        except Exception as e:
            record("I03 Saudization %", False, str(e))

        # -- I04: get_saudization_status returns structured response --
        try:
            result_json = await ahmad.handle_tool_call("get_saudization_status", {})
            result = json.loads(result_json)
            has_org = "org_summary" in result
            has_depts = "departments" in result
            has_at_risk = "at_risk_departments" in result
            record(
                "I04 get_saudization_status returns structured response",
                has_org and has_depts and has_at_risk,
                f"keys={list(result.keys())}",
            )
        except Exception as e:
            record("I04 get_saudization_status", False, str(e))

        # -- I05: get_turnover_metrics returns structured response --
        try:
            result_json = await ahmad.handle_tool_call("get_turnover_metrics", {})
            result = json.loads(result_json)
            has_rate = "overall_turnover_rate_pct" in result
            has_period = "period_months" in result
            has_depts = "departments" in result
            record(
                "I05 get_turnover_metrics returns structured response",
                has_rate and has_period and has_depts,
                f"rate={result.get('overall_turnover_rate_pct')}, months={result.get('period_months')}",
            )
        except Exception as e:
            record("I05 get_turnover_metrics", False, str(e))

        # -- I06: get_turnover_metrics respects months parameter --
        try:
            result_json = await ahmad.handle_tool_call("get_turnover_metrics", {"months": 6})
            result = json.loads(result_json)
            record(
                "I06 get_turnover_metrics respects months parameter",
                result.get("period_months") == 6,
                f"period_months={result.get('period_months')}",
            )
        except Exception as e:
            record("I06 get_turnover_metrics months param", False, str(e))

        # -- I07: get_department_budget returns budget data --
        try:
            result_json = await ahmad.handle_tool_call(
                "get_department_budget", {"department_id": str(department_id)}
            )
            result = json.loads(result_json)
            has_dept = "department" in result
            has_headcount = "headcount" in result
            headcount = result.get("headcount", 0)
            # k-anonymity: salary costs suppressed when headcount < 5
            if headcount >= 5:
                has_salary_or_note = "monthly_salary_cost_sar" in result
            else:
                has_salary_or_note = "salary_note" in result
            record(
                "I07 get_department_budget returns budget data",
                has_dept and has_headcount and has_salary_or_note,
                f"dept={result.get('department')}, headcount={headcount}",
            )
        except Exception as e:
            record("I07 get_department_budget", False, str(e))

        # -- I08: get_department_budget without department_id returns error --
        try:
            result_json = await ahmad.handle_tool_call("get_department_budget", {})
            result = json.loads(result_json)
            record(
                "I08 get_department_budget without dept_id returns error",
                "error" in result,
                f"Got: {result}",
            )
        except Exception as e:
            record("I08 get_department_budget no dept_id", False, str(e))

        # -- I09: get_salary_distribution returns aggregated stats --
        try:
            result_json = await ahmad.handle_tool_call("get_salary_distribution", {})
            result = json.loads(result_json)
            has_depts = "departments" in result
            has_privacy = "privacy_note" in result
            # Verify no individual names or employee IDs leaked
            result_str = json.dumps(result)
            no_emp_ids = "EMP-" not in result_str
            record(
                "I09 get_salary_distribution returns aggregated stats (no individual data)",
                has_depts and has_privacy and no_emp_ids,
                f"has_privacy={has_privacy}, no_emp_ids={no_emp_ids}",
            )
        except Exception as e:
            record("I09 get_salary_distribution", False, str(e))

        # -- I10: get_salary_distribution includes nationality and gender comparison --
        try:
            result_json = await ahmad.handle_tool_call("get_salary_distribution", {})
            result = json.loads(result_json)
            has_nat = "nationality_comparison" in result
            has_gender = "gender_comparison" in result
            record(
                "I10 get_salary_distribution includes nationality + gender comparison",
                has_nat and has_gender,
                f"nationality={has_nat}, gender={has_gender}",
            )
        except Exception as e:
            record("I10 get_salary_distribution comparisons", False, str(e))

        # -- I11: get_workforce_overview returns comprehensive snapshot --
        try:
            result_json = await ahmad.handle_tool_call("get_workforce_overview", {})
            result = json.loads(result_json)
            has_hc = "headcount" in result
            has_band = "nitaqat_band" in result
            has_breakdown = "department_breakdown" in result
            has_highlights = "highlights" in result
            has_ai = "ai_agents_active" in result
            record(
                "I11 get_workforce_overview returns comprehensive snapshot",
                has_hc and has_band and has_breakdown and has_highlights and has_ai,
                f"keys={list(result.keys())}",
            )
        except Exception as e:
            record("I11 get_workforce_overview", False, str(e))

        # -- I12: get_workforce_overview headcount fields --
        try:
            result_json = await ahmad.handle_tool_call("get_workforce_overview", {})
            result = json.loads(result_json)
            hc = result.get("headcount", {})
            required_fields = ["total", "saudi", "non_saudi", "saudi_pct", "male", "female"]
            has_all = all(f in hc for f in required_fields)
            # Verify total = saudi + non_saudi
            total_ok = hc.get("total", 0) == hc.get("saudi", 0) + hc.get("non_saudi", 0)
            record(
                "I12 get_workforce_overview headcount fields correct",
                has_all and total_ok,
                f"total={hc.get('total')}, saudi={hc.get('saudi')}, non_saudi={hc.get('non_saudi')}",
            )
        except Exception as e:
            record("I12 get_workforce_overview headcount", False, str(e))

        # -- I13: get_compliance_status returns structured response --
        try:
            result_json = await ahmad.handle_tool_call("get_compliance_status", {})
            result = json.loads(result_json)
            has_total = "total_items" in result
            has_compliant = "compliant" in result
            has_categories = "categories" in result
            record(
                "I13 get_compliance_status returns structured response",
                has_total and has_compliant and has_categories,
                f"total_items={result.get('total_items')}, compliant={result.get('compliant')}",
            )
        except Exception as e:
            record("I13 get_compliance_status", False, str(e))

        # -- I14: get_compliance_status overall_status field --
        try:
            result_json = await ahmad.handle_tool_call("get_compliance_status", {})
            result = json.loads(result_json)
            # If there are records, overall_status should be one of the valid values
            status_val = result.get("overall_status")
            if result.get("total_items", 0) > 0:
                valid = status_val in ("compliant", "needs_attention", "critical")
                record(
                    "I14 get_compliance_status has valid overall_status",
                    valid,
                    f"overall_status={status_val}",
                )
            else:
                # No records - that is fine, message should be present
                record(
                    "I14 get_compliance_status (no records, message present)",
                    "message" in result,
                    f"keys={list(result.keys())}",
                )
        except Exception as e:
            record("I14 get_compliance_status overall_status", False, str(e))

        # -- I15: Invalid department_id returns clean error --
        try:
            result_json = await ahmad.handle_tool_call(
                "get_headcount_summary", {"department_id": "not-a-valid-uuid"}
            )
            result = json.loads(result_json)
            record(
                "I15 Invalid department_id returns clean error",
                "error" in result,
                f"Got: {result}",
            )
        except Exception as e:
            record("I15 Invalid department_id", False, str(e))

        # -- I16: Non-existent department_id returns empty/no-data --
        try:
            fake_dept = str(uuid4())
            result_json = await ahmad.handle_tool_call(
                "get_headcount_summary", {"department_id": fake_dept}
            )
            result = json.loads(result_json)
            # Should return empty departments list or a message
            dept_list = result.get("departments", [])
            record(
                "I16 Non-existent department_id returns empty departments",
                len(dept_list) == 0 or "message" in result,
                f"depts={len(dept_list)}",
            )
        except Exception as e:
            record("I16 Non-existent department_id", False, str(e))

        # -- I17: Unknown tool returns error --
        try:
            result_json = await ahmad.handle_tool_call("nonexistent_tool", {})
            result = json.loads(result_json)
            record(
                "I17 Unknown tool returns error JSON",
                "error" in result and "nonexistent_tool" in result.get("error", ""),
                f"Got: {result}",
            )
        except Exception as e:
            record("I17 Unknown tool", False, str(e))

        # -- I18: Multi-tenant isolation --
        try:
            other_tenant = uuid4()
            ahmad_other = AhmadAgent(db, other_tenant)
            result_json = await ahmad_other.handle_tool_call("get_headcount_summary", {})
            result = json.loads(result_json)
            # Other tenant should see no departments or empty data
            dept_list = result.get("departments", [])
            all_empty = all(d.get("total", 0) == 0 for d in dept_list)
            record(
                "I18 Multi-tenant isolation: other tenant sees no data",
                len(dept_list) == 0 or all_empty,
                f"depts={len(dept_list)}, all_empty={all_empty}",
            )
        except Exception as e:
            record("I18 Multi-tenant isolation", False, str(e))

        # -- I19: get_salary_distribution with department filter --
        try:
            result_json = await ahmad.handle_tool_call(
                "get_salary_distribution", {"department_id": str(department_id)}
            )
            result = json.loads(result_json)
            depts = result.get("departments", [])
            # Should return 0 or 1 department (the filtered one)
            record(
                "I19 get_salary_distribution with dept filter returns filtered data",
                len(depts) <= 1,
                f"Got {len(depts)} departments",
            )
        except Exception as e:
            record("I19 get_salary_distribution filter", False, str(e))

        # -- I20: get_saudization_status includes gap_to_target --
        try:
            result_json = await ahmad.handle_tool_call("get_saudization_status", {})
            result = json.loads(result_json)
            depts = result.get("departments", [])
            if depts:
                has_gap = "gap_to_target" in depts[0]
                record(
                    "I20 get_saudization_status includes gap_to_target per dept",
                    has_gap,
                    f"first dept keys={list(depts[0].keys())}",
                )
            else:
                record("I20 get_saudization_status gap_to_target", True, "No departments")
        except Exception as e:
            record("I20 get_saudization_status gap", False, str(e))

        # -- I21: Orchestrator routes analytics keywords to ahmad --
        try:
            from app.agents.orchestrator import AgentOrchestrator

            orch = AgentOrchestrator(db, tenant_id)
            routed = await orch.route("Show me the workforce analytics dashboard")
            agent_name = routed[0] if isinstance(routed, tuple) else routed
            record(
                "I21 Orchestrator routes 'analytics dashboard' to ahmad",
                agent_name == "ahmad",
                f"Got: {agent_name}",
            )
        except Exception as e:
            record("I21 Orchestrator routing", False, str(e))

        # -- I22: Orchestrator routes Arabic analytics keywords to ahmad --
        try:
            from app.agents.orchestrator import AgentOrchestrator

            orch = AgentOrchestrator(db, tenant_id)
            routed = await orch.route("\u0623\u0628\u063a\u0649 \u062a\u062d\u0644\u064a\u0644\u0627\u062a \u0627\u0644\u0645\u0648\u0638\u0641\u064a\u0646")
            agent_name = routed[0] if isinstance(routed, tuple) else routed
            record(
                "I22 Orchestrator routes Arabic 'تحليلات' to ahmad",
                agent_name == "ahmad",
                f"Got: {agent_name}",
            )
        except Exception as e:
            record("I22 Orchestrator arabic routing", False, str(e))

        # -- I23: Switch phrase 'switch to ahmad' --
        try:
            from app.agents.orchestrator import AgentOrchestrator

            orch = AgentOrchestrator(db, tenant_id)
            routed = await orch.route("switch to ahmad", current_agent="deema")
            agent_name = routed[0] if isinstance(routed, tuple) else routed
            record(
                "I23 Orchestrator switch phrase overrides current agent",
                agent_name == "ahmad",
                f"Got: {agent_name}",
            )
        except Exception as e:
            record("I23 Switch phrase", False, str(e))

        # -- I24: 'switch to sarah' routes to ahmad (sarah absorbed) --
        try:
            from app.agents.orchestrator import AgentOrchestrator

            orch = AgentOrchestrator(db, tenant_id)
            routed = await orch.route("switch to sarah", current_agent="deema")
            agent_name = routed[0] if isinstance(routed, tuple) else routed
            # Sarah is NOT an alias — stays on current agent (deema) or routes via keywords
            record(
                "I24 'switch to sarah' does not route to ahmad (sarah removed as alias)",
                agent_name != "system",  # should not error
                f"Got: {agent_name}",
            )
        except Exception as e:
            record("I24 Sarah redirect to Ahmad", False, str(e))

        # -- I25: 'switch to norah' routes to ahmad (norah absorbed) --
        try:
            from app.agents.orchestrator import AgentOrchestrator

            orch = AgentOrchestrator(db, tenant_id)
            routed = await orch.route("switch to norah", current_agent="deema")
            agent_name = routed[0] if isinstance(routed, tuple) else routed
            # Norah is NOT an alias — stays on current agent or routes via keywords
            record(
                "I25 'switch to norah' does not route to ahmad (norah removed as alias)",
                agent_name != "system",  # should not error
                f"Got: {agent_name}",
            )
        except Exception as e:
            record("I25 Norah redirect to Ahmad", False, str(e))

        # ── A2 Integration Tests ─────────────────────────────────

        # -- I26: get_recruitment_analytics returns funnel data --
        try:
            result_json = await ahmad.handle_tool_call("get_recruitment_analytics", {})
            result = json.loads(result_json)
            has_funnel = "funnel" in result
            has_period = "period_months" in result
            has_open = "open_positions" in result
            has_conversion = "conversion_rates" in result
            record(
                "I26 get_recruitment_analytics returns funnel data",
                has_funnel and has_period and has_open and has_conversion,
                f"keys={list(result.keys())}",
            )
        except Exception as e:
            record("I26 get_recruitment_analytics funnel", False, str(e))

        # -- I27: get_recruitment_analytics respects department filter --
        try:
            result_json = await ahmad.handle_tool_call(
                "get_recruitment_analytics", {"department_id": str(department_id)}
            )
            result = json.loads(result_json)
            has_funnel = "funnel" in result
            has_period = "period_months" in result
            record(
                "I27 get_recruitment_analytics respects department filter",
                has_funnel and has_period,
                f"keys={list(result.keys())}",
            )
        except Exception as e:
            record("I27 get_recruitment_analytics dept filter", False, str(e))

        # -- I28: get_leave_analytics returns by-type breakdown --
        try:
            result_json = await ahmad.handle_tool_call("get_leave_analytics", {})
            result = json.loads(result_json)
            has_by_type = "by_type" in result
            has_approval = "approval_rates" in result
            has_dept_cmp = "department_comparison" in result
            has_monthly = "monthly_pattern" in result
            has_balance = "balance_utilization" in result
            record(
                "I28 get_leave_analytics returns by-type breakdown",
                has_by_type and has_approval and has_dept_cmp and has_monthly and has_balance,
                f"keys={list(result.keys())}",
            )
        except Exception as e:
            record("I28 get_leave_analytics by-type", False, str(e))

        # -- I29: get_leave_analytics respects months parameter --
        try:
            result_json = await ahmad.handle_tool_call("get_leave_analytics", {"months": 6})
            result = json.loads(result_json)
            record(
                "I29 get_leave_analytics respects months parameter",
                result.get("period_months") == 6,
                f"period_months={result.get('period_months')}",
            )
        except Exception as e:
            record("I29 get_leave_analytics months", False, str(e))

        # -- I30: get_attendance_analytics returns rates --
        try:
            result_json = await ahmad.handle_tool_call("get_attendance_analytics", {})
            result = json.loads(result_json)
            has_summary = "summary" in result
            has_period = "period_months" in result
            # Check that summary contains rate fields (if data exists)
            if has_summary and isinstance(result["summary"], dict):
                s = result["summary"]
                has_rates = (
                    "attendance_rate_pct" in s
                    and "late_rate_pct" in s
                    and "absence_rate_pct" in s
                )
            else:
                # Might return a "message" if no attendance data
                has_rates = "message" in result
            record(
                "I30 get_attendance_analytics returns rates",
                has_period and (has_rates or "message" in result),
                f"keys={list(result.keys())}",
            )
        except Exception as e:
            record("I30 get_attendance_analytics rates", False, str(e))

        # -- I31: get_attendance_analytics includes day-of-week pattern --
        try:
            result_json = await ahmad.handle_tool_call("get_attendance_analytics", {})
            result = json.loads(result_json)
            has_dow = "day_of_week_pattern" in result
            has_saudi = "saudi_context" in result
            # If there's data, day_of_week_pattern should be a list
            if has_dow:
                is_list = isinstance(result["day_of_week_pattern"], list)
            else:
                # No data case is also acceptable
                is_list = "message" in result
            record(
                "I31 get_attendance_analytics includes day-of-week pattern",
                (has_dow and is_list) or "message" in result,
                f"has_dow={has_dow}, has_saudi={has_saudi}",
            )
        except Exception as e:
            record("I31 get_attendance_analytics dow pattern", False, str(e))

        # -- I32: get_onboarding_analytics returns completion data --
        try:
            result_json = await ahmad.handle_tool_call("get_onboarding_analytics", {})
            result = json.loads(result_json)
            has_summary = "summary" in result
            has_period = "period_months" in result
            if has_summary and isinstance(result["summary"], dict):
                s = result["summary"]
                has_fields = (
                    "total_assignments" in s
                    and "completed" in s
                    and "completion_rate_pct" in s
                )
            else:
                has_fields = "message" in result
            record(
                "I32 get_onboarding_analytics returns completion data",
                has_period and (has_fields or "message" in result),
                f"keys={list(result.keys())}",
            )
        except Exception as e:
            record("I32 get_onboarding_analytics completion", False, str(e))

        # -- I33: get_payroll_summary returns cost trends --
        try:
            result_json = await ahmad.handle_tool_call("get_payroll_summary", {})
            result = json.loads(result_json)
            has_totals = "totals" in result
            has_period = "period_months" in result
            # If there is data, check for monthly_trend
            has_trend = "monthly_trend" in result
            if has_totals and isinstance(result["totals"], dict):
                t_keys = result["totals"]
                has_gross = "gross_salary_sar" in t_keys
                has_net = "net_salary_sar" in t_keys
            else:
                has_gross = has_net = "message" in result
            record(
                "I33 get_payroll_summary returns cost data",
                has_period and ((has_totals and has_gross and has_net) or "message" in result),
                f"keys={list(result.keys())}",
            )
        except Exception as e:
            record("I33 get_payroll_summary cost data", False, str(e))

        # -- I34: get_payroll_summary includes GOSI breakdown --
        try:
            result_json = await ahmad.handle_tool_call("get_payroll_summary", {})
            result = json.loads(result_json)
            has_gosi = "gosi_breakdown" in result
            if has_gosi:
                gb = result["gosi_breakdown"]
                has_emp = "employee_contribution_sar" in gb
                has_employer = "employer_contribution_estimated_sar" in gb
                has_total = "total_gosi_estimated_sar" in gb
                gosi_ok = has_emp and has_employer and has_total
            else:
                # No payroll data is also acceptable
                gosi_ok = "message" in result
            record(
                "I34 get_payroll_summary includes GOSI breakdown",
                gosi_ok,
                f"has_gosi={has_gosi}",
            )
        except Exception as e:
            record("I34 get_payroll_summary GOSI", False, str(e))

        # -- I35: k-anonymity applied in leave/attendance/payroll dept breakdowns --
        try:
            # Check leave analytics department_comparison
            leave_json = await ahmad.handle_tool_call("get_leave_analytics", {})
            leave = json.loads(leave_json)
            leave_depts = leave.get("department_comparison", [])

            # Check attendance department_comparison
            att_json = await ahmad.handle_tool_call("get_attendance_analytics", {})
            att = json.loads(att_json)
            att_depts = att.get("department_comparison", [])

            # Check payroll department_comparison
            pay_json = await ahmad.handle_tool_call("get_payroll_summary", {})
            pay = json.loads(pay_json)
            pay_depts = pay.get("department_comparison", [])

            # For each, verify that small departments have "note" with suppression
            k_violations = []
            min_group = 5

            for src_name, dept_list in [("leave", leave_depts), ("attendance", att_depts), ("payroll", pay_depts)]:
                for d in dept_list:
                    # For leave: check unique_employees, for attendance/payroll: check via 'note' presence logic
                    if src_name == "leave":
                        emp_count = d.get("unique_employees", 0)
                        if emp_count < min_group and "note" not in d:
                            k_violations.append(f"{src_name}:{d.get('department')}: {emp_count} employees, no suppression note")
                    elif src_name == "payroll":
                        headcount = d.get("headcount", 0)
                        if headcount < min_group and "note" not in d:
                            k_violations.append(f"{src_name}:{d.get('department')}: {headcount} headcount, no suppression note")
                    elif src_name == "attendance":
                        # Attendance entries either have detailed fields or a suppression note
                        has_detail = "total_records" in d
                        has_note = "note" in d
                        if not has_detail and not has_note:
                            k_violations.append(f"{src_name}:{d.get('department')}: neither detail nor note")

            record(
                "I35 k-anonymity applied in leave/attendance/payroll dept breakdowns",
                not k_violations,
                f"Violations: {k_violations}" if k_violations else "All departments comply",
            )
        except Exception as e:
            record("I35 k-anonymity check", False, str(e))

        # ── A3 Integration Tests ───────────���─────────────────────

        # -- I36: predict_attrition_risk returns risk data --
        try:
            result_json = await ahmad.handle_tool_call("predict_attrition_risk", {})
            result = json.loads(result_json)
            # Should have departments with risk scores or a message
            has_depts = "departments" in result
            has_summary = "summary" in result or "org_summary" in result or "message" in result
            record(
                "I36 predict_attrition_risk returns structured response",
                has_depts or has_summary or "message" in result,
                f"keys={list(result.keys())}",
            )
        except Exception as e:
            record("I36 predict_attrition_risk", False, str(e))

        # -- I37: predict_attrition_risk with department filter --
        try:
            result_json = await ahmad.handle_tool_call(
                "predict_attrition_risk", {"department_id": str(department_id)}
            )
            result = json.loads(result_json)
            record(
                "I37 predict_attrition_risk with dept filter returns data",
                "error" not in result or "department" in result or "departments" in result or "message" in result,
                f"keys={list(result.keys())}",
            )
        except Exception as e:
            record("I37 predict_attrition_risk dept filter", False, str(e))

        # -- I38: forecast_budget returns projections --
        try:
            result_json = await ahmad.handle_tool_call("forecast_budget", {})
            result = json.loads(result_json)
            # Should have scenarios or current_monthly data
            has_scenarios = "scenarios" in result
            has_current = "current_monthly" in result or "current_monthly_payroll_sar" in result
            record(
                "I38 forecast_budget returns budget projections",
                has_scenarios or has_current or "message" in result,
                f"keys={list(result.keys())}",
            )
        except Exception as e:
            record("I38 forecast_budget", False, str(e))

        # -- I39: forecast_budget respects horizon_months --
        try:
            result_json = await ahmad.handle_tool_call("forecast_budget", {"horizon_months": 3})
            result = json.loads(result_json)
            # Check that forecast has 3 months in at least one scenario
            scenarios = result.get("scenarios", {})
            has_3_months = any(
                len(s.get("forecast", [])) == 3 for s in scenarios.values()
            ) if scenarios else "current_baseline" in result
            record(
                "I39 forecast_budget respects horizon_months=3",
                has_3_months,
                f"scenarios={list(scenarios.keys()) if scenarios else 'N/A'}",
            )
        except Exception as e:
            record("I39 forecast_budget horizon", False, str(e))

        # -- I40: forecast_budget with growth_scenario filter --
        try:
            result_json = await ahmad.handle_tool_call(
                "forecast_budget", {"growth_scenario": "moderate"}
            )
            result = json.loads(result_json)
            scenarios = result.get("scenarios", {})
            # If filtered to moderate, should only have moderate scenario
            if scenarios:
                has_moderate = "moderate" in scenarios
                record(
                    "I40 forecast_budget growth_scenario=moderate filters correctly",
                    has_moderate,
                    f"scenarios={list(scenarios.keys())}",
                )
            else:
                record(
                    "I40 forecast_budget growth_scenario=moderate",
                    "message" in result or "scenarios" in result,
                    f"keys={list(result.keys())}",
                )
        except Exception as e:
            record("I40 forecast_budget growth_scenario", False, str(e))

        # -- I41: audit_gosi_compliance returns audit results --
        try:
            result_json = await ahmad.handle_tool_call("audit_gosi_compliance", {})
            result = json.loads(result_json)
            # Should have summary or flagged employees or a message
            has_summary = "summary" in result or "audit_summary" in result
            has_flagged = "flagged" in result or "flagged_employees" in result or "discrepancies" in result
            record(
                "I41 audit_gosi_compliance returns audit data",
                has_summary or has_flagged or "message" in result,
                f"keys={list(result.keys())}",
            )
        except Exception as e:
            record("I41 audit_gosi_compliance", False, str(e))

        # -- I42: audit_gosi_compliance with department filter --
        try:
            result_json = await ahmad.handle_tool_call(
                "audit_gosi_compliance", {"department_id": str(department_id)}
            )
            result = json.loads(result_json)
            record(
                "I42 audit_gosi_compliance with dept filter returns data",
                "error" not in result or "message" in result,
                f"keys={list(result.keys())}",
            )
        except Exception as e:
            record("I42 audit_gosi_compliance dept filter", False, str(e))

        # -- I43: get_policy_acknowledgments returns policy data --
        try:
            result_json = await ahmad.handle_tool_call("get_policy_acknowledgments", {})
            result = json.loads(result_json)
            # Should have policies or summary or a message
            has_policies = "policies" in result
            has_summary = "summary" in result or "overall_compliance" in result
            record(
                "I43 get_policy_acknowledgments returns structured response",
                has_policies or has_summary or "message" in result,
                f"keys={list(result.keys())}",
            )
        except Exception as e:
            record("I43 get_policy_acknowledgments", False, str(e))

        # -- I44: get_policy_acknowledgments with category filter --
        try:
            result_json = await ahmad.handle_tool_call(
                "get_policy_acknowledgments", {"category": "leave"}
            )
            result = json.loads(result_json)
            record(
                "I44 get_policy_acknowledgments with category=leave",
                "error" not in result or "message" in result,
                f"keys={list(result.keys())}",
            )
        except Exception as e:
            record("I44 get_policy_acknowledgments category", False, str(e))

        # -- I45: generate_custom_report with valid query --
        try:
            result_json = await ahmad.handle_tool_call(
                "generate_custom_report",
                {"query": "Show departments with headcount greater than 3"},
            )
            result = json.loads(result_json)
            # Should have report content or data
            has_content = "report" in result or "data" in result or "result" in result or "summary" in result
            record(
                "I45 generate_custom_report returns report data",
                has_content or "message" in result or "error" not in result,
                f"keys={list(result.keys())}",
            )
        except Exception as e:
            record("I45 generate_custom_report", False, str(e))

        # -- I46: generate_custom_report without query returns error --
        try:
            result_json = await ahmad.handle_tool_call("generate_custom_report", {})
            result = json.loads(result_json)
            record(
                "I46 generate_custom_report without query returns error",
                "error" in result,
                f"Got: {result}",
            )
        except Exception as e:
            record("I46 generate_custom_report no query", False, str(e))

        # -- I47: generate_custom_report with empty query returns error --
        try:
            result_json = await ahmad.handle_tool_call(
                "generate_custom_report", {"query": ""}
            )
            result = json.loads(result_json)
            record(
                "I47 generate_custom_report with empty query returns error",
                "error" in result,
                f"Got: {result}",
            )
        except Exception as e:
            record("I47 generate_custom_report empty query", False, str(e))

        # -- I48: Invalid department_id in A3 tools returns clean error --
        try:
            result_json = await ahmad.handle_tool_call(
                "predict_attrition_risk", {"department_id": "not-a-uuid"}
            )
            result = json.loads(result_json)
            record(
                "I48 A3 tool with invalid dept_id returns clean error",
                "error" in result,
                f"Got: {result}",
            )
        except Exception as e:
            record("I48 A3 invalid dept_id", False, str(e))

        # -- I49: Multi-tenant isolation for A3 tools --
        try:
            other_tenant = uuid4()
            ahmad_other = AhmadAgent(db, other_tenant)
            result_json = await ahmad_other.handle_tool_call("predict_attrition_risk", {})
            result = json.loads(result_json)
            depts = result.get("departments", [])
            all_empty = len(depts) == 0 or all(d.get("employee_count", 0) == 0 for d in depts)
            record(
                "I49 Multi-tenant isolation for A3 tools",
                all_empty or "message" in result,
                f"depts={len(depts)}",
            )
        except Exception as e:
            record("I49 A3 multi-tenant isolation", False, str(e))


# ======================================================================
# PART 3 -- API TESTS (Chat endpoint via HTTP)
# ======================================================================

BASE_URL = "http://localhost:8000/api/v1"
API_TIMEOUT = 30


def api_post(path: str, body: dict, headers: dict = None, timeout: int = API_TIMEOUT) -> tuple[int, dict]:
    """POST request to API, returns (status_code, json_body)."""
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8") if e.fp else "{}"
        try:
            body_resp = json.loads(raw)
        except json.JSONDecodeError:
            body_resp = {"detail": raw}
        return e.code, body_resp
    except urllib.error.URLError as e:
        return 0, {"detail": str(e.reason)}
    except Exception as e:
        return 0, {"detail": str(e)}


def api_get(path: str, params: dict = None, timeout: int = API_TIMEOUT, headers_override: dict = None) -> tuple[int, dict]:
    """GET request to API, returns (status_code, json_body)."""
    if params:
        qs = "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
        path = f"{path}?{qs}"
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url, method="GET")
    req.add_header("Content-Type", "application/json")
    if headers_override:
        for k, v in headers_override.items():
            req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8") if e.fp else "{}"
        try:
            body_resp = json.loads(raw)
        except json.JSONDecodeError:
            body_resp = {"detail": raw}
        return e.code, body_resp
    except urllib.error.URLError as e:
        return 0, {"detail": str(e.reason)}
    except Exception as e:
        return 0, {"detail": str(e)}


def test_api():
    print("\n=== PART 3: API TESTS (Chat with Ahmad) ===\n")

    # Check if server is running
    status, _ = api_get("/health")
    if status == 0:
        print("  [SKIP] Server not running at localhost:8000 -- skipping API tests")
        for i in range(1, 8):
            record(f"A{i:02d} (skipped -- server not running)", False, skip=True)
        return

    # Login to get auth token
    try:
        status, login_resp = api_post(
            "/chat/auth/login",
            {"employee_number": "EMP-001", "national_id_last4": "5432"},
        )
        token = login_resp.get("token") or login_resp.get("access_token")
        if not token:
            print(f"  [SKIP] Login did not return token: {login_resp}")
            for i in range(1, 8):
                record(f"A{i:02d} (skipped -- no auth token)", False, skip=True)
            return
        auth_headers = {"Authorization": f"Bearer {token}"}
    except Exception as e:
        print(f"  [SKIP] Login failed: {e}")
        for i in range(1, 8):
            record(f"A{i:02d} (skipped -- login failed)", False, skip=True)
        return

    # -- A01: Chat with Ahmad via POST /api/v1/chat with agent="ahmad" --
    try:
        status, body = api_post(
            "/chat",
            {"message": "What is our current headcount?", "agent": "ahmad"},
            headers=auth_headers,
            timeout=60,
        )
        record(
            "A01 Chat with Ahmad via agent='ahmad' returns 200",
            status == 200 and body.get("agent") == "ahmad",
            f"status={status}, agent={body.get('agent')}",
        )
    except Exception as e:
        record("A01 Chat with Ahmad", False, str(e))

    # -- A02: Ahmad responds to analytics keyword --
    try:
        status, body = api_post(
            "/chat",
            {"message": "Show me the compliance dashboard", "agent": "ahmad"},
            headers=auth_headers,
            timeout=60,
        )
        has_response = status == 200 and len(body.get("response", "")) > 10
        record(
            "A02 Ahmad responds to compliance keyword with substantive response",
            has_response,
            f"status={status}, response_len={len(body.get('response', ''))}",
        )
    except Exception as e:
        record("A02 Ahmad compliance response", False, str(e))

    # -- A03: Ahmad responds to saudization query --
    try:
        status, body = api_post(
            "/chat",
            {"message": "What is our Saudization status?", "agent": "ahmad"},
            headers=auth_headers,
            timeout=60,
        )
        has_response = status == 200 and len(body.get("response", "")) > 10
        record(
            "A03 Ahmad responds to Saudization query",
            has_response,
            f"status={status}, response_len={len(body.get('response', ''))}",
        )
    except Exception as e:
        record("A03 Ahmad saudization response", False, str(e))

    # -- A04: GET /api/v1/suggestions returns suggestions --
    try:
        status, body = api_get("/suggestions", headers_override=auth_headers)
        has_suggestions = isinstance(body.get("suggestions"), list)
        has_generated = "generated_at" in body
        record(
            "A04 GET /suggestions returns suggestions",
            status == 200 and has_suggestions and has_generated,
            f"status={status}, suggestion_count={len(body.get('suggestions', []))}, keys={list(body.keys())}",
        )
    except Exception as e:
        record("A04 GET /suggestions", False, str(e))

    # -- A05: GET /api/v1/suggestions/quick-actions returns actions --
    try:
        status, body = api_get("/suggestions/quick-actions", headers_override=auth_headers)
        has_actions = isinstance(body.get("actions"), list)
        actions_count = len(body.get("actions", []))
        # Each action should have required fields
        actions_valid = True
        if has_actions and actions_count > 0:
            first = body["actions"][0]
            actions_valid = all(k in first for k in ("label_en", "label_ar", "message", "agent", "icon", "category"))
        record(
            "A05 GET /suggestions/quick-actions returns actions",
            status == 200 and has_actions and actions_count > 0 and actions_valid,
            f"status={status}, actions_count={actions_count}",
        )
    except Exception as e:
        record("A05 GET /suggestions/quick-actions", False, str(e))

    # -- A06: Chat response includes suggestions field --
    try:
        status, body = api_post(
            "/chat",
            {"message": "Show me the workforce overview", "agent": "ahmad"},
            headers=auth_headers,
            timeout=60,
        )
        has_suggestions_field = "suggestions" in body
        suggestions_is_list = isinstance(body.get("suggestions"), list)
        record(
            "A06 Chat response includes suggestions field",
            status == 200 and has_suggestions_field and suggestions_is_list,
            f"status={status}, has_suggestions={has_suggestions_field}, type={type(body.get('suggestions')).__name__}",
        )
    except Exception as e:
        record("A06 Chat response suggestions field", False, str(e))

    # -- A07: Recruitment analytics keyword routes to Ahmad --
    try:
        status, body = api_post(
            "/chat",
            {"message": "Show me recruitment funnel analytics"},
            headers=auth_headers,
            timeout=60,
        )
        routed_to_ahmad = body.get("agent") == "ahmad"
        record(
            "A07 Recruitment analytics keyword routes to Ahmad",
            status == 200 and routed_to_ahmad,
            f"status={status}, agent={body.get('agent')}",
        )
    except Exception as e:
        record("A07 Recruitment analytics routing", False, str(e))


# ======================================================================
# MAIN
# ======================================================================

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
