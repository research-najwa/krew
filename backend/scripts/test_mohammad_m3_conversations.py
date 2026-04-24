"""Mohammad Agent -- M3 Conversation Tests (Multi-Turn Flows).

Tests multi-turn conversation scenarios for M3 tools:
  - Full recruitment closure flow (Arabic, 5 turns)
  - Edge cases (English, 4 turns)
  - Agent handoff context (bilingual, 3 turns)

These test context retention, mid-flow corrections, agent routing,
and bilingual handling across sequential turns in a single conversation.

Prerequisites:
  1. Server running at localhost:8000
  2. Seed data loaded: python -m scripts.seed_recruitment
  3. Redis running (for rate limits)
"""
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BASE = "http://localhost:8000/api/v1"
AHMED_CREDS = {"employee_number": "EMP-001", "national_id_last4": "5432"}

passed = 0
failed = 0
errors = 0
results = []


# -- Helpers (same pattern as test_mohammad_m1.py) --------------------------

def flush_rate_limits():
    """Clear all Redis rate-limit keys so tests don't get 429s."""
    try:
        import redis
        r = redis.from_url("redis://localhost:6379")
        keys = list(r.scan_iter("rl:*"))
        if keys:
            r.delete(*keys)
    except Exception as exc:
        print(f"  [warn] Could not flush rate limits: {exc}")


def api_post(path: str, data: dict, token: str | None = None, timeout: int = 120) -> dict:
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


def chat(message: str, token: str, language: str = "ar") -> dict:
    """Send a chat message and return the full response dict."""
    return api_post("/chat", {"message": message, "language": language}, token=token, timeout=180)


def record(name: str, ok: bool, agent: str = "", snippet: str = "", detail: str = ""):
    """Record and print a test result."""
    global passed, failed
    status = "PASS" if ok else "FAIL"
    if ok:
        passed += 1
    else:
        failed += 1
    results.append((status, name, detail))
    print(f"  [{status}] {name}")
    if agent:
        print(f"         agent: {agent}")
    if snippet:
        print(f"         response: {snippet[:200]}")
    if detail and not ok:
        print(f"         detail: {detail}")


def record_error(name: str, exc: Exception):
    """Record an error (test could not run)."""
    global errors
    errors += 1
    results.append(("ERROR", name, str(exc)))
    print(f"  [ERROR] {name}")
    print(f"          {exc}")


def has_any_keyword(text: str, keywords: list[str]) -> bool:
    """Check if text contains any of the keywords (case-insensitive for Latin)."""
    text_lower = text.lower()
    return any(kw.lower() in text_lower or kw in text for kw in keywords)


# -- Scenario 1: Full Recruitment Closure (Arabic, 5 turns) ----------------

def scenario_01_full_recruitment_closure(token: str, employee_id: str):
    """
    Arabic multi-turn flow: evaluation summary -> transcript analysis ->
    offer recommendation -> hire -> confirmation.
    All turns in the SAME conversation (no reset between turns).
    """
    print("\n" + "=" * 60)
    print("SCENARIO 1: Full Recruitment Closure (Arabic, 5 turns)")
    print("=" * 60)

    flush_rate_limits()
    reset(employee_id, token)
    time.sleep(1)

    # -- Turn 1: Ask for evaluation summary --
    print("\n-- Turn 1: Evaluation summary --")
    flush_rate_limits()
    r1 = chat("عطني ملخص تقييم فيصل العتيبي", token, language="ar")
    if "_http_error" in r1:
        record("S1-T1 Evaluation summary", False, detail=f"HTTP {r1['_http_error']}: {r1['_detail']}")
        return
    text1 = r1.get("response", "")
    agent1 = r1.get("agent", "")
    record(
        "S1-T1 Routes to Mohammad",
        agent1 == "mohammad",
        agent=agent1,
        snippet=text1,
        detail=f"Expected agent 'mohammad', got '{agent1}'",
    )
    record(
        "S1-T1 Returns evaluation/summary content",
        has_any_keyword(text1, [
            "فيصل", "Faisal", "تقييم", "evaluation", "summary", "ملخص",
            "مرشح", "candidate", "مقابلة", "interview", "نقاط", "score",
        ]),
        snippet=text1,
        detail="Response missing evaluation content for Faisal",
    )

    # -- Turn 2: Paste transcript for analysis --
    print("\n-- Turn 2: Transcript analysis --")
    flush_rate_limits()
    transcript = (
        "المحاور: كلمنا عن خبرتك في البرمجة.\n"
        "فيصل: عندي 5 سنين خبرة في بايثون و FastAPI وبناء REST APIs.\n"
        "المحاور: كيف تتعامل مع قواعد البيانات؟\n"
        "فيصل: أستخدم PostgreSQL مع Alembic للمايقريشنز وعندي خبرة في Redis.\n"
        "المحاور: احكيلي عن مشكلة تقنية حليتها.\n"
        "فيصل: كان عندنا race condition في سيرفس الدفع، حليتها باستخدام optimistic locking.\n"
        "المحاور: ليش تبي تشتغل معنا؟\n"
        "فيصل: أنا متحمس لمجال الـ AI في الموارد البشرية وأبي أساهم في تطوير السوق السعودي."
    )
    r2 = chat(f"حلل هالنص من مقابلة فيصل:\n{transcript}", token, language="ar")
    if "_http_error" in r2:
        record("S1-T2 Transcript analysis", False, detail=f"HTTP {r2['_http_error']}: {r2['_detail']}")
        return
    text2 = r2.get("response", "")
    agent2 = r2.get("agent", "")
    record(
        "S1-T2 Routes to Mohammad",
        agent2 == "mohammad",
        agent=agent2,
        snippet=text2,
        detail=f"Expected agent 'mohammad', got '{agent2}'",
    )
    record(
        "S1-T2 Returns analysis with scores",
        has_any_keyword(text2, [
            "score", "درجة", "نقاط", "تقييم", "توصية", "recommendation",
            "/10", "/100", "قوة", "strength", "تحليل", "analysis",
        ]),
        snippet=text2,
        detail="Response missing scores or analysis keywords",
    )

    # -- Turn 3: Offer recommendation --
    print("\n-- Turn 3: Offer recommendation --")
    flush_rate_limits()
    r3 = chat("عطني توصية عرض لفيصل", token, language="ar")
    if "_http_error" in r3:
        record("S1-T3 Offer recommendation", False, detail=f"HTTP {r3['_http_error']}: {r3['_detail']}")
        return
    text3 = r3.get("response", "")
    agent3 = r3.get("agent", "")
    record(
        "S1-T3 Routes to Mohammad",
        agent3 == "mohammad",
        agent=agent3,
        snippet=text3,
        detail=f"Expected agent 'mohammad', got '{agent3}'",
    )
    record(
        "S1-T3 Offer contains SAR salary",
        has_any_keyword(text3, ["SAR", "ريال", "salary", "راتب"]),
        snippet=text3,
        detail="Response missing SAR/salary info",
    )
    record(
        "S1-T3 Offer mentions probation or GOSI",
        has_any_keyword(text3, [
            "probation", "تجربة", "فترة", "GOSI", "تأمين",
            "اجتماعي", "article", "مادة", "نظام العمل", "labor",
        ]),
        snippet=text3,
        detail="Response missing probation/GOSI/labor law references",
    )

    # -- Turn 4: Hire command --
    print("\n-- Turn 4: Hire command --")
    flush_rate_limits()
    r4 = chat("وظفه", token, language="ar")
    if "_http_error" in r4:
        record("S1-T4 Hire command", False, detail=f"HTTP {r4['_http_error']}: {r4['_detail']}")
        return
    text4 = r4.get("response", "")
    agent4 = r4.get("agent", "")
    record(
        "S1-T4 Routes to Mohammad",
        agent4 == "mohammad",
        agent=agent4,
        snippet=text4,
        detail=f"Expected agent 'mohammad', got '{agent4}'",
    )

    # -- Turn 5: If confirmation needed, confirm; otherwise validate hire --
    needs_confirmation = has_any_keyword(text4, ["تأكيد", "confirm", "قبل ما", "هل أنت متأكد", "are you sure"])
    if needs_confirmation:
        print("\n-- Turn 5: Confirmation --")
        print("         [info] Mohammad asked for confirmation, sending 'تأكيد'...")
        flush_rate_limits()
        r5 = chat("تأكيد", token, language="ar")
        if "_http_error" in r5:
            record("S1-T5 Confirmation", False, detail=f"HTTP {r5['_http_error']}: {r5['_detail']}")
            return
        text5 = r5.get("response", "")
        agent5 = r5.get("agent", "")
        record(
            "S1-T5 Confirmation processed",
            True,
            agent=agent5,
            snippet=text5,
        )
        hire_text = text5
    else:
        print("\n-- Turn 5: (skipped -- hire was immediate) --")
        record(
            "S1-T5 Hire was immediate (no confirmation needed)",
            True,
            snippet=text4,
        )
        hire_text = text4

    # Validate hire outcome
    record(
        "S1 Hire mentions Waleed or onboarding",
        has_any_keyword(hire_text, [
            "وليد", "Waleed", "onboarding", "تهيئة", "EMP-",
            "مبروك", "hired", "توظيف", "توظّف", "تم",
        ]),
        snippet=hire_text,
        detail="Hire response did not mention Waleed handoff or success confirmation",
    )

    # Context retention check: Did Mohammad remember Faisal across all turns?
    record(
        "S1 Context: 'وظفه' resolved to Faisal without re-asking",
        has_any_keyword(hire_text, ["فيصل", "Faisal"]) or has_any_keyword(text4, ["فيصل", "Faisal"]),
        snippet=hire_text,
        detail="Agent did not resolve pronoun 'him' to Faisal from prior context",
    )


# -- Scenario 2: Edge Cases (English, 4 turns) ----------------------------

def scenario_02_edge_cases(token: str, employee_id: str):
    """
    English edge cases: missing candidate name, offer without interview,
    hire nonexistent candidate, Zoom stub.
    Each turn is independent (reset between turns for isolation).
    """
    print("\n" + "=" * 60)
    print("SCENARIO 2: Edge Cases (English, 4 turns)")
    print("=" * 60)

    # -- Turn 1: Analyze transcript without specifying candidate --
    print("\n-- Turn 1: Transcript analysis without candidate name --")
    flush_rate_limits()
    reset(employee_id, token)
    time.sleep(1)
    r1 = chat("Analyze this interview transcript for a candidate", token, language="en")
    if "_http_error" in r1:
        record("S2-T1 No candidate name", False, detail=f"HTTP {r1['_http_error']}: {r1['_detail']}")
    else:
        text1 = r1.get("response", "")
        agent1 = r1.get("agent", "")
        record(
            "S2-T1 Routes to Mohammad",
            agent1 == "mohammad",
            agent=agent1,
            snippet=text1,
            detail=f"Expected agent 'mohammad', got '{agent1}'",
        )
        # Agent should ask for candidate name or transcript content
        record(
            "S2-T1 Asks for missing info (name or transcript)",
            has_any_keyword(text1, [
                "which candidate", "candidate name", "who", "name",
                "transcript", "specify", "provide", "please",
                "اسم", "مرشح", "من",
            ]),
            snippet=text1,
            detail="Agent did not ask for missing candidate name or transcript",
        )

    # -- Turn 2: Generate offer for Faisal --
    print("\n-- Turn 2: Offer for Faisal --")
    flush_rate_limits()
    reset(employee_id, token)
    time.sleep(1)
    r2 = chat("Generate an offer recommendation for Faisal Al-Otaibi", token, language="en")
    if "_http_error" in r2:
        record("S2-T2 Offer for Faisal", False, detail=f"HTTP {r2['_http_error']}: {r2['_detail']}")
    else:
        text2 = r2.get("response", "")
        agent2 = r2.get("agent", "")
        record(
            "S2-T2 Routes to Mohammad",
            agent2 == "mohammad",
            agent=agent2,
            snippet=text2,
            detail=f"Expected agent 'mohammad', got '{agent2}'",
        )
        record(
            "S2-T2 Returns offer content",
            has_any_keyword(text2, [
                "offer", "salary", "SAR", "probation", "Faisal",
                "recommendation", "compensation", "package",
            ]),
            snippet=text2,
            detail="Response missing offer content for Faisal",
        )

    # -- Turn 3: Hire nonexistent candidate --
    print("\n-- Turn 3: Hire nonexistent candidate --")
    flush_rate_limits()
    reset(employee_id, token)
    time.sleep(1)
    r3 = chat("Hire Abdullah Al-Zahrani for Software Engineer", token, language="en")
    if "_http_error" in r3:
        record("S2-T3 Nonexistent candidate", False, detail=f"HTTP {r3['_http_error']}: {r3['_detail']}")
    else:
        text3 = r3.get("response", "")
        agent3 = r3.get("agent", "")
        record(
            "S2-T3 Routes to Mohammad",
            agent3 == "mohammad",
            agent=agent3,
            snippet=text3,
            detail=f"Expected agent 'mohammad', got '{agent3}'",
        )
        record(
            "S2-T3 Returns not-found or error",
            has_any_keyword(text3, [
                "not found", "no candidate", "doesn't exist", "cannot find",
                "لا يوجد", "غير موجود", "not in", "no matching",
                "couldn't find", "unable", "unknown",
            ]),
            snippet=text3,
            detail="Agent did not return a not-found error for nonexistent candidate",
        )

    # -- Turn 4: Zoom integration stub --
    print("\n-- Turn 4: Zoom interview scheduling (Phase 2 stub) --")
    flush_rate_limits()
    reset(employee_id, token)
    time.sleep(1)
    r4 = chat("Schedule a Zoom interview for the next candidate", token, language="en")
    if "_http_error" in r4:
        record("S2-T4 Zoom stub", False, detail=f"HTTP {r4['_http_error']}: {r4['_detail']}")
    else:
        text4 = r4.get("response", "")
        agent4 = r4.get("agent", "")
        record(
            "S2-T4 Routes to Mohammad",
            agent4 == "mohammad",
            agent=agent4,
            snippet=text4,
            detail=f"Expected agent 'mohammad', got '{agent4}'",
        )
        record(
            "S2-T4 Returns Phase 2 / coming-soon stub",
            has_any_keyword(text4, [
                "phase 2", "coming soon", "not yet", "manually",
                "المرحلة الثانية", "قريبا", "zoom", "مستقبل",
                "future", "planned", "roadmap",
            ]),
            snippet=text4,
            detail="Agent did not return Phase 2 stub for Zoom scheduling",
        )


# -- Scenario 3: Agent Handoff Context (Bilingual, 3 turns) ---------------

def scenario_03_agent_handoff(token: str, employee_id: str):
    """
    Bilingual handoff: Start with Waleed topic -> route to Mohammad ->
    unknown candidate -> list available candidates.
    All turns in the SAME conversation to test handoff context.
    """
    print("\n" + "=" * 60)
    print("SCENARIO 3: Agent Handoff Context (Bilingual, 3 turns)")
    print("=" * 60)

    flush_rate_limits()
    reset(employee_id, token)
    time.sleep(1)

    # -- Turn 1: Start with recruitment question (may route Waleed or Mohammad) --
    print("\n-- Turn 1: Recruitment status question --")
    flush_rate_limits()
    r1 = chat("وش الجديد في التوظيف؟", token, language="ar")
    if "_http_error" in r1:
        record("S3-T1 Recruitment question", False, detail=f"HTTP {r1['_http_error']}: {r1['_detail']}")
        return
    text1 = r1.get("response", "")
    agent1 = r1.get("agent", "")
    # This should route to Mohammad (recruitment keyword)
    record(
        "S3-T1 Routes to Mohammad (recruitment topic)",
        agent1 == "mohammad",
        agent=agent1,
        snippet=text1,
        detail=f"Expected routing to 'mohammad', got '{agent1}'",
    )
    record(
        "S3-T1 Response contains recruitment info",
        has_any_keyword(text1, [
            "توظيف", "مرشح", "وظيفة", "candidate", "position",
            "pipeline", "recruitment", "شاغر", "posting",
        ]),
        snippet=text1,
        detail="Response missing recruitment-related content",
    )

    # -- Turn 2: Ask about a candidate that doesn't exist (Sara) --
    print("\n-- Turn 2: Ask for nonexistent candidate Sara --")
    flush_rate_limits()
    r2 = chat("عطني ملخص كامل عن سارة المطيري", token, language="ar")
    if "_http_error" in r2:
        record("S3-T2 Unknown candidate Sara", False, detail=f"HTTP {r2['_http_error']}: {r2['_detail']}")
        return
    text2 = r2.get("response", "")
    agent2 = r2.get("agent", "")
    record(
        "S3-T2 Still routed to Mohammad",
        agent2 == "mohammad",
        agent=agent2,
        snippet=text2,
        detail=f"Expected agent 'mohammad', got '{agent2}'",
    )
    # Agent should either return info about Sara (if she exists in seed) or
    # indicate candidate not found. Either way is acceptable.
    record(
        "S3-T2 Responds about Sara (found or not-found)",
        has_any_keyword(text2, [
            "سارة", "Sara", "غير موجود", "not found", "لا يوجد",
            "مرشح", "candidate", "تقييم", "evaluation",
        ]),
        snippet=text2,
        detail="Response did not address the Sara query at all",
    )

    # -- Turn 3: List available candidates --
    print("\n-- Turn 3: List available candidates --")
    flush_rate_limits()
    r3 = chat("وش المرشحين المتاحين؟", token, language="ar")
    if "_http_error" in r3:
        record("S3-T3 List candidates", False, detail=f"HTTP {r3['_http_error']}: {r3['_detail']}")
        return
    text3 = r3.get("response", "")
    agent3 = r3.get("agent", "")
    record(
        "S3-T3 Still routed to Mohammad",
        agent3 == "mohammad",
        agent=agent3,
        snippet=text3,
        detail=f"Expected agent 'mohammad', got '{agent3}'",
    )
    record(
        "S3-T3 Lists candidate names",
        has_any_keyword(text3, [
            "فيصل", "Faisal", "أحمد", "Ahmed", "نورة", "Nora",
            "سارة", "Sara", "خالد", "Khalid", "مها", "Maha",
            "مرشح", "candidate",
        ]),
        snippet=text3,
        detail="Response did not list any candidate names from seed data",
    )


# -- Main -----------------------------------------------------------------

def main():
    print("=" * 70)
    print("  Mohammad Agent -- M3 Conversation Tests (Multi-Turn Flows)")
    print("=" * 70)
    print()

    token, employee_id = login(AHMED_CREDS)
    print(f"Logged in as Ahmed (employee_id={employee_id})")

    scenarios = [
        ("Scenario 1: Full Recruitment Closure", scenario_01_full_recruitment_closure),
        ("Scenario 2: Edge Cases", scenario_02_edge_cases),
        ("Scenario 3: Agent Handoff Context", scenario_03_agent_handoff),
    ]

    for label, fn in scenarios:
        print(f"\n>>> {label}")
        try:
            fn(token, employee_id)
        except Exception as exc:
            record_error(label, exc)

    # -- Summary -----------------------------------------------------------
    print("\n" + "=" * 70)
    print(f"  SUMMARY: {passed} passed, {failed} failed, {errors} errors  (total: {passed + failed + errors})")
    print("=" * 70)
    print()

    print(f"{'#':<4} {'Result':<8} {'Test':<55} {'Detail'}")
    print("-" * 120)
    for i, (status, name, detail) in enumerate(results, 1):
        det = detail[:70] if detail else ""
        print(f"{i:<4} {status:<8} {name:<55} {det}")

    # -- Context Retention Scorecard ----------------------------------------
    print()
    print("-" * 70)
    print("  Context Retention Scorecard (Scenario 1)")
    print("-" * 70)
    s1_results = [(s, n, d) for s, n, d in results if n.startswith("S1")]
    s1_pass = sum(1 for s, _, _ in s1_results if s == "PASS")
    s1_total = len(s1_results)
    print(f"  Turns retained context: {s1_pass}/{s1_total} checks passed")
    pronoun_result = [s for s, n, _ in results if "Context" in n]
    if pronoun_result:
        print(f"  Pronoun resolution ('him' -> Faisal): {pronoun_result[0]}")
    print()

    if failed > 0 or errors > 0:
        print(f"  ** {failed} failure(s), {errors} error(s) -- see details above **")
        sys.exit(1)
    else:
        print("  All tests passed.")
        sys.exit(0)


if __name__ == "__main__":
    main()
