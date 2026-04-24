"""Waleed W2 Conversation Quality Tests — Multi-turn flows against the live API.

Uses only stdlib (urllib.request). No external dependencies.
Run: cd backend && source venv/bin/activate && python scripts/test_waleed_conversations.py
"""
import json
import sys
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field

BASE_URL = "http://localhost:8000/api/v1"

# Seed data credentials (last 4 of national_id)
AHMED = {"employee_number": "EMP-001", "national_id_last4": "5432"}   # Manager
KHALID = {"employee_number": "EMP-005", "national_id_last4": "2109"}  # Non-manager


@dataclass
class Turn:
    input_msg: str
    agent: str | None  # None = let routing decide
    expected: str       # Description of expected behavior
    response: str = ""
    actual: str = ""
    passed: bool | None = None
    response_time: float = 0.0


@dataclass
class Scenario:
    name: str
    employee: dict
    turns: list[Turn] = field(default_factory=list)
    notes: str = ""
    error: str = ""


# ── HTTP Helpers ───────────────────────────────────────────────────

def _post(url: str, data: dict, token: str = "") -> dict:
    body = json.dumps(data).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else ""
        return {"_error": True, "_status": e.code, "_detail": error_body}
    except Exception as e:
        return {"_error": True, "_status": 0, "_detail": str(e)}


def login(emp: dict) -> tuple[str, str]:
    """Login and return (token, employee_id)."""
    resp = _post(f"{BASE_URL}/chat/auth/login", emp)
    if resp.get("_error"):
        print(f"  LOGIN FAILED for {emp['employee_number']}: {resp.get('_detail')}")
        sys.exit(1)
    return resp["token"], resp["employee_id"]


def reset(token: str, employee_id: str):
    """Reset conversation between scenarios."""
    _post(f"{BASE_URL}/chat/reset/{employee_id}", {}, token)


def send(token: str, message: str, agent: str | None = None) -> dict:
    """Send a chat message and return the full response."""
    payload = {"message": message}
    if agent:
        payload["agent"] = agent
    t0 = time.time()
    resp = _post(f"{BASE_URL}/chat", payload, token)
    elapsed = time.time() - t0
    resp["_elapsed"] = elapsed
    return resp


# ── Test Evaluation Helpers ─────────────────────────────────────────

def contains_any(text: str, keywords: list[str]) -> bool:
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


def check(turn: Turn, response: dict, keywords: list[str], agent_check: str = ""):
    """Evaluate a turn response."""
    turn.response = response.get("response", response.get("_detail", ""))
    turn.response_time = response.get("_elapsed", 0)

    if response.get("_error"):
        turn.actual = f"HTTP error {response.get('_status')}: {response.get('_detail', '')[:200]}"
        turn.passed = False
        return

    matched = contains_any(turn.response, keywords) if keywords else True
    agent_ok = True
    if agent_check:
        agent_ok = response.get("agent", "").lower() == agent_check.lower()
        if not agent_ok:
            turn.actual = f"Agent was '{response.get('agent')}' (expected {agent_check}). Response: {turn.response[:200]}"
            turn.passed = False
            return

    turn.passed = matched
    turn.actual = turn.response[:300] if matched else f"Keywords not found. Response: {turn.response[:300]}"


# ── Scenarios ──────────────────────────────────────────────────────

def scenario_1_onboarding_multiturn(token: str, emp_id: str) -> Scenario:
    """Onboarding Multi-Turn Flow (as Ahmed): search Rayan, overdue steps, complete step."""
    sc = Scenario(name="1. Onboarding Multi-Turn Flow", employee=AHMED)

    # Turn 1: show onboarding for Rayan
    t1 = Turn("show onboarding for Rayan", agent="waleed", expected="Should search for Rayan and show checklist")
    r1 = send(token, t1.input_msg, t1.agent)
    check(t1, r1, ["rayan", "onboarding", "checklist", "step", "contract", "pending", "completed", "progress"])
    sc.turns.append(t1)

    # Turn 2: which steps are overdue?
    t2 = Turn("which steps are overdue?", agent=None, expected="Should show overdue steps from context")
    r2 = send(token, t2.input_msg)
    check(t2, r2, ["overdue", "due", "late", "pending", "behind", "متأخر"])
    sc.turns.append(t2)

    # Turn 3: complete the first pending step
    t3 = Turn("complete the first pending step", agent=None, expected="Should attempt to complete a pending step")
    r3 = send(token, t3.input_msg)
    check(t3, r3, ["complete", "completed", "done", "marked", "step", "اكتمل", "تم", "error", "cannot"])
    sc.turns.append(t3)

    return sc


def scenario_2_manager_approval(token: str, emp_id: str) -> Scenario:
    """Manager Approval Flow (as Ahmed): pending approvals, approve Omar's sick leave, check remaining."""
    sc = Scenario(name="2. Manager Approval Flow", employee=AHMED)

    # Turn 1: show pending approvals
    t1 = Turn("show pending approvals", agent="waleed", expected="Should list pending leave requests")
    r1 = send(token, t1.input_msg, t1.agent)
    check(t1, r1, ["pending", "leave", "request", "omar", "khalid", "turki", "approve", "معلق"])
    sc.turns.append(t1)

    # Turn 2: approve Omar's sick leave
    t2 = Turn("approve Omar's sick leave", agent=None, expected="Should approve Omar's pending request")
    r2 = send(token, t2.input_msg)
    check(t2, r2, ["approv", "omar", "sick", "تم", "موافق"])
    sc.turns.append(t2)

    # Turn 3: any more pending?
    t3 = Turn("any more pending?", agent=None, expected="Should show remaining pending requests (count decreased)")
    r3 = send(token, t3.input_msg)
    check(t3, r3, ["pending", "request", "khalid", "turki", "معلق", "no pending", "لا توجد"])
    sc.turns.append(t3)

    return sc


def scenario_3_agent_handoff(token: str, emp_id: str) -> Scenario:
    """Agent Handoff: Deema -> Waleed."""
    sc = Scenario(name="3. Agent Handoff (Deema -> Waleed)", employee=AHMED)

    # Turn 1: ask Deema about leave policy
    t1 = Turn("what is the annual leave policy?", agent="deema", expected="Deema should answer about leave policy")
    r1 = send(token, t1.input_msg, t1.agent)
    check(t1, r1, ["leave", "annual", "days", "policy", "إجازة", "سنوي"], agent_check="deema")
    sc.turns.append(t1)

    # Reset so we start fresh for handoff test
    reset(token, emp_id)

    # Turn 2: ask about team (Waleed keyword) — should route to Waleed
    t2 = Turn("show my team members", agent="waleed", expected="Waleed should respond with team list")
    r2 = send(token, t2.input_msg, t2.agent)
    check(t2, r2, ["team", "omar", "khalid", "noura", "rayan", "turki", "فريق"], agent_check="waleed")
    sc.turns.append(t2)

    return sc


def scenario_4_bilingual(token: str, emp_id: str) -> Scenario:
    """Bilingual: Arabic -> English -> Arabic."""
    sc = Scenario(name="4. Bilingual Flow", employee=AHMED)

    # Turn 1: Arabic - show my team
    t1 = Turn("عرض فريقي", agent="waleed", expected="Should respond with team info (Arabic)")
    r1 = send(token, t1.input_msg, t1.agent)
    check(t1, r1, ["فريق", "team", "omar", "khalid", "عمر", "خالد", "noura", "نور"], agent_check="waleed")
    sc.turns.append(t1)

    # Turn 2: English - show pending approvals
    t2 = Turn("show pending approvals", agent=None, expected="Should switch to English and show approvals")
    r2 = send(token, t2.input_msg)
    check(t2, r2, ["pending", "leave", "request", "approve", "معلق", "إجازة"])
    sc.turns.append(t2)

    # Turn 3: Arabic - approve Khalid's leave
    t3 = Turn("وافق على إجازة خالد", agent=None, expected="Should process approval in Arabic")
    r3 = send(token, t3.input_msg)
    check(t3, r3, ["خالد", "khalid", "approv", "موافق", "تم", "إجازة"])
    sc.turns.append(t3)

    return sc


def scenario_5_keyword_routing(token: str, emp_id: str) -> Scenario:
    """Keyword Routing: verify messages route to Waleed without explicit agent."""
    sc = Scenario(name="5. Keyword Routing to Waleed", employee=AHMED)

    keywords_to_test = [
        ("my team members", ["team", "فريق", "omar", "khalid"]),
        ("pending approvals", ["pending", "approv", "request", "معلق", "no pending"]),
        ("onboarding checklist", ["onboarding", "checklist", "تهيئة", "step"]),
        ("تهيئة الموظف الجديد", ["تهيئة", "onboarding", "جديد", "new"]),
    ]

    for msg, expected_kw in keywords_to_test:
        reset(token, emp_id)
        t = Turn(msg, agent=None, expected=f"Should route to Waleed and contain: {expected_kw}")
        r = send(token, t.input_msg)
        check(t, r, expected_kw, agent_check="waleed")
        sc.turns.append(t)

    return sc


def scenario_6_sticky_agent(token: str, emp_id: str) -> Scenario:
    """Sticky Agent: start with agent=waleed, then send without agent."""
    sc = Scenario(name="6. Sticky Agent", employee=AHMED)

    # Turn 1: explicitly waleed
    t1 = Turn("hello", agent="waleed", expected="Waleed greets the user")
    r1 = send(token, t1.input_msg, t1.agent)
    check(t1, r1, ["hello", "hi", "مرحبا", "أهلا", "waleed", "help", "assist", "welcome"], agent_check="waleed")
    sc.turns.append(t1)

    # Turn 2: no agent specified, should stay with waleed
    t2 = Turn("show my team", agent=None, expected="Should stay with Waleed (sticky)")
    r2 = send(token, t2.input_msg)
    check(t2, r2, ["team", "omar", "khalid", "فريق"], agent_check="waleed")
    sc.turns.append(t2)

    return sc


def scenario_7_error_recovery(token: str, emp_id: str) -> Scenario:
    """Error Recovery: invalid ID then valid name."""
    sc = Scenario(name="7. Error Recovery", employee=AHMED)

    # Turn 1: invalid employee id
    t1 = Turn("check onboarding for employee abc-invalid-id", agent="waleed",
              expected="Should handle invalid ID gracefully")
    r1 = send(token, t1.input_msg, t1.agent)
    check(t1, r1, ["not found", "invalid", "error", "no employee", "couldn't find", "لم يتم", "غير", "search", "rayan", "lama", "turki"])
    sc.turns.append(t1)

    # Turn 2: recover with valid name
    t2 = Turn("search for Rayan instead", agent=None, expected="Should find Rayan and show info")
    r2 = send(token, t2.input_msg)
    check(t2, r2, ["rayan", "ريان", "EMP-007", "frontend", "onboarding"])
    sc.turns.append(t2)

    return sc


def scenario_8_non_manager(token_khalid: str, emp_id_khalid: str) -> Scenario:
    """Non-Manager Using Manager Tools (as Khalid EMP-005)."""
    sc = Scenario(name="8. Non-Manager Access Denial", employee=KHALID)

    t1 = Turn("show my team", agent="waleed", expected="Should deny — Khalid is not a manager")
    r1 = send(token_khalid, t1.input_msg, t1.agent)
    check(t1, r1, ["not a manager", "no direct reports", "لست مدير", "don't have", "cannot", "لم يتم"])
    sc.turns.append(t1)

    return sc


# ── Report Generation ──────────────────────────────────────────────

def generate_report(scenarios: list[Scenario]) -> str:
    total_turns = sum(len(s.turns) for s in scenarios)
    passed = sum(1 for s in scenarios for t in s.turns if t.passed)
    failed = sum(1 for s in scenarios for t in s.turns if t.passed is False)

    lines = [
        "# Waleed W2 Conversation Test Results",
        "",
        f"**Date:** {time.strftime('%Y-%m-%d %H:%M')}",
        f"**Tester:** Huda (Conversation Tester)",
        f"**Target:** Waleed Agent via live API at {BASE_URL}",
        "",
        f"## Summary: {passed}/{total_turns} turns passed, {failed}/{total_turns} failed",
        "",
    ]

    for sc in scenarios:
        sc_passed = sum(1 for t in sc.turns if t.passed)
        sc_total = len(sc.turns)
        sc_status = "PASS" if sc_passed == sc_total else "FAIL"
        lines.append(f"---")
        lines.append(f"")
        lines.append(f"### {sc.name} [{sc_status}] ({sc_passed}/{sc_total})")
        lines.append(f"")

        if sc.error:
            lines.append(f"**Error:** {sc.error}")
            lines.append("")
            continue

        lines.append("| Turn | Input | Expected | Result | Time |")
        lines.append("|------|-------|----------|--------|------|")
        for i, t in enumerate(sc.turns, 1):
            status = "PASS" if t.passed else "FAIL"
            msg_short = t.input_msg[:50]
            exp_short = t.expected[:60]
            lines.append(f"| {i} | `{msg_short}` | {exp_short} | **{status}** | {t.response_time:.1f}s |")

        lines.append("")
        lines.append("**Full Transcript:**")
        lines.append("")
        for i, t in enumerate(sc.turns, 1):
            status_icon = "[PASS]" if t.passed else "[FAIL]"
            lines.append(f"**Turn {i} {status_icon}** ({t.response_time:.1f}s)")
            lines.append(f"")
            lines.append(f"*User:* `{t.input_msg}`")
            lines.append(f"")
            # Truncate very long responses for readability
            resp_display = t.response[:800] + ("..." if len(t.response) > 800 else "")
            lines.append(f"*Agent:* {resp_display}")
            lines.append(f"")
            if not t.passed:
                lines.append(f"*Failure:* {t.actual[:300]}")
                lines.append(f"")

    # Bugs section
    lines.append("---")
    lines.append("")
    lines.append("## Bugs Found")
    lines.append("")
    lines.append("| # | Severity | Scenario | Turn | Issue |")
    lines.append("|---|----------|----------|------|-------|")
    bug_num = 0
    for sc in scenarios:
        for i, t in enumerate(sc.turns, 1):
            if not t.passed:
                bug_num += 1
                sev = "Critical" if i == 1 else "Major"
                issue = t.actual[:120].replace("|", "/").replace("\n", " ")
                lines.append(f"| {bug_num} | {sev} | {sc.name[:30]} | Turn {i} | {issue} |")

    if bug_num == 0:
        lines.append("| - | - | - | - | No bugs found |")

    # Response time summary
    lines.append("")
    lines.append("## Response Times")
    lines.append("")
    all_times = [t.response_time for s in scenarios for t in s.turns if t.response_time > 0]
    if all_times:
        lines.append(f"- **Average:** {sum(all_times)/len(all_times):.1f}s")
        lines.append(f"- **Min:** {min(all_times):.1f}s")
        lines.append(f"- **Max:** {max(all_times):.1f}s")
        slow = [t for s in scenarios for t in s.turns if t.response_time > 15]
        if slow:
            lines.append(f"- **Slow turns (>15s):** {len(slow)}")

    lines.append("")
    lines.append("## Recommendations")
    lines.append("")

    # Dynamic recommendations based on failures
    recs = []
    for sc in scenarios:
        for t in sc.turns:
            if not t.passed:
                if "keyword" in sc.name.lower() or "routing" in sc.name.lower():
                    recs.append("- Review keyword routing in orchestrator.py — some messages may not match Waleed's keywords")
                elif "sticky" in sc.name.lower():
                    recs.append("- Sticky agent logic may need adjustment — conversation.agent_name not persisted correctly")
                elif "bilingual" in sc.name.lower():
                    recs.append("- Bilingual handling needs improvement — agent may not switch language context properly")
                elif "error" in sc.name.lower() or "recovery" in sc.name.lower():
                    recs.append("- Error recovery flow needs work — agent should gracefully handle invalid inputs")
                elif "non-manager" in sc.name.lower() or "denial" in sc.name.lower():
                    recs.append("- Non-manager denial message should be clearer and more helpful")
                elif "approval" in sc.name.lower():
                    recs.append("- Manager approval flow needs context retention fixes")
                elif "onboarding" in sc.name.lower():
                    recs.append("- Onboarding multi-turn flow has context issues")

    if not recs:
        recs.append("- All scenarios passed. Consider adding edge case tests for longer conversations (30+ turns).")
        recs.append("- Monitor response times under load — some turns may slow down with conversation history growth.")

    for r in sorted(set(recs)):
        lines.append(r)

    lines.append("")
    return "\n".join(lines)


# ── Main ───────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Waleed W2 Conversation Quality Tests")
    print("=" * 60)
    print()

    # Login as Ahmed (manager)
    print("[Auth] Logging in as Ahmed (EMP-001)...")
    ahmed_token, ahmed_id = login(AHMED)
    print(f"  OK: employee_id={ahmed_id}")

    # Login as Khalid (non-manager)
    print("[Auth] Logging in as Khalid (EMP-005)...")
    khalid_token, khalid_id = login(KHALID)
    print(f"  OK: employee_id={khalid_id}")
    print()

    scenarios: list[Scenario] = []

    # Run each scenario with reset between them
    test_funcs = [
        ("Scenario 1: Onboarding Multi-Turn", lambda: scenario_1_onboarding_multiturn(ahmed_token, ahmed_id)),
        ("Scenario 2: Manager Approval", lambda: scenario_2_manager_approval(ahmed_token, ahmed_id)),
        ("Scenario 3: Agent Handoff", lambda: scenario_3_agent_handoff(ahmed_token, ahmed_id)),
        ("Scenario 4: Bilingual", lambda: scenario_4_bilingual(ahmed_token, ahmed_id)),
        ("Scenario 5: Keyword Routing", lambda: scenario_5_keyword_routing(ahmed_token, ahmed_id)),
        ("Scenario 6: Sticky Agent", lambda: scenario_6_sticky_agent(ahmed_token, ahmed_id)),
        ("Scenario 7: Error Recovery", lambda: scenario_7_error_recovery(ahmed_token, ahmed_id)),
        ("Scenario 8: Non-Manager Denial", lambda: scenario_8_non_manager(khalid_token, khalid_id)),
    ]

    for name, func in test_funcs:
        print(f"[Test] {name}...")

        # Reset Ahmed's conversation before each scenario (except Khalid ones)
        if "Non-Manager" not in name:
            reset(ahmed_token, ahmed_id)
        else:
            reset(khalid_token, khalid_id)

        try:
            sc = func()
            scenarios.append(sc)
            passed = sum(1 for t in sc.turns if t.passed)
            total = len(sc.turns)
            status = "PASS" if passed == total else "FAIL"
            print(f"  {status}: {passed}/{total} turns passed")
            for i, t in enumerate(sc.turns, 1):
                icon = "  [OK]" if t.passed else "  [FAIL]"
                print(f"    Turn {i} {icon} ({t.response_time:.1f}s): {t.input_msg[:50]}")
                if not t.passed:
                    print(f"           -> {t.actual[:150]}")
        except Exception as e:
            sc = Scenario(name=name, employee=AHMED, error=str(e))
            scenarios.append(sc)
            print(f"  ERROR: {e}")
        print()

    # Generate report
    report = generate_report(scenarios)
    report_path = "/Users/najwamalghamdi/Desktop/HR-AI-Startup/docs/waleed_w2_conversation_results.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"Report written to: {report_path}")
    print()

    # Final summary
    total = sum(len(s.turns) for s in scenarios)
    passed = sum(1 for s in scenarios for t in s.turns if t.passed)
    print(f"TOTAL: {passed}/{total} turns passed")


if __name__ == "__main__":
    main()
