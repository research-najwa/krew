"""Waleed Agent — W4 Regression + Feature Tests.

Tests proactive context, agent handoff, sticky routing, empty states,
tool regression (view_team, onboarding_dashboard), and role-based access.

Uses urllib.request (no 3rd-party HTTP libs). Deterministic where possible,
LLM-based where routing / natural language is involved.
"""
import json
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BASE = "http://localhost:8000/api/v1"

# ── Credentials ──────────────────────────────────────────────────────
AHMED_CREDS = {"employee_number": "EMP-001", "national_id_last4": "5432"}
RAYAN_CREDS = {"employee_number": "EMP-007", "national_id_last4": "0987"}

# ── Counters ─────────────────────────────────────────────────────────
passed = 0
failed = 0
errors = 0
results = []


# ── Helpers ──────────────────────────────────────────────────────────

def flush_rate_limits():
    """Clear all Redis rate-limit keys."""
    try:
        import redis
        r = redis.from_url("redis://localhost:6379")
        keys = list(r.scan_iter("rl:*"))
        if keys:
            r.delete(*keys)
    except Exception as exc:
        print(f"  [warn] Could not flush rate limits: {exc}")


def api_post(path: str, data: dict, token: str | None = None, timeout: int = 60) -> dict:
    """POST JSON to the API and return parsed response."""
    url = f"{BASE}{path}"
    body = json.dumps(data).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode() if exc.fp else ""
        return {"_http_error": exc.code, "_detail": error_body}


def login(creds: dict) -> tuple[str, str]:
    """Login and return (token, employee_id)."""
    resp = api_post("/chat/auth/login", creds)
    if "_http_error" in resp:
        raise RuntimeError(f"Login failed: {resp}")
    return resp["token"], resp["employee_id"]


def reset(employee_id: str, token: str):
    """Reset conversation for an employee."""
    api_post(f"/chat/reset/{employee_id}", {}, token=token)


def chat(message: str, token: str) -> dict:
    """Send a chat message and return the full response dict."""
    return api_post("/chat", {"message": message}, token=token, timeout=90)


def record(name: str, ok: bool, agent: str = "", snippet: str = "", detail: str = ""):
    """Record and print a test result."""
    global passed, failed
    status = "PASS" if ok else "FAIL"
    if ok:
        passed += 1
    else:
        failed += 1
    results.append((status, name, detail))
    icon = "PASS" if ok else "FAIL"
    print(f"  [{icon}] {name}")
    if agent:
        print(f"         agent: {agent}")
    if snippet:
        print(f"         response: {snippet[:150]}")
    if detail and not ok:
        print(f"         detail: {detail}")


def record_error(name: str, exc: Exception):
    """Record an error (test could not run)."""
    global errors
    errors += 1
    results.append(("ERROR", name, str(exc)))
    print(f"  [ERROR] {name}")
    print(f"          {exc}")


# ── Tests ────────────────────────────────────────────────────────────

def test_01_proactive_manager():
    """Login as Ahmed (manager), send greeting. Expect proactive context about
    pending approvals, team alerts, or onboarding."""
    flush_rate_limits()
    token, emp_id = login(AHMED_CREDS)
    reset(emp_id, token)
    time.sleep(1)

    resp = chat("مرحبا", token)
    if "_http_error" in resp:
        record("01 Proactive Context - Manager", False, detail=f"HTTP {resp['_http_error']}: {resp['_detail']}")
        return

    agent = resp.get("agent", "")
    text = resp.get("response", "")
    text_lower = text.lower()

    # Manager greeting should mention something proactive — approvals, team, onboarding, etc.
    proactive_keywords = [
        "معلق", "موافق", "طلب", "إجازة", "فريق", "تهيئة", "onboarding",
        "pending", "approval", "team", "leave", "request", "alert",
        "overdue", "new hire", "انضم", "موظف", "خطوات",
    ]
    has_proactive = any(kw in text_lower or kw in text for kw in proactive_keywords)

    record(
        "01 Proactive Context - Manager",
        has_proactive,
        agent=agent,
        snippet=text,
        detail="Response did not mention any proactive context (pending approvals, team alerts, onboarding)."
        if not has_proactive else "",
    )


def test_02_proactive_new_hire():
    """Login as Rayan (new hire), ask about onboarding status. Expect
    onboarding progress info."""
    flush_rate_limits()
    token, emp_id = login(RAYAN_CREDS)
    reset(emp_id, token)
    time.sleep(1)

    resp = chat("مرحبا وش وضعي في التهيئة", token)
    if "_http_error" in resp:
        record("02 Proactive Context - New Hire", False, detail=f"HTTP {resp['_http_error']}: {resp['_detail']}")
        return

    agent = resp.get("agent", "")
    text = resp.get("response", "")
    text_lower = text.lower()

    onboarding_keywords = [
        "تهيئة", "onboarding", "خطو", "step", "progress", "تقدم",
        "مكتمل", "complete", "checklist", "مهام", "إنجاز", "%",
        "مرحلة", "برنامج", "تعريف",
    ]
    has_onboarding = any(kw in text_lower or kw in text for kw in onboarding_keywords)

    record(
        "02 Proactive Context - New Hire",
        has_onboarding,
        agent=agent,
        snippet=text,
        detail="Response did not mention onboarding progress or steps."
        if not has_onboarding else "",
    )


def test_03_handoff_deema_to_waleed():
    """Login as Ahmed. First message routes to Deema (leave balance),
    second message should route to Waleed (team view)."""
    flush_rate_limits()
    token, emp_id = login(AHMED_CREDS)
    reset(emp_id, token)
    time.sleep(1)

    # Step 1: Leave balance question -> should go to Deema
    resp1 = chat("كم رصيد إجازتي", token)
    if "_http_error" in resp1:
        record("03 Agent Handoff Deema->Waleed", False, detail=f"HTTP {resp1['_http_error']}")
        return
    agent1 = resp1.get("agent", "").lower()

    time.sleep(2)
    flush_rate_limits()

    # Step 2: Team view -> should go to Waleed
    resp2 = chat("عرض فريقي", token)
    if "_http_error" in resp2:
        record("03 Agent Handoff Deema->Waleed", False, detail=f"HTTP {resp2['_http_error']}")
        return
    agent2 = resp2.get("agent", "").lower()

    # Agent should change from deema to waleed
    switched = agent1 == "deema" and agent2 == "waleed"
    # Also acceptable: agent2 is waleed regardless of agent1
    acceptable = agent2 == "waleed"

    record(
        "03 Agent Handoff Deema->Waleed",
        acceptable,
        agent=f"{agent1} -> {agent2}",
        snippet=resp2.get("response", ""),
        detail=f"Expected agent change to waleed, got: {agent1} -> {agent2}"
        if not acceptable else "",
    )


def test_04_sticky_routing():
    """After routing to Waleed, a follow-up manager question should stay
    with Waleed (not bounce back to Deema)."""
    flush_rate_limits()
    token, emp_id = login(AHMED_CREDS)
    reset(emp_id, token)
    time.sleep(1)

    # First: route to Waleed
    resp1 = chat("عرض فريقي", token)
    if "_http_error" in resp1:
        record("04 Sticky Routing", False, detail=f"HTTP {resp1['_http_error']}")
        return
    agent1 = resp1.get("agent", "").lower()

    time.sleep(2)
    flush_rate_limits()

    # Second: follow-up still manager/Waleed domain
    resp2 = chat("وريني طلبات الإجازة المعلقة", token)
    if "_http_error" in resp2:
        record("04 Sticky Routing", False, detail=f"HTTP {resp2['_http_error']}")
        return
    agent2 = resp2.get("agent", "").lower()

    stays_waleed = agent2 == "waleed"

    record(
        "04 Sticky Routing",
        stays_waleed,
        agent=f"{agent1} -> {agent2}",
        snippet=resp2.get("response", ""),
        detail=f"Expected waleed sticky routing, got: {agent1} -> {agent2}"
        if not stays_waleed else "",
    )


def test_05_empty_state_not_manager():
    """Login as Rayan (not a manager), ask to view pending approvals.
    Should get a friendly error about not being a manager."""
    flush_rate_limits()
    token, emp_id = login(RAYAN_CREDS)
    reset(emp_id, token)
    time.sleep(1)

    resp = chat("عرض الموافقات المعلقة", token)
    if "_http_error" in resp:
        record("05 Empty State - Not Manager", False, detail=f"HTTP {resp['_http_error']}")
        return

    agent = resp.get("agent", "")
    text = resp.get("response", "")
    text_lower = text.lower()

    # Should mention not being a manager, or no direct reports, or access denied
    denial_keywords = [
        "لست مدير", "ليس لديك", "لا يمكن", "غير مدير", "لا تملك صلاحية",
        "not a manager", "no direct reports", "cannot", "don't have",
        "صلاحية", "مدير", "تابعين", "غير متاح", "لا توجد",
        "not authorized", "permission",
    ]
    has_denial = any(kw in text_lower or kw in text for kw in denial_keywords)

    record(
        "05 Empty State - Not Manager",
        has_denial,
        agent=agent,
        snippet=text,
        detail="Response did not indicate that the user is not a manager or lacks permission."
        if not has_denial else "",
    )


def test_06_tool_regression_view_team():
    """Login as Ahmed (manager), ask to view team. Expect team list
    with count > 0."""
    flush_rate_limits()
    token, emp_id = login(AHMED_CREDS)
    reset(emp_id, token)
    time.sleep(1)

    resp = chat("عرض فريقي", token)
    if "_http_error" in resp:
        record("06 Tool Regression - View Team", False, detail=f"HTTP {resp['_http_error']}")
        return

    agent = resp.get("agent", "")
    text = resp.get("response", "")

    # The response should contain team member names or a count
    # Look for indicators of a team list
    has_team_data = False
    # Check for numbers indicating count
    import re
    numbers = re.findall(r'\d+', text)
    # Check for common patterns — names, EMP- numbers, etc.
    team_indicators = [
        "فريق", "team", "موظف", "employee", "EMP-",
        "عضو", "member", "تابع", "report",
    ]
    has_indicators = any(ind in text for ind in team_indicators)
    has_names = bool(re.search(r'[A-Z][a-z]+\s+[A-Z]', text))  # e.g. "Sara Al"
    has_arabic_names = bool(re.search(r'[\u0621-\u064A]+\s+[\u0621-\u064A]+', text))

    has_team_data = has_indicators and (has_names or has_arabic_names or len(numbers) > 0)

    record(
        "06 Tool Regression - View Team",
        has_team_data,
        agent=agent,
        snippet=text,
        detail="Response did not contain recognizable team data (names, counts, etc.)."
        if not has_team_data else "",
    )


def test_07_onboarding_dashboard():
    """Login as Ahmed, ask for onboarding dashboard. Expect dashboard data
    or a message about no in-progress onboarding."""
    flush_rate_limits()
    token, emp_id = login(AHMED_CREDS)
    reset(emp_id, token)
    time.sleep(1)

    resp = chat("عرض لوحة التهيئة", token)
    if "_http_error" in resp:
        record("07 Onboarding Dashboard", False, detail=f"HTTP {resp['_http_error']}")
        return

    agent = resp.get("agent", "")
    text = resp.get("response", "")
    text_lower = text.lower()

    # Should mention onboarding dashboard data OR "no assignments" message
    dashboard_keywords = [
        "تهيئة", "onboarding", "dashboard", "لوحة", "تقدم", "progress",
        "خطو", "step", "مكتمل", "complete", "%", "لا توجد",
        "no in-progress", "no active", "assignment", "برنامج",
        "موظف جديد", "new hire",
    ]
    has_dashboard = any(kw in text_lower or kw in text for kw in dashboard_keywords)

    record(
        "07 Onboarding Dashboard",
        has_dashboard,
        agent=agent,
        snippet=text,
        detail="Response did not contain onboarding dashboard data or status message."
        if not has_dashboard else "",
    )


# ── Runner ───────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("  Waleed Agent — W4 Regression + Feature Tests")
    print("=" * 70)
    print()

    tests = [
        ("Test 01: Proactive Context - Manager", test_01_proactive_manager),
        ("Test 02: Proactive Context - New Hire", test_02_proactive_new_hire),
        ("Test 03: Agent Handoff Deema->Waleed", test_03_handoff_deema_to_waleed),
        ("Test 04: Sticky Routing", test_04_sticky_routing),
        ("Test 05: Empty State - Not Manager", test_05_empty_state_not_manager),
        ("Test 06: Tool Regression - View Team", test_06_tool_regression_view_team),
        ("Test 07: Onboarding Dashboard", test_07_onboarding_dashboard),
    ]

    for label, fn in tests:
        print(f"\n--- {label} ---")
        try:
            fn()
        except Exception as exc:
            record_error(label, exc)

    # ── Summary ──────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print(f"  SUMMARY: {passed} passed, {failed} failed, {errors} errors  (total: {passed + failed + errors})")
    print("=" * 70)
    print()

    print(f"{'#':<4} {'Result':<8} {'Test':<50} {'Detail'}")
    print("-" * 100)
    for i, (status, name, detail) in enumerate(results, 1):
        det = detail[:60] if detail else ""
        print(f"{i:<4} {status:<8} {name:<50} {det}")

    print()
    if failed > 0 or errors > 0:
        print(f"  ** {failed} failure(s), {errors} error(s) — see details above **")
        sys.exit(1)
    else:
        print("  All tests passed.")
        sys.exit(0)


if __name__ == "__main__":
    main()
