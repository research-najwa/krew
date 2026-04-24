"""Sprint 8 cross-track test suite.

Covers:
  Track 2: Dynamic quick actions per agent (?agent= parameter)
  Track 3: Knowledge Management (models, ingestion chunking, API)
  Track 4: Ahmad English-only responses (validated in test_ahmad.py U25, reinforced here)
  Track 5: @mention routing, agent access control, unified chat fields

Categories:
  - Unit: mention parser, access control helpers, chunking, model enums
  - Integration: DB-backed role derivation, access checks
  - API: suggestions, quick-actions, knowledge, chat endpoints

Prerequisites:
  1. Server running at localhost:8000 (for API tests only)
  2. Seed data loaded: python -m scripts.seed
  3. PostgreSQL running at localhost:5432/krew

Usage:
    cd /Users/najwamalghamdi/Desktop/HR-AI-Startup/backend
    source venv/bin/activate
    python scripts/test_sprint8.py
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

def test_unit_mention_parser():
    """Track 5: @mention parser unit tests."""
    print("\n=== TRACK 5: @MENTION PARSER UNIT TESTS ===\n")

    from app.utils.mention_parser import (
        parse_mention, get_mentioned_raw,
        AGENT_ALIASES, MENTION_TO_AGENT,
    )

    # -- M01: Basic English mention --
    agent, msg = parse_mention("@deema check my leave")
    record(
        "M01 parse_mention('@deema check my leave') -> ('deema', 'check my leave')",
        agent == "deema" and msg == "check my leave",
        f"agent={agent}, msg={msg}",
    )

    # -- M02: Arabic mention --
    agent, msg = parse_mention("@\u0623\u062d\u0645\u062f analytics")
    record(
        "M02 parse_mention('@\u0623\u062d\u0645\u062f analytics') -> ('ahmad', 'analytics')",
        agent == "ahmad" and msg == "analytics",
        f"agent={agent}, msg={msg}",
    )

    # -- M03: No mention --
    agent, msg = parse_mention("no mention here")
    record(
        "M03 parse_mention('no mention here') -> (None, 'no mention here')",
        agent is None and msg == "no mention here",
        f"agent={agent}, msg={msg}",
    )

    # -- M04: Unrecognized mention returns (None, original) --
    agent, msg = parse_mention("@unknown do something")
    record(
        "M04 parse_mention('@unknown ...') -> (None, original_message)",
        agent is None and msg == "@unknown do something",
        f"agent={agent}, msg={msg}",
    )

    # -- M05: Case insensitive --
    agent, msg = parse_mention("@AHMAD show analytics")
    record(
        "M05 parse_mention('@AHMAD ...') -> ('ahmad', ...)",
        agent == "ahmad",
        f"agent={agent}",
    )

    # -- M06: Mention in middle of message --
    agent, msg = parse_mention("hey @mohammad schedule interview")
    record(
        "M06 parse_mention('hey @mohammad ...') -> ('mohammad', 'hey schedule interview')",
        agent == "mohammad" and "hey" in msg and "schedule interview" in msg,
        f"agent={agent}, msg={msg}",
    )

    # -- M07: Arabic Deema alias --
    agent, msg = parse_mention("@\u062f\u064a\u0645\u0629 \u0643\u0645 \u0631\u0635\u064a\u062f")
    record(
        "M07 parse_mention('@\u062f\u064a\u0645\u0629 ...') -> ('deema', ...)",
        agent == "deema",
        f"agent={agent}",
    )

    # -- M08: Waleed mention --
    agent, msg = parse_mention("@waleed show team overview")
    record(
        "M08 parse_mention('@waleed ...') -> ('waleed', ...)",
        agent == "waleed",
        f"agent={agent}",
    )

    # -- M09: Yara mention --
    agent, msg = parse_mention("@yara create agent")
    record(
        "M09 parse_mention('@yara ...') -> ('yara', ...)",
        agent == "yara",
        f"agent={agent}",
    )

    # -- M10: dept:{uuid} format passes through --
    test_uuid = "550e8400-e29b-41d4-a716-446655440000"
    agent, msg = parse_mention(f"@dept:{test_uuid} help me")
    record(
        "M10 parse_mention('@dept:{{uuid}} help') -> ('dept:{{uuid}}', 'help me')",
        agent == f"dept:{test_uuid}" and msg == "help me",
        f"agent={agent}, msg={msg}",
    )

    # -- M11: get_mentioned_raw returns raw @mention string --
    raw = get_mentioned_raw("hello @deema check leave")
    record(
        "M11 get_mentioned_raw returns '@deema'",
        raw == "@deema",
        f"raw={raw}",
    )

    # -- M12: get_mentioned_raw returns None for no mention --
    raw = get_mentioned_raw("no mention here")
    record(
        "M12 get_mentioned_raw returns None for no mention",
        raw is None,
        f"raw={raw}",
    )

    # -- M13: All 5 core agents have aliases --
    expected_agents = {"deema", "waleed", "mohammad", "yara", "ahmad"}
    has_all = expected_agents == set(AGENT_ALIASES.keys())
    record(
        "M13 AGENT_ALIASES contains all 5 core agents",
        has_all,
        f"aliases keys={set(AGENT_ALIASES.keys())}",
    )

    # -- M14: MENTION_TO_AGENT inverted lookup is populated --
    record(
        "M14 MENTION_TO_AGENT has entries for all aliases",
        len(MENTION_TO_AGENT) >= 10,  # At least 2 aliases per agent
        f"entries={len(MENTION_TO_AGENT)}",
    )

    # -- M15: Email address not treated as mention --
    agent, msg = parse_mention("email me at user@deema.com")
    record(
        "M15 Email address not treated as @mention",
        agent is None,
        f"agent={agent}, msg={msg}",
    )


def test_unit_access_control():
    """Track 5: Access control unit tests (evaluate_rule, no DB)."""
    print("\n=== TRACK 5: ACCESS CONTROL UNIT TESTS ===\n")

    from app.utils.agent_access import _evaluate_rule, invalidate_access_cache, _access_cache

    # -- AC01: No rule = allow (permissive default) --
    result = _evaluate_rule(None, uuid4(), "employee", None)
    record(
        "AC01 No access rule -> allow (permissive default)",
        result is True,
        f"result={result}",
    )

    # -- AC02: Create a mock rule for testing --
    # We'll create a simple mock class that mimics AgentAccessRule
    class MockRule:
        def __init__(self, access_type, allowed_roles=None, allowed_departments=None, allowed_users=None):
            self.access_type = access_type
            self.allowed_roles = allowed_roles or []
            self.allowed_departments = allowed_departments or []
            self.allowed_users = allowed_users or []

    from app.models.agent_access_rule import AccessType

    # AC02: access_type 'all' -> always allow
    rule_all = MockRule(AccessType.all)
    result = _evaluate_rule(rule_all, uuid4(), "employee", None)
    record(
        "AC02 access_type='all' -> allow",
        result is True,
        f"result={result}",
    )

    # -- AC03: access_type 'role_based' with matching role --
    rule_role = MockRule(AccessType.role_based, allowed_roles=["manager", "hr_admin"])
    result = _evaluate_rule(rule_role, uuid4(), "manager", None)
    record(
        "AC03 access_type='role_based' with matching role -> allow",
        result is True,
        f"result={result}",
    )

    # -- AC04: access_type 'role_based' with non-matching role --
    result = _evaluate_rule(rule_role, uuid4(), "employee", None)
    record(
        "AC04 access_type='role_based' with non-matching role -> deny",
        result is False,
        f"result={result}",
    )

    # -- AC05: access_type 'department' with matching dept --
    dept_id = uuid4()
    rule_dept = MockRule(AccessType.department, allowed_departments=[str(dept_id)])
    result = _evaluate_rule(rule_dept, uuid4(), "employee", dept_id)
    record(
        "AC05 access_type='department' with matching dept -> allow",
        result is True,
        f"result={result}",
    )

    # -- AC06: access_type 'department' with non-matching dept --
    result = _evaluate_rule(rule_dept, uuid4(), "employee", uuid4())
    record(
        "AC06 access_type='department' with non-matching dept -> deny",
        result is False,
        f"result={result}",
    )

    # -- AC07: access_type 'department' with None dept -> deny --
    result = _evaluate_rule(rule_dept, uuid4(), "employee", None)
    record(
        "AC07 access_type='department' with None dept_id -> deny",
        result is False,
        f"result={result}",
    )

    # -- AC08: access_type 'specific_users' with matching user --
    user_id = uuid4()
    rule_users = MockRule(AccessType.specific_users, allowed_users=[str(user_id)])
    result = _evaluate_rule(rule_users, user_id, "employee", None)
    record(
        "AC08 access_type='specific_users' with matching user -> allow",
        result is True,
        f"result={result}",
    )

    # -- AC09: access_type 'specific_users' with non-matching user --
    result = _evaluate_rule(rule_users, uuid4(), "employee", None)
    record(
        "AC09 access_type='specific_users' with non-matching user -> deny",
        result is False,
        f"result={result}",
    )

    # -- AC10: Cache invalidation works --
    tenant = uuid4()
    _access_cache[(tenant, "test_agent")] = (time.time(), None)
    invalidate_access_cache(tenant, "test_agent")
    record(
        "AC10 invalidate_access_cache removes specific entry",
        (tenant, "test_agent") not in _access_cache,
        f"cache still has key: {(tenant, 'test_agent') in _access_cache}",
    )

    # -- AC11: Cache invalidation for entire tenant --
    _access_cache[(tenant, "agent1")] = (time.time(), None)
    _access_cache[(tenant, "agent2")] = (time.time(), None)
    invalidate_access_cache(tenant)
    has_any = any(k[0] == tenant for k in _access_cache)
    record(
        "AC11 invalidate_access_cache(tenant) removes all entries for tenant",
        not has_any,
        f"remaining keys for tenant: {[k for k in _access_cache if k[0] == tenant]}",
    )


def test_unit_knowledge_chunking():
    """Track 3: Knowledge ingestion chunking unit tests."""
    print("\n=== TRACK 3: KNOWLEDGE CHUNKING UNIT TESTS ===\n")

    from app.services.knowledge_ingestion import (
        chunk_markdown, _parse_sections, _count_tokens,
    )

    # -- KC01: Simple text with no headings -> single section --
    sections = _parse_sections("Hello world\nThis is a test.")
    record(
        "KC01 Text with no headings -> 1 section with empty heading_path",
        len(sections) == 1 and sections[0]["heading_path"] == [],
        f"sections={len(sections)}, path={sections[0]['heading_path'] if sections else 'N/A'}",
    )

    # -- KC02: Heading-based parsing --
    md = "# Leave Policy\nAnnual leave is 21 days.\n\n## Sick Leave\n30 days per year."
    sections = _parse_sections(md)
    record(
        "KC02 Heading-based parsing extracts 2 sections",
        len(sections) == 2,
        f"sections={len(sections)}, paths={[s['heading_path'] for s in sections]}",
    )

    # -- KC03: Nested headings maintain hierarchy --
    md = "# Policy\n\n## Leave\nLeave text.\n\n### Annual\nAnnual text."
    sections = _parse_sections(md)
    # Should have sections for Leave and Annual
    annual_section = [s for s in sections if any("Annual" in h for h in s["heading_path"])]
    record(
        "KC03 Nested headings maintain hierarchy in heading_path",
        len(annual_section) > 0 and len(annual_section[0]["heading_path"]) >= 2,
        f"paths={[s['heading_path'] for s in sections]}",
    )

    # -- KC04: chunk_markdown returns (content, token_count) tuples --
    chunks = chunk_markdown("# Test\nSome content here.", chunk_size=800)
    record(
        "KC04 chunk_markdown returns list of (content, token_count) tuples",
        len(chunks) > 0 and isinstance(chunks[0], tuple) and len(chunks[0]) == 2,
        f"chunks={len(chunks)}, first type={type(chunks[0]) if chunks else 'N/A'}",
    )

    # -- KC05: Token count is positive --
    if chunks:
        _, token_count = chunks[0]
        record(
            "KC05 Token count is positive integer",
            isinstance(token_count, int) and token_count > 0,
            f"token_count={token_count}",
        )
    else:
        record("KC05 Token count check", False, "No chunks produced")

    # -- KC06: Chunk content includes heading prefix --
    md = "# Leave Policy\nAnnual leave is 21 working days per year."
    chunks = chunk_markdown(md, chunk_size=800)
    if chunks:
        content = chunks[0][0]
        has_heading = "Leave Policy" in content
        record(
            "KC06 Chunk content includes heading prefix",
            has_heading,
            f"content starts with: {content[:80]}",
        )
    else:
        record("KC06 Heading prefix check", False, "No chunks produced")

    # -- KC07: Large text gets split into multiple chunks --
    large_md = "# Big Document\n" + ("This is a paragraph of test text. " * 200)
    chunks = chunk_markdown(large_md, chunk_size=100, chunk_overlap=20)
    record(
        "KC07 Large text gets split into multiple chunks",
        len(chunks) > 1,
        f"chunks={len(chunks)}",
    )

    # -- KC08: Empty content produces no chunks --
    chunks = chunk_markdown("", chunk_size=800)
    record(
        "KC08 Empty content produces no chunks",
        len(chunks) == 0,
        f"chunks={len(chunks)}",
    )

    # -- KC09: _count_tokens returns reasonable count --
    count = _count_tokens("Hello world")
    record(
        "KC09 _count_tokens returns reasonable count for 'Hello world'",
        1 <= count <= 5,
        f"count={count}",
    )

    # -- KC10: Arabic text tokenizes correctly --
    count_ar = _count_tokens("\u0633\u064a\u0627\u0633\u0629 \u0627\u0644\u0625\u062c\u0627\u0632\u0627\u062a")
    record(
        "KC10 Arabic text tokenizes to positive count",
        count_ar > 0,
        f"count={count_ar}",
    )


def test_unit_knowledge_models():
    """Track 3: Knowledge source model enum tests."""
    print("\n=== TRACK 3: KNOWLEDGE MODEL UNIT TESTS ===\n")

    from app.models.knowledge_source import SourceType, EmbeddingStatus

    # -- KM01: SourceType enum has expected values --
    expected_types = {"policy", "document", "markdown", "custom_text", "url"}
    actual_types = {e.value for e in SourceType}
    record(
        "KM01 SourceType enum has expected values",
        expected_types == actual_types,
        f"expected={expected_types}, actual={actual_types}",
    )

    # -- KM02: EmbeddingStatus enum has expected values --
    expected_statuses = {"pending", "processing", "complete", "failed"}
    actual_statuses = {e.value for e in EmbeddingStatus}
    record(
        "KM02 EmbeddingStatus enum has expected values",
        expected_statuses == actual_statuses,
        f"expected={expected_statuses}, actual={actual_statuses}",
    )

    # -- KM03: KnowledgeSource table name --
    from app.models.knowledge_source import KnowledgeSource
    record(
        "KM03 KnowledgeSource.__tablename__ is 'knowledge_sources'",
        KnowledgeSource.__tablename__ == "knowledge_sources",
        f"tablename={KnowledgeSource.__tablename__}",
    )

    # -- KM04: KnowledgeChunk table name --
    from app.models.knowledge_source import KnowledgeChunk
    record(
        "KM04 KnowledgeChunk.__tablename__ is 'knowledge_chunks'",
        KnowledgeChunk.__tablename__ == "knowledge_chunks",
        f"tablename={KnowledgeChunk.__tablename__}",
    )

    # -- KM05: AgentKnowledgeAssignment table name --
    from app.models.knowledge_source import AgentKnowledgeAssignment
    record(
        "KM05 AgentKnowledgeAssignment.__tablename__ is 'agent_knowledge_assignments'",
        AgentKnowledgeAssignment.__tablename__ == "agent_knowledge_assignments",
        f"tablename={AgentKnowledgeAssignment.__tablename__}",
    )


def test_unit_quick_actions():
    """Track 2: Dynamic quick actions unit tests (code structure)."""
    print("\n=== TRACK 2: QUICK ACTIONS UNIT TESTS ===\n")

    from app.api.suggestions import (
        _AGENT_ACTIONS, _ROLE_RESTRICTED_ACTIONS,
        QuickAction, QuickActionsResponse,
    )

    # -- QA01: _AGENT_ACTIONS has entries for all 5 core agents --
    expected_agents = {"deema", "ahmad", "mohammad", "waleed", "yara"}
    actual_agents = set(_AGENT_ACTIONS.keys())
    record(
        "QA01 _AGENT_ACTIONS has entries for all 5 core agents",
        expected_agents == actual_agents,
        f"expected={expected_agents}, actual={actual_agents}",
    )

    # -- QA02: Each agent has exactly 5 actions --
    all_have_5 = True
    bad_counts = []
    for agent_name, actions in _AGENT_ACTIONS.items():
        if len(actions) != 5:
            all_have_5 = False
            bad_counts.append(f"{agent_name}={len(actions)}")
    record(
        "QA02 Each agent has exactly 5 actions",
        all_have_5,
        f"Bad counts: {bad_counts}",
    )

    # -- QA03: Each action has required fields --
    required_fields = {"label_en", "label_ar", "message", "agent", "icon", "category"}
    all_valid = True
    bad_actions = []
    for agent_name, actions in _AGENT_ACTIONS.items():
        for action in actions:
            missing = required_fields - set(action.keys())
            if missing:
                all_valid = False
                bad_actions.append(f"{agent_name}/{action.get('label_en', '?')}: missing {missing}")
    record(
        "QA03 Every action has required fields (label_en, label_ar, message, agent, icon, category)",
        all_valid,
        f"Bad: {bad_actions}",
    )

    # -- QA04: Deema actions are self_service category --
    deema_actions = _AGENT_ACTIONS.get("deema", [])
    all_self_service = all(a.get("category") == "self_service" for a in deema_actions)
    record(
        "QA04 Deema actions are all 'self_service' category",
        all_self_service,
        f"categories={[a.get('category') for a in deema_actions]}",
    )

    # -- QA05: Ahmad actions are all 'analytics' category --
    ahmad_actions = _AGENT_ACTIONS.get("ahmad", [])
    all_analytics = all(a.get("category") == "analytics" for a in ahmad_actions)
    record(
        "QA05 Ahmad actions are all 'analytics' category",
        all_analytics,
        f"categories={[a.get('category') for a in ahmad_actions]}",
    )

    # -- QA06: Each action's agent field matches its agent key --
    all_match = True
    mismatches = []
    for agent_name, actions in _AGENT_ACTIONS.items():
        for action in actions:
            if action.get("agent") != agent_name:
                all_match = False
                mismatches.append(f"{agent_name}/{action.get('label_en')}: agent={action.get('agent')}")
    record(
        "QA06 Each action's 'agent' field matches its agent key",
        all_match,
        f"Mismatches: {mismatches}",
    )

    # -- QA07: Role restrictions exist for employee role --
    has_employee_restrictions = "employee" in _ROLE_RESTRICTED_ACTIONS
    record(
        "QA07 Role restrictions defined for 'employee' role",
        has_employee_restrictions,
        f"roles with restrictions: {list(_ROLE_RESTRICTED_ACTIONS.keys())}",
    )

    # -- QA08: Employee can't access ahmad Budget Forecast and Attrition Risk --
    employee_restrictions = _ROLE_RESTRICTED_ACTIONS.get("employee", {})
    ahmad_restricted = employee_restrictions.get("ahmad", set())
    record(
        "QA08 Employee restricted from Ahmad 'Budget Forecast' and 'Attrition Risk'",
        "Budget Forecast" in ahmad_restricted and "Attrition Risk" in ahmad_restricted,
        f"ahmad restrictions={ahmad_restricted}",
    )


def test_unit_employee_role():
    """Track 5: Employee role derivation (code structure, no DB)."""
    print("\n=== TRACK 5: EMPLOYEE ROLE UNIT TESTS ===\n")

    from app.api.suggestions import _determine_role

    # -- ER01: _determine_role exists and is callable --
    record(
        "ER01 _determine_role is callable",
        callable(_determine_role),
        "",
    )

    # -- ER02: Employee role module has derive_employee_role --
    from app.utils.employee_role import derive_employee_role
    record(
        "ER02 derive_employee_role function exists",
        callable(derive_employee_role),
        "",
    )


def test_unit_scoped_retriever():
    """Track 3: Scoped retriever structure tests."""
    print("\n=== TRACK 3: SCOPED RETRIEVER UNIT TESTS ===\n")

    from app.rag.scoped_retriever import ScopedKnowledgeRetriever

    # -- SR01: ScopedKnowledgeRetriever class exists with search method --
    record(
        "SR01 ScopedKnowledgeRetriever has search() method",
        hasattr(ScopedKnowledgeRetriever, "search"),
        "",
    )

    # -- SR02: Has _scoped_search and _global_search methods --
    has_scoped = hasattr(ScopedKnowledgeRetriever, "_scoped_search")
    has_global = hasattr(ScopedKnowledgeRetriever, "_global_search")
    record(
        "SR02 ScopedKnowledgeRetriever has _scoped_search and _global_search",
        has_scoped and has_global,
        f"scoped={has_scoped}, global={has_global}",
    )


# ======================================================================
# PART 2 -- INTEGRATION TESTS (DB required)
# ======================================================================

async def test_integration_role_derivation():
    """Track 5: Role derivation with real DB."""
    print("\n=== TRACK 5: ROLE DERIVATION INTEGRATION TESTS ===\n")

    try:
        from app.database import async_session
        from app.models.employee import Employee, Department
        from app.utils.employee_role import derive_employee_role
        from sqlalchemy import select
    except ImportError as e:
        record("Role derivation import", False, str(e))
        return

    try:
        async with async_session() as db:
            # Find a department and its employees
            dept_result = await db.execute(select(Department).limit(1))
            dept = dept_result.scalar_one_or_none()
            if not dept:
                record("RD00 Department found", False, "No departments in DB")
                return

            tenant_id = dept.tenant_id

            # -- RD01: Employee with no special title -> 'employee' role --
            emp_result = await db.execute(
                select(Employee).where(
                    Employee.tenant_id == tenant_id,
                    Employee.job_title.ilike("%engineer%"),
                ).limit(1)
            )
            emp = emp_result.scalar_one_or_none()
            if emp:
                role = await derive_employee_role(db, tenant_id, emp.id)
                # Role depends on title — VP/Chief/Head titles map to c_suite/dept_head
                title_lower = (emp.job_title or "").lower()
                if any(kw in title_lower for kw in ["vp", "chief", "vice president"]):
                    expected = ("c_suite",)
                else:
                    expected = ("employee", "manager", "department_head")
                record(
                    "RD01 Engineer derives to valid role",
                    role in expected,
                    f"role={role}, title={emp.job_title}",
                )
            else:
                record("RD01 Engineer role", True, "No engineer found in DB, skipping")

            # -- RD02: Non-existent employee -> 'employee' default --
            fake_id = uuid4()
            role = await derive_employee_role(db, tenant_id, fake_id)
            record(
                "RD02 Non-existent employee -> 'employee' default",
                role == "employee",
                f"role={role}",
            )

            # -- RD03: Role derivation respects tenant isolation --
            other_tenant = uuid4()
            if emp:
                role = await derive_employee_role(db, other_tenant, emp.id)
                record(
                    "RD03 Employee in wrong tenant -> 'employee' default",
                    role == "employee",
                    f"role={role}",
                )
            else:
                record("RD03 Tenant isolation", True, "No employee to test")

    except Exception as e:
        record("Role derivation DB tests", False, str(e))


async def test_integration_orchestrator_mention():
    """Track 5: Orchestrator @mention routing integration tests."""
    print("\n=== TRACK 5: ORCHESTRATOR @MENTION ROUTING ===\n")

    try:
        from app.database import async_session
        from app.models.employee import Department
        from app.agents.orchestrator import AgentOrchestrator
        from sqlalchemy import select
    except ImportError as e:
        record("Orchestrator import", False, str(e))
        return

    try:
        async with async_session() as db:
            dept_result = await db.execute(select(Department).limit(1))
            dept = dept_result.scalar_one_or_none()
            if not dept:
                record("OM00 DB data check", False, "No departments in DB")
                return

            tenant_id = dept.tenant_id
            orch = AgentOrchestrator(db, tenant_id)

            # -- OM01: @deema mention routes to deema --
            agent, cleaned, error = await orch.route(
                "@deema check my leave balance",
                current_agent=None,
            )
            record(
                "OM01 '@deema check leave' routes to deema",
                agent == "deema" and error is None,
                f"agent={agent}, error={error}",
            )

            # -- OM02: @ahmad mention routes to ahmad --
            agent, cleaned, error = await orch.route(
                "@ahmad show analytics",
                current_agent="deema",
            )
            record(
                "OM02 '@ahmad show analytics' routes to ahmad (overrides current)",
                agent == "ahmad" and error is None,
                f"agent={agent}, cleaned={cleaned}",
            )

            # -- OM03: @mention cleans the mention from message --
            agent, cleaned, error = await orch.route("@waleed team overview")
            record(
                "OM03 @mention strips mention from cleaned message",
                agent == "waleed" and "@waleed" not in cleaned,
                f"agent={agent}, cleaned={cleaned}",
            )

            # -- OM04: Arabic @mention routes correctly --
            agent, cleaned, error = await orch.route("@\u0623\u062d\u0645\u062f \u062a\u062d\u0644\u064a\u0644\u0627\u062a")
            record(
                "OM04 Arabic '@\u0623\u062d\u0645\u062f ...' routes to ahmad",
                agent == "ahmad" and error is None,
                f"agent={agent}",
            )

            # -- OM05: Unrecognized @mention returns error --
            agent, cleaned, error = await orch.route("@nonexistent help me")
            record(
                "OM05 Unrecognized '@nonexistent' returns error message",
                agent == "system" and error is not None,
                f"agent={agent}, error={error}",
            )

            # -- OM06: Sticky @mention -- last_mentioned_agent is used --
            agent, cleaned, error = await orch.route(
                "show me more details",
                current_agent=None,
                last_mentioned_agent="ahmad",
            )
            record(
                "OM06 Sticky @mention -- 'show me more' routes to last_mentioned ahmad",
                agent == "ahmad",
                f"agent={agent}",
            )

    except Exception as e:
        record("Orchestrator mention tests", False, str(e))


# ======================================================================
# PART 3 -- API TESTS (HTTP)
# ======================================================================

BASE_URL = "http://localhost:8000/api/v1"
API_TIMEOUT = 30


def api_post(path: str, body: dict, headers: dict = None, timeout: int = API_TIMEOUT) -> tuple[int, dict]:
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
    """API tests for Sprint 8 tracks."""
    print("\n=== API TESTS (Sprint 8) ===\n")

    # Check server
    status, _ = api_get("/health")
    if status == 0:
        print("  [SKIP] Server not running at localhost:8000 -- skipping API tests")
        for i in range(1, 20):
            record(f"API{i:02d} (skipped -- server not running)", False, skip=True)
        return

    # Login
    try:
        status, login_resp = api_post(
            "/chat/auth/login",
            {"employee_number": "EMP-001", "national_id_last4": "5432"},
        )
        token = login_resp.get("token") or login_resp.get("access_token")
        if not token:
            print(f"  [SKIP] Login did not return token: {login_resp}")
            for i in range(1, 20):
                record(f"API{i:02d} (skipped -- no auth)", False, skip=True)
            return
        auth = {"Authorization": f"Bearer {token}"}
    except Exception as e:
        print(f"  [SKIP] Login failed: {e}")
        for i in range(1, 20):
            record(f"API{i:02d} (skipped -- login failed)", False, skip=True)
        return

    # ── Track 2: Quick Actions ──────────────────────────────────

    # -- API01: GET /suggestions/quick-actions?agent=deema returns Deema actions --
    try:
        status, body = api_get(
            "/suggestions/quick-actions",
            params={"agent": "deema"},
            headers_override=auth,
        )
        actions = body.get("actions", [])
        all_deema = all(a.get("agent") == "deema" for a in actions) if actions else False
        record(
            "API01 GET /suggestions/quick-actions?agent=deema returns Deema-specific actions",
            status == 200 and len(actions) > 0 and all_deema,
            f"status={status}, count={len(actions)}, all_deema={all_deema}",
        )
    except Exception as e:
        record("API01 Quick actions deema", False, str(e))

    # -- API02: GET /suggestions/quick-actions?agent=ahmad returns Ahmad actions --
    try:
        status, body = api_get(
            "/suggestions/quick-actions",
            params={"agent": "ahmad"},
            headers_override=auth,
        )
        actions = body.get("actions", [])
        all_ahmad = all(a.get("agent") == "ahmad" for a in actions) if actions else False
        record(
            "API02 GET /suggestions/quick-actions?agent=ahmad returns Ahmad-specific actions",
            status == 200 and len(actions) > 0 and all_ahmad,
            f"status={status}, count={len(actions)}, all_ahmad={all_ahmad}",
        )
    except Exception as e:
        record("API02 Quick actions ahmad", False, str(e))

    # -- API03: GET /suggestions/quick-actions (no agent) returns default/role actions --
    try:
        status, body = api_get(
            "/suggestions/quick-actions",
            headers_override=auth,
        )
        actions = body.get("actions", [])
        has_actions = len(actions) > 0
        # Each action should have required fields
        if has_actions:
            first = actions[0]
            has_fields = all(k in first for k in ("label_en", "label_ar", "message", "agent", "icon", "category"))
        else:
            has_fields = False
        record(
            "API03 GET /suggestions/quick-actions (no agent) returns default actions",
            status == 200 and has_actions and has_fields,
            f"status={status}, count={len(actions)}",
        )
    except Exception as e:
        record("API03 Quick actions default", False, str(e))

    # -- API04: Agent actions have required fields --
    try:
        status, body = api_get(
            "/suggestions/quick-actions",
            params={"agent": "waleed"},
            headers_override=auth,
        )
        actions = body.get("actions", [])
        all_valid = True
        bad = []
        for a in actions:
            missing = {"label_en", "label_ar", "message", "icon", "category"} - set(a.keys())
            if missing:
                all_valid = False
                bad.append(f"{a.get('label_en', '?')}: missing {missing}")
        record(
            "API04 Agent-scoped actions have all required fields",
            status == 200 and len(actions) > 0 and all_valid,
            f"status={status}, count={len(actions)}, bad={bad}",
        )
    except Exception as e:
        record("API04 Action fields validation", False, str(e))

    # -- API05: Max 6 actions returned --
    try:
        status, body = api_get(
            "/suggestions/quick-actions",
            params={"agent": "mohammad"},
            headers_override=auth,
        )
        actions = body.get("actions", [])
        record(
            "API05 Quick actions returns max 6 actions",
            status == 200 and len(actions) <= 6,
            f"status={status}, count={len(actions)}",
        )
    except Exception as e:
        record("API05 Max actions count", False, str(e))

    # ── Track 5: Unified Chat ───────────────────────────────────

    # -- API06: Chat response includes agent_display_name, agent_color, available_agents --
    try:
        status, body = api_post(
            "/chat",
            {"message": "What is my leave balance?"},
            headers=auth,
            timeout=60,
        )
        has_display = "agent_display_name" in body and len(body["agent_display_name"]) > 0
        has_color = "agent_color" in body and body["agent_color"].startswith("#")
        has_available = "available_agents" in body and isinstance(body["available_agents"], list)
        record(
            "API06 Chat response includes agent_display_name, agent_color, available_agents",
            status == 200 and has_display and has_color and has_available,
            f"display={body.get('agent_display_name')}, color={body.get('agent_color')}, "
            f"available_count={len(body.get('available_agents', []))}",
        )
    except Exception as e:
        record("API06 Unified chat fields", False, str(e))

    # -- API07: available_agents includes core agents --
    try:
        # Reuse previous response body if available
        available = body.get("available_agents", [])
        agent_names = [a.get("name") for a in available]
        has_core = all(a in agent_names for a in ["deema", "ahmad", "waleed", "mohammad"])
        record(
            "API07 available_agents includes core agents (deema, ahmad, waleed, mohammad)",
            has_core,
            f"agent_names={agent_names}",
        )
    except Exception as e:
        record("API07 Available agents list", False, str(e))

    # -- API08: available_agents entries have display_name and color --
    try:
        available = body.get("available_agents", [])
        all_valid = True
        for a in available:
            if not a.get("display_name") or not a.get("color"):
                all_valid = False
                break
        record(
            "API08 available_agents entries have display_name and color",
            all_valid and len(available) > 0,
            f"first entry={available[0] if available else 'N/A'}",
        )
    except Exception as e:
        record("API08 Available agents fields", False, str(e))

    # -- API09: @mention routes to correct agent --
    try:
        status, body = api_post(
            "/chat",
            {"message": "@ahmad show me workforce overview"},
            headers=auth,
            timeout=60,
        )
        routed = body.get("agent") == "ahmad"
        routed_by = body.get("routed_by", "")
        record(
            "API09 @ahmad in message routes to Ahmad agent",
            status == 200 and routed,
            f"agent={body.get('agent')}, routed_by={routed_by}",
        )
    except Exception as e:
        record("API09 @mention routing", False, str(e))

    # -- API10: routed_by field is present --
    try:
        record(
            "API10 Chat response includes routed_by field",
            "routed_by" in body and body["routed_by"] in ("mention", "keyword", "sticky", "switch", "default", "error", ""),
            f"routed_by={body.get('routed_by')}",
        )
    except Exception as e:
        record("API10 routed_by field", False, str(e))

    # -- API11: Chat with Arabic @mention --
    try:
        status, body = api_post(
            "/chat",
            {"message": "@\u062f\u064a\u0645\u0629 \u0643\u0645 \u0631\u0635\u064a\u062f \u0625\u062c\u0627\u0632\u0627\u062a\u064a"},
            headers=auth,
            timeout=60,
        )
        record(
            "API11 Arabic '@\u062f\u064a\u0645\u0629 ...' routes to Deema",
            status == 200 and body.get("agent") == "deema",
            f"agent={body.get('agent')}",
        )
    except Exception as e:
        record("API11 Arabic @mention routing", False, str(e))

    # ── Track 4: Ahmad English-only ─────────────────────────────

    # -- API12: Ahmad responds in English to Arabic input --
    try:
        status, body = api_post(
            "/chat",
            {"message": "@ahmad \u0623\u0631\u0646\u064a \u062a\u062d\u0644\u064a\u0644\u0627\u062a \u0627\u0644\u0645\u0648\u0638\u0641\u064a\u0646", "agent": "ahmad"},
            headers=auth,
            timeout=60,
        )
        response_text = body.get("response", "")
        # Check that response is predominantly English (more Latin chars than Arabic)
        latin_chars = sum(1 for c in response_text if c.isascii() and c.isalpha())
        arabic_chars = sum(1 for c in response_text if '\u0600' <= c <= '\u06FF')
        is_english = latin_chars > arabic_chars * 2  # At least 2x more Latin
        record(
            "API12 Ahmad responds in English even to Arabic input",
            status == 200 and is_english and len(response_text) > 20,
            f"latin={latin_chars}, arabic={arabic_chars}, len={len(response_text)}",
        )
    except Exception as e:
        record("API12 Ahmad English-only", False, str(e))

    # ── Track 3: Knowledge API ──────────────────────────────────

    # Knowledge API requires admin auth, try to get admin token
    admin_token = None
    try:
        status, login_resp = api_post(
            "/auth/login",
            {"email": "admin@krew.sa", "password": "admin123"},
        )
        admin_token = login_resp.get("access_token") or login_resp.get("token")
    except Exception:
        pass

    if not admin_token:
        print("  [SKIP] Admin auth not available -- skipping Knowledge API tests")
        for i in range(13, 20):
            record(f"API{i:02d} (skipped -- no admin auth)", False, skip=True)
        return

    admin_auth = {"Authorization": f"Bearer {admin_token}"}

    # -- API13: POST /knowledge/sources creates a source --
    source_id = None
    try:
        status, body = api_post(
            "/knowledge/sources",
            {
                "title": "Test Leave Policy",
                "source_type": "policy",
                "category": "leave",
                "content_text": "# Leave Policy\nAnnual leave is 21 days.",
            },
            headers=admin_auth,
        )
        source_id = body.get("id")
        record(
            "API13 POST /knowledge/sources creates a source",
            status == 201 and source_id is not None,
            f"status={status}, id={source_id}",
        )
    except Exception as e:
        record("API13 Create knowledge source", False, str(e))

    # -- API14: GET /knowledge/sources lists sources --
    try:
        status, body = api_get("/knowledge/sources", headers_override=admin_auth)
        has_items = "items" in body and isinstance(body["items"], list)
        has_total = "total" in body
        has_page = "page" in body
        record(
            "API14 GET /knowledge/sources returns paginated list",
            status == 200 and has_items and has_total and has_page,
            f"status={status}, total={body.get('total')}, page={body.get('page')}",
        )
    except Exception as e:
        record("API14 List knowledge sources", False, str(e))

    # -- API15: GET /knowledge/sources?source_type=policy filters --
    try:
        status, body = api_get(
            "/knowledge/sources",
            params={"source_type": "policy"},
            headers_override=admin_auth,
        )
        items = body.get("items", [])
        all_policy = all(i.get("source_type") == "policy" for i in items) if items else True
        record(
            "API15 GET /knowledge/sources?source_type=policy filters correctly",
            status == 200 and all_policy,
            f"status={status}, count={len(items)}",
        )
    except Exception as e:
        record("API15 Knowledge source filter", False, str(e))

    # -- API16: POST /knowledge/sources/{id}/ingest-text triggers ingestion --
    if source_id:
        try:
            status, body = api_post(
                f"/knowledge/sources/{source_id}/ingest-text",
                {"content": "# Leave Policy\n\nAnnual leave entitlement is 21 working days.\n\n## Sick Leave\n\n30 days per year."},
                headers=admin_auth,
            )
            record(
                "API16 POST /knowledge/sources/{id}/ingest-text returns 202",
                status == 202 and body.get("status") == "processing",
                f"status={status}, body={body}",
            )
        except Exception as e:
            record("API16 Ingest text", False, str(e))
    else:
        record("API16 Ingest text", False, skip=True)

    # -- API17: POST /knowledge/capture returns structured output --
    try:
        status, body = api_post(
            "/knowledge/capture",
            {"content": "Employees get 21 days of annual leave and 30 days of sick leave", "language": "en"},
            headers=admin_auth,
            timeout=60,
        )
        has_title = "suggested_title" in body
        has_category = "suggested_category" in body
        has_agents = "suggested_agents" in body
        has_content = "structured_content" in body
        has_confidence = "confidence" in body
        record(
            "API17 POST /knowledge/capture returns structured output",
            status == 200 and has_title and has_category and has_agents and has_content and has_confidence,
            f"status={status}, keys={list(body.keys())}",
        )
    except Exception as e:
        record("API17 Knowledge capture", False, str(e))

    # -- API18: Knowledge source response has expected fields --
    if source_id:
        try:
            status, body = api_get(
                f"/knowledge/sources/{source_id}",
                headers_override=admin_auth,
            )
            expected_fields = {"id", "tenant_id", "title", "source_type", "chunk_count",
                             "embedding_status", "is_active", "created_at", "updated_at"}
            has_all = expected_fields.issubset(set(body.keys()))
            record(
                "API18 Knowledge source response has expected fields",
                status == 200 and has_all,
                f"status={status}, keys={list(body.keys())}",
            )
        except Exception as e:
            record("API18 Knowledge source fields", False, str(e))
    else:
        record("API18 Knowledge source fields", False, skip=True)

    # -- API19: Cleanup -- delete the test source --
    if source_id:
        try:
            url = f"{BASE_URL}/knowledge/sources/{source_id}"
            req = urllib.request.Request(url, method="DELETE")
            req.add_header("Content-Type", "application/json")
            for k, v in admin_auth.items():
                req.add_header(k, v)
            with urllib.request.urlopen(req, timeout=API_TIMEOUT) as resp:
                status = resp.status
            record(
                "API19 DELETE /knowledge/sources/{id} soft-deletes",
                status == 200,
                f"status={status}",
            )
        except Exception as e:
            record("API19 Delete knowledge source", False, str(e))
    else:
        record("API19 Delete knowledge source", False, skip=True)


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
    test_unit_mention_parser()
    test_unit_access_control()
    test_unit_knowledge_chunking()
    test_unit_knowledge_models()
    test_unit_quick_actions()
    test_unit_employee_role()
    test_unit_scoped_retriever()

    # Part 2: Integration tests (need DB)
    try:
        asyncio.run(test_integration_role_derivation())
    except Exception as e:
        print(f"\n  [ERROR] Role derivation tests failed to run: {e}")
        record("Role derivation suite", False, str(e))

    try:
        asyncio.run(test_integration_orchestrator_mention())
    except Exception as e:
        print(f"\n  [ERROR] Orchestrator mention tests failed to run: {e}")
        record("Orchestrator mention suite", False, str(e))

    # Part 3: API tests (need running server)
    test_api()

    elapsed = time.time() - t0
    print_summary()
    print(f"  Total time: {elapsed:.1f}s")
    sys.exit(1 if failed > 0 else 0)
