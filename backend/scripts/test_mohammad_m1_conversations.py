#!/usr/bin/env python3
"""Mohammad M1 Multi-Turn Conversation Tests -- Huda (Conversation Tester)

Tests multi-turn conversation quality for the recruitment agent:
- Full pipeline walkthrough (pipeline summary -> postings -> details -> candidates -> screening)
- Create-and-fill flow (generate JD -> create posting -> add candidate -> screen)
- Agent handoff (Mohammad -> Deema -> Mohammad)
- Context retention across turns
- Arabic language consistency

Usage:
    cd /Users/najwamalghamdi/Desktop/HR-AI-Startup/backend
    source venv/bin/activate
    python -m scripts.seed_recruitment   # ensure seed data exists
    python scripts/test_mohammad_m1_conversations.py
"""
import json
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime

# -- Configuration ---------------------------------------------------------
BASE_URL = "http://localhost:8000/api/v1"
TIMEOUT = 120

EMPLOYEES = {
    "ahmed": {"employee_number": "EMP-001", "national_id_last4": "5432"},
    "rayan": {"employee_number": "EMP-007", "national_id_last4": "0987"},
}

# -- Helpers ---------------------------------------------------------------

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
    payload = {"message": message}
    if agent:
        payload["agent"] = agent
    return api_request("POST", "/chat", payload, token=token)


def has_arabic(text: str) -> bool:
    """Check if text contains Arabic characters."""
    return any("\u0600" <= c <= "\u06FF" for c in text)


def truncate(text: str, n: int = 150) -> str:
    if len(text) <= n:
        return text
    return text[:n] + "..."


# -- Turn Result -----------------------------------------------------------

class TurnResult:
    def __init__(self, turn: int, message: str, expected_agent: str,
                 checks: list[str]):
        self.turn = turn
        self.message = message
        self.expected_agent = expected_agent
        self.checks = checks
        self.actual_agent = ""
        self.response = ""
        self.conversation_id = ""
        self.passed_checks: list[str] = []
        self.failed_checks: list[str] = []
        self.status = "SKIP"
        self.error = ""
        self.duration = 0.0


# -- Scenario Runner -------------------------------------------------------

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

            # -- Check: correct agent --
            if tr.actual_agent == expected_agent:
                tr.passed_checks.append(f"agent={expected_agent}")
            else:
                tr.failed_checks.append(
                    f"agent: expected={expected_agent}, got={tr.actual_agent}"
                )

            # -- Check: Arabic response --
            if "arabic" in checks:
                if has_arabic(tr.response):
                    tr.passed_checks.append("arabic_response")
                else:
                    tr.failed_checks.append("arabic_response: no Arabic chars found")

            # -- Check: same conversation --
            if "same_conversation" in checks and conversation_id:
                if tr.conversation_id == conversation_id:
                    tr.passed_checks.append("same_conversation")
                else:
                    tr.failed_checks.append(
                        f"conversation_id changed: {conversation_id[:8]} -> {tr.conversation_id[:8]}"
                    )

            # -- Check: keywords present --
            if "keywords" in turn:
                resp_lower = tr.response.lower()
                for kw in turn["keywords"]:
                    if kw.lower() in resp_lower or kw in tr.response:
                        tr.passed_checks.append(f"keyword:{kw}")
                    else:
                        tr.failed_checks.append(f"keyword_missing:{kw}")

            # -- Check: non-empty response --
            if "nonempty" in checks:
                if len(tr.response.strip()) > 20:
                    tr.passed_checks.append("nonempty")
                else:
                    tr.failed_checks.append("response too short or empty")

            # -- Check: no raw JSON in response --
            if "no_raw_json" in checks:
                if '{"' not in tr.response and "\\n" not in tr.response[:50]:
                    tr.passed_checks.append("no_raw_json")
                else:
                    tr.failed_checks.append("raw JSON detected in response")

            # -- Check: context retention (keywords from previous turn) --
            if "context_keywords" in turn:
                resp_lower = tr.response.lower()
                for kw in turn["context_keywords"]:
                    if kw.lower() in resp_lower or kw in tr.response:
                        tr.passed_checks.append(f"context:{kw}")
                    else:
                        tr.failed_checks.append(f"context_lost:{kw}")

            # -- Check: no 500 / crash --
            if "no_crash" in checks:
                tr.passed_checks.append("no_crash")

            # Overall status
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
    print(f"    Response: {truncate(tr.response, 200)}")
    if tr.passed_checks:
        print(f"    Passed:   {', '.join(tr.passed_checks)}")
    if tr.failed_checks:
        print(f"    FAILED:   {', '.join(tr.failed_checks)}")
    if tr.error:
        print(f"    Error:    {tr.error}")


# -- Scenario Definitions -------------------------------------------------

def scenario_1_full_pipeline() -> list[TurnResult]:
    """Scenario 1: Full Recruitment Pipeline (5 turns)
    Pipeline summary -> list postings -> posting details -> candidates -> screen candidate
    """
    turns = [
        {
            "message": "محمد، وش وضع التوظيف عندنا؟",
            "expected_agent": "mohammad",
            "checks": ["arabic", "nonempty", "same_conversation", "no_raw_json", "no_crash"],
            "keywords": ["وظيف", "مرشح"],  # Should mention postings/candidates
        },
        {
            "message": "وريني الوظائف الشاغرة",
            "expected_agent": "mohammad",
            "checks": ["arabic", "nonempty", "same_conversation", "no_raw_json"],
            "keywords": ["مهندس", "برمجيات"],  # Should list the SW engineer posting
        },
        {
            "message": "عطني تفاصيل وظيفة مهندس البرمجيات",
            "expected_agent": "mohammad",
            "checks": ["arabic", "nonempty", "same_conversation", "no_raw_json"],
            "keywords": ["Python", "مهندس"],  # Details should mention Python
        },
        {
            "message": "وريني المرشحين لهالوظيفة",
            "expected_agent": "mohammad",
            "checks": ["arabic", "nonempty", "same_conversation", "no_raw_json"],
            "keywords": ["أحمد", "سارة"],  # Known candidates: Ahmed Al-Rashid, Sara Al-Dosari
        },
        {
            "message": "افحص لي أحمد الرشيدي",
            "expected_agent": "mohammad",
            "checks": ["arabic", "nonempty", "same_conversation", "no_crash"],
            # AI screening — should produce a score or analysis
        },
    ]
    return run_scenario(
        "S1: Full Recruitment Pipeline (5 turns, all Mohammad, Arabic)",
        "ahmed",
        turns,
    )


def scenario_2_create_and_fill() -> list[TurnResult]:
    """Scenario 2: Create and Fill a Role (4 turns)
    Generate JD -> Create posting -> Add candidate -> Screen candidate
    """
    turns = [
        {
            "message": "اكتب وصف وظيفي لمحلل بيانات",
            "expected_agent": "mohammad",
            "checks": ["arabic", "nonempty", "same_conversation", "no_crash"],
            # Should generate a JD with AI
        },
        {
            "message": "أنشئ الوظيفة",
            "expected_agent": "mohammad",
            "checks": ["nonempty", "same_conversation", "no_crash"],
            # Should create the posting from the generated JD
        },
        {
            "message": "أضف مرشح اسمه خالد البكري ايميله khalid@test.com",
            "expected_agent": "mohammad",
            "checks": ["nonempty", "same_conversation", "no_crash"],
            "keywords": ["خالد"],
        },
        {
            "message": "افحص خالد",
            "expected_agent": "mohammad",
            "checks": ["nonempty", "same_conversation", "no_crash"],
            # Should screen the candidate that was just added
            "context_keywords": ["خالد"],  # Context retention: remembers Khalid
        },
    ]
    return run_scenario(
        "S2: Create and Fill a Role (4 turns, JD->Post->Add->Screen)",
        "ahmed",
        turns,
    )


def scenario_3_agent_handoff() -> list[TurnResult]:
    """Scenario 3: Agent Handoff Round-Trip (3 turns)
    Mohammad -> Deema -> Mohammad
    """
    turns = [
        {
            "message": "وش وضع التوظيف عندنا؟",
            "expected_agent": "mohammad",
            "checks": ["arabic", "nonempty", "same_conversation", "no_crash"],
        },
        {
            "message": "وش رصيد إجازتي السنوية؟",
            "expected_agent": "deema",
            "checks": ["arabic", "nonempty", "same_conversation", "no_crash"],
            "keywords": ["إجاز"],  # Should mention leave/balance
        },
        {
            "message": "وريني المرشحين لوظيفة مهندس البرمجيات",
            "expected_agent": "mohammad",
            "checks": ["arabic", "nonempty", "same_conversation", "no_crash"],
            "keywords": ["مرشح"],  # Should route back to Mohammad with candidates
        },
    ]
    return run_scenario(
        "S3: Agent Handoff (Mohammad -> Deema -> Mohammad)",
        "ahmed",
        turns,
    )


def scenario_4_context_retention() -> list[TurnResult]:
    """Scenario 4: Context Retention (3 turns)
    Ask about a specific posting, then refer to it implicitly.
    """
    turns = [
        {
            "message": "عطني تفاصيل وظيفة مهندس البرمجيات",
            "expected_agent": "mohammad",
            "checks": ["arabic", "nonempty", "same_conversation"],
        },
        {
            "message": "كم عدد المرشحين عليها؟",
            "expected_agent": "mohammad",
            "checks": ["nonempty", "same_conversation"],
            # "عليها" = on it — should understand "it" refers to SW Engineer posting
            # The posting has 6 candidates
        },
        {
            "message": "مين أقوى مرشح؟",
            "expected_agent": "mohammad",
            "checks": ["nonempty", "same_conversation"],
            # Should identify Nora Al-Qahtani (score 91) as the top candidate
            "keywords": ["نورة", "Nora"],  # Either Arabic or English name
        },
    ]
    return run_scenario(
        "S4: Context Retention (posting -> implicit 'it' -> strongest candidate)",
        "ahmed",
        turns,
    )


def scenario_5_bilingual_switch() -> list[TurnResult]:
    """Scenario 5: Bilingual Mid-Conversation Switch (3 turns)
    Start in Arabic, switch to English, back to Arabic
    """
    turns = [
        {
            "message": "محمد، وش وضع التوظيف؟",
            "expected_agent": "mohammad",
            "checks": ["arabic", "nonempty", "same_conversation"],
        },
        {
            "message": "Show me the candidates for the Software Engineer position",
            "expected_agent": "mohammad",
            "checks": ["nonempty", "same_conversation"],
            # Should handle English mid-conversation
        },
        {
            "message": "عطني تقرير عن أحمد الرشيدي",
            "expected_agent": "mohammad",
            "checks": ["arabic", "nonempty", "same_conversation"],
        },
    ]
    return run_scenario(
        "S5: Bilingual Switch (Arabic -> English -> Arabic)",
        "ahmed",
        turns,
    )


# -- Main ------------------------------------------------------------------

def main():
    print("=" * 70)
    print("MOHAMMAD M1 MULTI-TURN CONVERSATION TESTS -- Huda (Conversation Tester)")
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

    # Pre-flight: Login test user
    print("\n[Pre-flight] Logging in test users...")
    for name in ["ahmed"]:
        tok, eid = login(name)
        if tok:
            print(f"  OK: {name} -> {eid[:8]}...")
        else:
            print(f"  FAIL: {name} login failed")
            sys.exit(1)

    # Run scenarios
    all_results: list[tuple[str, list[TurnResult]]] = []

    s1 = scenario_1_full_pipeline()
    all_results.append(("S1: Full Recruitment Pipeline", s1))

    s2 = scenario_2_create_and_fill()
    all_results.append(("S2: Create and Fill a Role", s2))

    s3 = scenario_3_agent_handoff()
    all_results.append(("S3: Agent Handoff", s3))

    s4 = scenario_4_context_retention()
    all_results.append(("S4: Context Retention", s4))

    s5 = scenario_5_bilingual_switch()
    all_results.append(("S5: Bilingual Switch", s5))

    # -- Summary -----------------------------------------------------------
    print("\n" + "=" * 70)
    print("CONVERSATION TEST REPORT -- Mohammad M1")
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
            print(f"  Turn {r.turn}: [{icon}] {r.status} | agent={agent_ok} | {truncate(r.message, 50)}")
            if r.failed_checks:
                for fc in r.failed_checks:
                    print(f"         FAIL: {fc}")

    print(f"\n{'=' * 70}")
    print(f"TOTAL: {total_turns} turns | PASS: {total_pass} | FAIL: {total_fail} | ERROR: {total_error}")
    rate = (total_pass / total_turns * 100) if total_turns > 0 else 0
    print(f"Pass Rate: {rate:.0f}%")
    print(f"{'=' * 70}")

    # -- Agent Routing Table -----------------------------------------------
    print("\nAgent Routing Analysis:")
    print(f"{'Scenario':<35} {'Turn':<6} {'Expected':<12} {'Actual':<12} {'Match':<6}")
    print("-" * 73)
    for scenario_name, results in all_results:
        for r in results:
            match = "YES" if r.actual_agent == r.expected_agent else "NO"
            short_name = scenario_name[:33]
            print(f"{short_name:<35} {r.turn:<6} {r.expected_agent:<12} {r.actual_agent:<12} {match:<6}")

    # -- Arabic Consistency ------------------------------------------------
    print("\nArabic Response Consistency:")
    for scenario_name, results in all_results:
        arabic_count = sum(1 for r in results if has_arabic(r.response))
        print(f"  {scenario_name}: {arabic_count}/{len(results)} turns had Arabic responses")

    # -- Conversation ID Preservation --------------------------------------
    print("\nConversation ID Preservation:")
    for scenario_name, results in all_results:
        if results:
            first_cid = results[0].conversation_id
            all_same = all(r.conversation_id == first_cid for r in results)
            status_str = "PRESERVED" if all_same else "BROKEN"
            print(f"  {scenario_name}: {status_str} (id={first_cid[:8] if first_cid else 'N/A'}...)")

    # -- Context Retention Score -------------------------------------------
    print("\nContext Retention Score:")
    for scenario_name, results in all_results:
        context_checks = 0
        context_pass = 0
        for r in results:
            for c in r.passed_checks:
                if c.startswith("context:"):
                    context_checks += 1
                    context_pass += 1
            for c in r.failed_checks:
                if c.startswith("context_lost:"):
                    context_checks += 1
        if context_checks > 0:
            pct = context_pass / context_checks * 100
            print(f"  {scenario_name}: {context_pass}/{context_checks} ({pct:.0f}%)")
        else:
            print(f"  {scenario_name}: No context checks defined")

    # -- Issues Found ------------------------------------------------------
    issues = []
    for scenario_name, results in all_results:
        for r in results:
            if r.status in ("FAIL", "ERROR"):
                issues.append((scenario_name, r))

    if issues:
        print(f"\nIssues Found ({len(issues)}):")
        print(f"{'#':<4} {'Severity':<10} {'Scenario':<30} {'Turn':<6} {'Issue'}")
        print("-" * 85)
        for i, (sname, r) in enumerate(issues, 1):
            severity = "Critical" if r.status == "ERROR" else "Major"
            issue_desc = "; ".join(r.failed_checks) if r.failed_checks else r.error
            print(f"{i:<4} {severity:<10} {sname[:28]:<30} {r.turn:<6} {issue_desc[:70]}")
    else:
        print("\nNo issues found -- all turns passed.")

    # -- Response Time Analysis --------------------------------------------
    print("\nResponse Time Analysis:")
    for scenario_name, results in all_results:
        if results:
            times = [r.duration for r in results if r.duration > 0]
            if times:
                avg = sum(times) / len(times)
                mx = max(times)
                print(f"  {scenario_name}: avg={avg:.1f}s, max={mx:.1f}s")

    print(f"\nCompleted: {datetime.now().isoformat()}")

    # Exit code
    sys.exit(1 if total_fail > 0 or total_error > 0 else 0)


if __name__ == "__main__":
    main()
