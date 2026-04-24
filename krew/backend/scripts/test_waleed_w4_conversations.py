#!/usr/bin/env python3
"""Waleed W4 Multi-Turn Conversation Tests -- Huda (Conversation Tester)

Tests multi-turn conversation quality: agent stickiness, handoffs,
context retention, and Arabic language consistency across turns.

Usage:
    cd /Users/najwamalghamdi/Desktop/HR-AI-Startup/backend
    source venv/bin/activate
    python scripts/test_waleed_w4_conversations.py
"""
import json
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime

# ── Configuration ──────────────────────────────────────────────────
BASE_URL = "http://localhost:8000/api/v1"
TIMEOUT = 120

EMPLOYEES = {
    "ahmed": {"employee_number": "EMP-001", "national_id_last4": "5432"},
    "rayan": {"employee_number": "EMP-007", "national_id_last4": "0987"},
}

# ── Helpers ────────────────────────────────────────────────────────

tokens: dict[str, str] = {}
employee_ids: dict[str, str] = {}


def flush_rate_limits():
    """Clear all rate limit keys from Redis."""
    try:
        import redis
        r = redis.from_url("redis://localhost:6379")
        keys = list(r.scan_iter("rl:*"))
        if keys:
            r.delete(*keys)
        # Also clear login lockout keys
        lock_keys = list(r.scan_iter("krew:login_fail:*"))
        if lock_keys:
            r.delete(*lock_keys)
    except Exception as e:
        print(f"  [WARN] Could not flush Redis rate limits: {e}")


def api_request(method: str, path: str, data: dict = None,
                token: str = None) -> tuple[int, dict]:
    """Make an HTTP request and return (status_code, json_body)."""
    url = f"{BASE_URL}{path}"
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
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


def login(name: str) -> tuple[str, str]:
    """Login and return (token, employee_id). Caches results."""
    if name in tokens:
        return tokens[name], employee_ids[name]

    flush_rate_limits()
    creds = EMPLOYEES[name]
    status, body = api_request("POST", "/chat/auth/login", creds)
    if status != 200:
        print(f"  [LOGIN FAIL] {name}: {status} {body}")
        return "", ""

    tok = body["token"]
    eid = body["employee_id"]
    tokens[name] = tok
    employee_ids[name] = eid
    return tok, eid


def reset_conversation(name: str):
    """Reset conversation for a named employee."""
    if name not in tokens:
        return
    flush_rate_limits()
    api_request("POST", f"/chat/reset/{employee_ids[name]}", token=tokens[name])
    time.sleep(0.5)


def chat(token: str, message: str, agent: str = "") -> tuple[int, dict]:
    """Send a chat message. No agent override -- let orchestrator route."""
    flush_rate_limits()
    return api_request("POST", "/chat", {
        "message": message,
        "agent": agent,
    }, token=token)


def has_arabic(text: str) -> bool:
    """Check if text contains Arabic characters."""
    return any("\u0600" <= c <= "\u06FF" for c in text)


def truncate(text: str, n: int = 150) -> str:
    """Truncate text for display."""
    if len(text) <= n:
        return text
    return text[:n] + "..."


# ── Turn Result ────────────────────────────────────────────────────

class TurnResult:
    def __init__(self, turn: int, message: str, expected_agent: str,
                 checks: list[str]):
        self.turn = turn
        self.message = message
        self.expected_agent = expected_agent
        self.checks = checks  # list of check names
        self.actual_agent = ""
        self.response = ""
        self.conversation_id = ""
        self.passed_checks: list[str] = []
        self.failed_checks: list[str] = []
        self.status = "SKIP"
        self.error = ""
        self.duration = 0.0


# ── Scenario Runner ───────────────────────────────────────────────

def run_scenario(name: str, employee: str, turns: list[dict]) -> list[TurnResult]:
    """Run a multi-turn scenario and return results for each turn."""
    print(f"\n{'=' * 70}")
    print(f"SCENARIO: {name}")
    print(f"Employee: {employee}")
    print(f"{'=' * 70}")

    tok, eid = login(employee)
    if not tok:
        print("  FATAL: Login failed, skipping scenario")
        return []

    reset_conversation(employee)

    results = []
    conversation_id = None

    for i, turn in enumerate(turns):
        turn_num = i + 1
        msg = turn["message"]
        expected_agent = turn["expected_agent"]
        checks = turn.get("checks", [])

        tr = TurnResult(turn_num, msg, expected_agent, checks)
        start = time.time()

        try:
            flush_rate_limits()
            status, body = chat(tok, msg)
            tr.duration = time.time() - start

            if status != 200:
                tr.status = "ERROR"
                tr.error = f"HTTP {status}: {json.dumps(body, ensure_ascii=False)[:200]}"
                results.append(tr)
                _print_turn(tr)
                continue

            tr.actual_agent = body.get("agent", "")
            tr.response = body.get("response", "")
            tr.conversation_id = body.get("conversation_id", "")

            if conversation_id is None:
                conversation_id = tr.conversation_id

            # Run checks
            # Check 1: Correct agent
            if "agent" in checks or True:  # Always check agent
                if tr.actual_agent == expected_agent:
                    tr.passed_checks.append(f"agent={expected_agent}")
                else:
                    tr.failed_checks.append(
                        f"agent: expected={expected_agent}, got={tr.actual_agent}"
                    )

            # Check 2: Arabic response
            if "arabic" in checks:
                if has_arabic(tr.response):
                    tr.passed_checks.append("arabic_response")
                else:
                    tr.failed_checks.append("arabic_response: no Arabic chars found")

            # Check 3: Conversation ID preserved
            if "same_conversation" in checks and conversation_id:
                if tr.conversation_id == conversation_id:
                    tr.passed_checks.append("same_conversation")
                else:
                    tr.failed_checks.append(
                        f"conversation_id changed: {conversation_id[:8]} -> {tr.conversation_id[:8]}"
                    )

            # Check 4: Contains keywords
            if "keywords" in turn:
                resp_lower = tr.response.lower()
                for kw in turn["keywords"]:
                    if kw.lower() in resp_lower or kw in tr.response:
                        tr.passed_checks.append(f"keyword:{kw}")
                    else:
                        tr.failed_checks.append(f"keyword_missing:{kw}")

            # Check 5: Non-empty response
            if "nonempty" in checks:
                if len(tr.response.strip()) > 20:
                    tr.passed_checks.append("nonempty")
                else:
                    tr.failed_checks.append("response too short or empty")

            # Determine overall status
            if tr.failed_checks:
                tr.status = "FAIL"
            else:
                tr.status = "PASS"

        except Exception as e:
            tr.status = "ERROR"
            tr.error = str(e)
            tr.duration = time.time() - start

        results.append(tr)
        _print_turn(tr)

    return results


def _print_turn(tr: TurnResult):
    """Print a single turn result."""
    icon = {"PASS": "+", "FAIL": "X", "ERROR": "E", "SKIP": "-"}.get(tr.status, "?")
    print(f"\n  Turn {tr.turn}: [{icon}] {tr.status} ({tr.duration:.1f}s)")
    print(f"    Input:    {tr.message}")
    print(f"    Agent:    expected={tr.expected_agent}, actual={tr.actual_agent}")
    print(f"    Response: {truncate(tr.response, 150)}")
    if tr.passed_checks:
        print(f"    Passed:   {', '.join(tr.passed_checks)}")
    if tr.failed_checks:
        print(f"    FAILED:   {', '.join(tr.failed_checks)}")
    if tr.error:
        print(f"    Error:    {tr.error}")


# ── Scenario Definitions ──────────────────────────────────────────

def scenario_1_manager_demo_flow() -> list[TurnResult]:
    """Scenario 1: Manager Full Demo Flow (Ahmed, 4 turns)
    All turns should stay with Waleed, Arabic responses, tool usage.
    """
    turns = [
        {
            "message": "عرض فريقي",
            "expected_agent": "waleed",
            "checks": ["arabic", "nonempty", "same_conversation"],
        },
        {
            "message": "وريني طلبات الإجازة المعلقة",
            "expected_agent": "waleed",
            "checks": ["arabic", "nonempty", "same_conversation"],
        },
        {
            "message": "عرض لوحة التهيئة",
            "expected_agent": "waleed",
            "checks": ["arabic", "nonempty", "same_conversation"],
        },
        {
            "message": "كم عدد فريقي؟",
            "expected_agent": "waleed",
            "checks": ["arabic", "nonempty", "same_conversation"],
        },
    ]
    return run_scenario(
        "S1: Manager Full Demo Flow (4 turns, all Waleed, Arabic)",
        "ahmed",
        turns,
    )


def scenario_2_new_hire_onboarding() -> list[TurnResult]:
    """Scenario 2: New Hire Onboarding Flow (Rayan, 3 turns)
    All turns with Waleed, Arabic, context retention.
    """
    turns = [
        {
            "message": "وش باقي عليّ في التهيئة؟",
            "expected_agent": "waleed",
            "checks": ["arabic", "nonempty", "same_conversation"],
        },
        {
            "message": "مين مديري؟",
            "expected_agent": "waleed",
            "checks": ["arabic", "nonempty", "same_conversation"],
        },
        {
            "message": "شكرا وليد",
            "expected_agent": "waleed",
            "checks": ["arabic", "nonempty", "same_conversation"],
        },
    ]
    return run_scenario(
        "S2: New Hire Onboarding Flow (3 turns, Waleed sticky, Arabic)",
        "rayan",
        turns,
    )


def scenario_3_agent_handoff_roundtrip() -> list[TurnResult]:
    """Scenario 3: Agent Handoff Round-Trip (Ahmed, 4 turns)
    Deema -> Waleed -> Waleed (sticky) -> Deema
    """
    turns = [
        {
            "message": "كم رصيد إجازتي السنوية؟",
            "expected_agent": "deema",
            "checks": ["arabic", "nonempty", "same_conversation"],
        },
        {
            "message": "عرض فريقي",
            "expected_agent": "waleed",
            "checks": ["arabic", "nonempty", "same_conversation"],
        },
        {
            "message": "وريني طلبات الإجازة المعلقة",
            "expected_agent": "waleed",
            "checks": ["arabic", "nonempty", "same_conversation"],
        },
        {
            "message": "وش رصيد إجازتي المرضية؟",
            "expected_agent": "deema",
            "checks": ["arabic", "nonempty", "same_conversation"],
        },
    ]
    return run_scenario(
        "S3: Agent Handoff Round-Trip (Deema -> Waleed -> Waleed -> Deema)",
        "ahmed",
        turns,
    )


# ── Main ───────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("WALEED W4 MULTI-TURN CONVERSATION TESTS -- Huda (Conversation Tester)")
    print(f"Started: {datetime.now().isoformat()}")
    print(f"API: {BASE_URL}")
    print("=" * 70)

    # Pre-flight: API reachable
    print("\n[Pre-flight] Checking API...")
    flush_rate_limits()
    status, body = api_request("GET", "/chat/tenants")
    if status != 200:
        print(f"  FATAL: API not reachable at {BASE_URL} (status={status})")
        sys.exit(1)
    print(f"  OK: API reachable, {len(body)} tenant(s)")

    # Pre-flight: Login both users
    print("\n[Pre-flight] Logging in test users...")
    for name in ["ahmed", "rayan"]:
        tok, eid = login(name)
        if tok:
            print(f"  OK: {name} -> {eid[:8]}...")
        else:
            print(f"  FAIL: {name} login failed")
            sys.exit(1)

    # Run scenarios
    all_results: list[tuple[str, list[TurnResult]]] = []

    s1 = scenario_1_manager_demo_flow()
    all_results.append(("S1: Manager Full Demo Flow", s1))

    s2 = scenario_2_new_hire_onboarding()
    all_results.append(("S2: New Hire Onboarding Flow", s2))

    s3 = scenario_3_agent_handoff_roundtrip()
    all_results.append(("S3: Agent Handoff Round-Trip", s3))

    # ── Summary ────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("CONVERSATION TEST REPORT -- Waleed W4")
    print("=" * 70)

    total_turns = 0
    total_pass = 0
    total_fail = 0
    total_error = 0

    for scenario_name, results in all_results:
        print(f"\n--- {scenario_name} ---")
        s_pass = sum(1 for r in results if r.status == "PASS")
        s_fail = sum(1 for r in results if r.status == "FAIL")
        s_err = sum(1 for r in results if r.status == "ERROR")
        total_turns += len(results)
        total_pass += s_pass
        total_fail += s_fail
        total_error += s_err
        print(f"  Turns: {len(results)} | PASS: {s_pass} | FAIL: {s_fail} | ERROR: {s_err}")

        for r in results:
            icon = {"PASS": "+", "FAIL": "X", "ERROR": "E"}.get(r.status, "?")
            agent_ok = "OK" if r.actual_agent == r.expected_agent else f"WRONG({r.actual_agent})"
            print(f"  Turn {r.turn}: [{icon}] {r.status} | agent={agent_ok} | {truncate(r.message, 40)}")
            if r.failed_checks:
                for fc in r.failed_checks:
                    print(f"         FAIL: {fc}")

    print(f"\n{'=' * 70}")
    print(f"TOTAL: {total_turns} turns | PASS: {total_pass} | FAIL: {total_fail} | ERROR: {total_error}")
    rate = (total_pass / total_turns * 100) if total_turns > 0 else 0
    print(f"Pass Rate: {rate:.0f}%")
    print(f"{'=' * 70}")

    # ── Agent Routing Table ────────────────────────────────────────
    print("\nAgent Routing Analysis:")
    print(f"{'Scenario':<35} {'Turn':<6} {'Expected':<10} {'Actual':<10} {'Match':<6}")
    print("-" * 70)
    for scenario_name, results in all_results:
        for r in results:
            match = "YES" if r.actual_agent == r.expected_agent else "NO"
            short_name = scenario_name[:33]
            print(f"{short_name:<35} {r.turn:<6} {r.expected_agent:<10} {r.actual_agent:<10} {match:<6}")

    # ── Arabic Consistency ─────────────────────────────────────────
    print("\nArabic Response Consistency:")
    for scenario_name, results in all_results:
        arabic_count = sum(1 for r in results if has_arabic(r.response))
        print(f"  {scenario_name}: {arabic_count}/{len(results)} turns had Arabic responses")

    # ── Conversation ID Preservation ───────────────────────────────
    print("\nConversation ID Preservation:")
    for scenario_name, results in all_results:
        if results:
            first_cid = results[0].conversation_id
            all_same = all(r.conversation_id == first_cid for r in results)
            status_str = "PRESERVED" if all_same else "BROKEN"
            print(f"  {scenario_name}: {status_str} (id={first_cid[:8] if first_cid else 'N/A'}...)")

    # ── Issues Found ───────────────────────────────────────────────
    issues = []
    for scenario_name, results in all_results:
        for r in results:
            if r.status in ("FAIL", "ERROR"):
                issues.append((scenario_name, r))

    if issues:
        print(f"\nIssues Found ({len(issues)}):")
        print(f"{'#':<4} {'Severity':<10} {'Scenario':<30} {'Turn':<6} {'Issue'}")
        print("-" * 80)
        for i, (sname, r) in enumerate(issues, 1):
            severity = "Critical" if r.status == "ERROR" else "Major"
            issue_desc = "; ".join(r.failed_checks) if r.failed_checks else r.error
            print(f"{i:<4} {severity:<10} {sname[:28]:<30} {r.turn:<6} {issue_desc[:60]}")
    else:
        print("\nNo issues found -- all turns passed.")

    print(f"\nCompleted: {datetime.now().isoformat()}")

    # Exit code
    sys.exit(1 if total_fail > 0 or total_error > 0 else 0)


if __name__ == "__main__":
    main()
