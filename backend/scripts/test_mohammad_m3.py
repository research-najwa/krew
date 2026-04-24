"""Mohammad Agent -- M3 Sprint Tests (Closing the Loop).

Tests M3 tools: transcript analysis, interview summary, offer recommendation, hire + handoff.
Server must be running at localhost:8000 with seed data loaded.

Prerequisites:
  1. Server running at localhost:8000
  2. Seed data loaded: python -m scripts.seed_recruitment
  3. Redis running (for rate limits)
"""
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BASE = "http://localhost:8000/api/v1"
AHMED_CREDS = {"employee_number": "EMP-001", "national_id_last4": "5432"}

passed = 0
failed = 0
results = []


def flush_rate_limits():
    try:
        import redis
        r = redis.from_url("redis://localhost:6379")
        keys = list(r.scan_iter("rl:*"))
        if keys:
            r.delete(*keys)
    except Exception as exc:
        print(f"  [warn] Could not flush rate limits: {exc}")


def api_post(path: str, data: dict, token: str | None = None, timeout: int = 120) -> dict:
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
    resp = api_post("/chat/auth/login", creds)
    if "_http_error" in resp:
        raise RuntimeError(f"Login failed: {resp}")
    return resp["token"], resp["employee_id"]


def reset(employee_id: str, token: str):
    api_post(f"/chat/reset/{employee_id}", {}, token=token)


def chat(message: str, token: str, language: str = "ar") -> dict:
    return api_post("/chat", {"message": message, "language": language}, token=token, timeout=180)


def record(name: str, ok: bool, snippet: str = "", detail: str = ""):
    global passed, failed
    status = "PASS" if ok else "FAIL"
    if ok:
        passed += 1
    else:
        failed += 1
    results.append((status, name, detail))
    print(f"  [{status}] {name}")
    if snippet:
        print(f"         response: {snippet[:200]}")
    if detail and not ok:
        print(f"         detail: {detail}")


# ── Tests ───────────────────────────────────────────────────────────

def test_01_interview_summary_no_interviews(token: str):
    """M3-02: Get interview summary for a candidate with no interviews."""
    flush_rate_limits()
    print("\n── Test 01: Interview Summary (no interviews) ──")
    resp = chat("Give me the evaluation summary for Faisal Al-Otaibi", token, language="en")
    text = resp.get("response", "")
    agent = resp.get("agent", "")
    record(
        "Interview summary routes to Mohammad",
        agent == "mohammad",
        snippet=text,
        detail=f"agent={agent}",
    )
    record(
        "Summary returned (no error)",
        "error" not in text.lower() or "no interview" in text.lower() or "evaluation" in text.lower() or "summary" in text.lower(),
        snippet=text,
    )


def test_02_analyze_transcript(token: str):
    """M3-01: Analyze a pasted interview transcript."""
    flush_rate_limits()
    print("\n── Test 02: Analyze Interview Transcript ──")
    transcript = """
    Interviewer: Tell me about your experience with Python and backend development.
    Faisal: I have 5 years of experience building REST APIs with FastAPI and Django.
    I've worked extensively with PostgreSQL and Redis for caching.

    Interviewer: How do you handle database migrations in a production environment?
    Faisal: I use Alembic for migrations. I always test migrations on staging first,
    use transaction-safe migrations, and have rollback plans ready.

    Interviewer: Describe a challenging bug you fixed recently.
    Faisal: We had a race condition in our payment service where concurrent requests
    could double-charge customers. I implemented optimistic locking with version columns
    and added idempotency keys to prevent duplicates.

    Interviewer: Why are you interested in this role?
    Faisal: I'm excited about AI-powered HR tech and building systems that help
    Saudi businesses modernize. The combination of AI and HR is a growing field.
    """
    resp = chat(f"Analyze this interview transcript for Faisal Al-Otaibi:\n{transcript}", token, language="en")
    text = resp.get("response", "")
    agent = resp.get("agent", "")
    record(
        "Transcript analysis routes to Mohammad",
        agent == "mohammad",
        snippet=text,
        detail=f"agent={agent}",
    )
    # Check for analysis indicators (bilingual)
    has_score = any(word in text.lower() for word in ["score", "/100", "recommendation", "hire", "strong", "توظيف", "درجة", "توصية", "نقاط"])
    record(
        "Analysis contains score/recommendation",
        has_score,
        snippet=text,
        detail="Looking for score or recommendation keywords (en/ar)",
    )


def test_03_interview_summary_with_data(token: str):
    """M3-02: Get interview summary after transcript analysis (should have data now)."""
    flush_rate_limits()
    print("\n── Test 03: Interview Summary (with data) ──")
    resp = chat("Show me the full evaluation timeline for Faisal Al-Otaibi", token, language="en")
    text = resp.get("response", "")
    has_timeline = any(word in text.lower() for word in ["timeline", "event", "transcript", "analysis", "screening", "application", "سجل", "تقييم", "تحليل", "نقاط", "مقابلة"])
    record(
        "Summary includes evaluation data",
        has_timeline,
        snippet=text,
    )


def test_04_offer_recommendation(token: str):
    """M3-04: Generate offer recommendation (needs candidate at interview stage+)."""
    flush_rate_limits()
    print("\n── Test 04: Offer Recommendation ──")
    resp = chat("Generate an offer recommendation for Faisal Al-Otaibi", token, language="en")
    text = resp.get("response", "")
    agent = resp.get("agent", "")
    record(
        "Offer recommendation routes to Mohammad",
        agent == "mohammad",
        snippet=text,
        detail=f"agent={agent}",
    )
    # Check for Saudi labor law references
    has_labor = any(word in text.lower() for word in ["sar", "probation", "gosi", "article", "salary", "leave"])
    record(
        "Offer includes Saudi labor law context",
        has_labor,
        snippet=text,
    )


def test_05_hire_candidate(token: str):
    """M3-05: Hire the candidate and verify Waleed handoff."""
    flush_rate_limits()
    print("\n── Test 05: Hire Candidate + Waleed Handoff ──")
    resp = chat("وظّف فيصل العتيبي", token, language="ar")
    text = resp.get("response", "")
    agent = resp.get("agent", "")
    record(
        "Hire routes to Mohammad",
        agent == "mohammad",
        snippet=text,
        detail=f"agent={agent}",
    )
    # Mohammad may ask for confirmation first — if so, confirm
    if any(word in text for word in ["تأكيد", "confirm", "قبل ما"]):
        print("         [info] Mohammad asked for confirmation, confirming...")
        flush_rate_limits()
        resp = chat("تأكيد", token, language="ar")
        text = resp.get("response", "")
    has_hire = any(word in text for word in ["وليد", "Waleed", "onboarding", "تهيئة", "EMP-", "مبروك", "hired", "توظيف", "توظّف"])
    record(
        "Hire response mentions Waleed handoff or success",
        has_hire,
        snippet=text,
    )


def test_06_hire_already_hired(token: str):
    """M3-05: Try to hire an already-hired candidate — should fail."""
    flush_rate_limits()
    print("\n── Test 06: Hire Already-Hired Candidate ──")
    resp = chat("Hire Faisal Al-Otaibi again", token, language="en")
    text = resp.get("response", "")
    has_error = any(word in text.lower() for word in ["already", "cannot", "لا يمكن", "بالفعل", "hired", "تم توظيف", "سبق", "مُوظّف"])
    record(
        "Rejects re-hiring an already-hired candidate",
        has_error,
        snippet=text,
    )


def test_07_zoom_stub(token: str):
    """M3-03: Zoom integration stub returns coming-soon message."""
    flush_rate_limits()
    print("\n── Test 07: Zoom Integration Stub ──")
    resp = chat("Schedule a Zoom interview for the next candidate", token, language="en")
    text = resp.get("response", "")
    has_phase2 = any(word in text.lower() for word in ["phase 2", "coming", "المرحلة الثانية", "zoom", "manually"])
    record(
        "Zoom stub returns Phase 2 message",
        has_phase2,
        snippet=text,
    )


# ── Main ────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("MOHAMMAD M3 QA TESTS — Closing the Loop")
    print("=" * 60)

    token, employee_id = login(AHMED_CREDS)
    print(f"Logged in as Ahmed (employee_id={employee_id})")

    reset(employee_id, token)
    print("Conversation reset.")

    # Run tests in order (they build on each other)
    test_01_interview_summary_no_interviews(token)
    test_02_analyze_transcript(token)
    test_03_interview_summary_with_data(token)
    test_04_offer_recommendation(token)
    test_05_hire_candidate(token)
    test_06_hire_already_hired(token)
    test_07_zoom_stub(token)

    # Summary
    print("\n" + "=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed out of {passed + failed} checks")
    print("=" * 60)
    for status, name, detail in results:
        icon = "PASS" if status == "PASS" else "FAIL"
        print(f"  [{icon}] {name}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
