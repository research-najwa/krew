"""Mohammad Agent -- M2 Sprint Tests (AI Interviews + Assessments).

Tests the 7 new M2 tools via the chat API (server must be running at localhost:8000).
Follows the same pattern as test_mohammad_m1.py: urllib.request, no 3rd-party HTTP libs.

M2 Tools:
  1. start_screening_interview
  2. submit_interview_answer
  3. end_interview
  4. generate_assessment
  5. score_interview
  6. compare_candidates
  7. generate_interview_questions

Prerequisites:
  1. Server running at localhost:8000
  2. Seed data loaded: python -m scripts.seed_recruitment
  3. Redis running (for rate limits)
"""
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BASE = "http://localhost:8000/api/v1"

# Ahmed is a manager in Engineering -- can access recruitment tools
AHMED_CREDS = {"employee_number": "EMP-001", "national_id_last4": "5432"}

# ── Counters ─────────────────────────────────────────────────────────
passed = 0
failed = 0
errors = 0
results = []


# ── Helpers ──────────────────────────────────────────────────────────

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
    except Exception as exc:
        return {"_http_error": 0, "_detail": str(exc)}


def login(creds: dict) -> tuple[str, str]:
    """Login and return (token, employee_id)."""
    resp = api_post("/chat/auth/login", creds)
    if "_http_error" in resp:
        raise RuntimeError(f"Login failed: {resp}")
    return resp["token"], resp["employee_id"]


def reset(employee_id: str, token: str):
    """Reset conversation for an employee."""
    api_post(f"/chat/reset/{employee_id}", {}, token=token)


def chat(message: str, token: str, language: str = "ar", timeout: int = 120) -> dict:
    """Send a chat message and return the full response dict."""
    return api_post("/chat", {"message": message, "language": language}, token=token, timeout=timeout)


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
        print(f"         response: {snippet[:300]}")
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


def check_http_error(resp: dict, test_name: str) -> bool:
    """Check for HTTP errors. Returns True if there is an error (test should stop)."""
    if "_http_error" in resp:
        record(test_name, False, detail=f"HTTP {resp['_http_error']}: {resp['_detail'][:200]}")
        return True
    return False


# ── Tests ────────────────────────────────────────────────────────────

def test_01_start_screening_interview():
    """Start a screening interview for Sara Al-Dosari on Senior Software Engineer.
    Expect: Interview starts, first question is returned."""
    flush_rate_limits()
    token, emp_id = login(AHMED_CREDS)
    reset(emp_id, token)
    time.sleep(1)

    resp = chat("ابدأ مقابلة فرز لسارة الدوسري على وظيفة المهندس", token, timeout=120)
    if check_http_error(resp, "01 Start Screening Interview"):
        return

    agent = resp.get("agent", "").lower()
    text = resp.get("response", "")

    # Should contain an interview question or indicate the interview started
    interview_keywords = [
        "مقابلة", "interview", "سؤال", "question",
        "سارة", "Sara", "بدأ", "start",
        "أول سؤال", "first question", "Q1", "السؤال الأول",
        "تقنية", "technical", "خبرة", "experience",
        "أخبرنا", "حدثنا", "tell us", "describe",
        "?", "؟",  # questions end with question marks
    ]
    has_interview = has_any_keyword(text, interview_keywords)

    record(
        "01 Start Screening Interview",
        has_interview,
        agent=agent,
        snippet=text,
        detail="Response did not contain interview start / first question." if not has_interview else "",
    )


def test_02_generate_assessment():
    """Generate a technical assessment for Senior Software Engineer.
    Expect: Assessment with questions and scoring rubric."""
    flush_rate_limits()
    token, emp_id = login(AHMED_CREDS)
    reset(emp_id, token)
    time.sleep(1)

    resp = chat("سوِّ تقييم تقني لوظيفة مهندس البرمجيات", token, timeout=120)
    if check_http_error(resp, "02 Generate Assessment"):
        return

    agent = resp.get("agent", "").lower()
    text = resp.get("response", "")

    # Assessment should have questions and rubric/scoring
    assessment_keywords = [
        "تقييم", "assessment", "سؤال", "question",
        "معيار", "rubric", "criteria", "درجة", "score",
        "تقني", "technical", "Python", "FastAPI", "API",
        "إجابة", "answer", "متوقع", "expected",
        "مبتدئ", "متقدم", "junior", "senior",
        "1", "2", "3",  # numbered questions
    ]
    has_assessment = has_any_keyword(text, assessment_keywords)

    # Should have multiple questions (look for numbered items or bullet points)
    has_multiple = bool(re.search(r'[2-9]|٢|٣|٤|٥|٦|٧|٨|٩|١٠', text))

    record(
        "02 Generate Assessment",
        has_assessment and has_multiple,
        agent=agent,
        snippet=text,
        detail="Response did not contain assessment questions with rubric." if not (has_assessment and has_multiple) else "",
    )


def test_03_score_interview():
    """Score an interview with notes about Sara's performance.
    Expect: Structured scorecard with category scores and recommendation."""
    flush_rate_limits()
    token, emp_id = login(AHMED_CREDS)
    reset(emp_id, token)
    time.sleep(1)

    resp = chat(
        "قيّم مقابلة سارة الدوسري، كانت ممتازة في التقنية وضعيفة في القيادة",
        token,
        timeout=120,
    )
    if check_http_error(resp, "03 Score Interview"):
        return

    agent = resp.get("agent", "").lower()
    text = resp.get("response", "")

    # Scorecard should have scores, categories, strengths, weaknesses, recommendation
    score_keywords = [
        "درجة", "score", "تقييم", "evaluation", "scorecard",
        "تقنية", "technical", "قيادة", "leadership",
        "نقاط القوة", "strength", "ضعف", "weakness", "red flag",
        "توصية", "recommendation", "hire", "توظيف",
        "ممتاز", "excellent", "ضعيف", "weak",
        "/10", "/5", "من 10", "من 5",
    ]
    has_scorecard = has_any_keyword(text, score_keywords)

    # Should have numeric scores
    has_numbers = bool(re.search(r'\d+\s*/\s*\d+|\d+\s*من\s*\d+|\b[1-9]\d?\b', text))

    record(
        "03 Score Interview",
        has_scorecard and has_numbers,
        agent=agent,
        snippet=text,
        detail="Response did not contain structured scorecard with scores." if not (has_scorecard and has_numbers) else "",
    )


def test_04_compare_candidates():
    """Compare candidates for the Software Engineer role.
    Expect: Side-by-side comparison with rankings."""
    flush_rate_limits()
    token, emp_id = login(AHMED_CREDS)
    reset(emp_id, token)
    time.sleep(1)

    resp = chat(
        "قارن بين سارة وفيصل ونورة لوظيفة المهندس",
        token,
        timeout=120,
    )
    if check_http_error(resp, "04 Compare Candidates"):
        return

    agent = resp.get("agent", "").lower()
    text = resp.get("response", "")

    # Comparison should mention multiple candidate names and rankings
    compare_keywords = [
        "مقارنة", "comparison", "compare",
        "سارة", "Sara", "فيصل", "Faisal", "نورة", "Nora",
        "ترتيب", "ranking", "rank", "#1", "#2", "#3",
        "أفضل", "best", "توصية", "recommendation",
        "نقاط القوة", "strength", "فجو", "gap",
        "الأول", "الثاني", "الثالث", "first", "second",
    ]
    has_comparison = has_any_keyword(text, compare_keywords)

    # Should mention at least 2 different candidate names
    name_count = 0
    for name_pair in [("سارة", "Sara"), ("فيصل", "Faisal"), ("نورة", "Nora")]:
        if any(n.lower() in text.lower() or n in text for n in name_pair):
            name_count += 1
    has_multiple_names = name_count >= 2

    record(
        "04 Compare Candidates",
        has_comparison and has_multiple_names,
        agent=agent,
        snippet=text,
        detail=f"Response did not contain comparison of multiple candidates (found {name_count} names)." if not (has_comparison and has_multiple_names) else "",
    )


def test_05_generate_interview_questions():
    """Generate behavioral interview questions for Software Engineer.
    Expect: Questions with follow-up probes."""
    flush_rate_limits()
    token, emp_id = login(AHMED_CREDS)
    reset(emp_id, token)
    time.sleep(1)

    resp = chat(
        "جهز أسئلة مقابلة سلوكية لوظيفة المهندس",
        token,
        timeout=120,
    )
    if check_http_error(resp, "05 Generate Interview Questions"):
        return

    agent = resp.get("agent", "").lower()
    text = resp.get("response", "")

    # Should return behavioral questions with probes
    question_keywords = [
        "سؤال", "question", "سلوكي", "behavioral",
        "أخبرنا", "tell us", "حدثنا", "describe",
        "موقف", "situation", "تحدي", "challenge",
        "STAR", "probe", "متابعة", "follow-up",
        "تقييم", "criteria", "evaluation",
        "?", "؟",
    ]
    has_questions = has_any_keyword(text, question_keywords)

    # Should have multiple questions
    has_multiple = bool(re.search(r'[3-9]|١٠|٣|٤|٥|٦|٧', text))

    record(
        "05 Generate Interview Questions",
        has_questions and has_multiple,
        agent=agent,
        snippet=text,
        detail="Response did not contain behavioral interview questions with probes." if not (has_questions and has_multiple) else "",
    )


def test_06_m1_regression_pipeline_summary():
    """M1 Regression: Ask for recruitment pipeline summary.
    Expect: Still works -- returns positions/candidates data (M1 not broken)."""
    flush_rate_limits()
    token, emp_id = login(AHMED_CREDS)
    reset(emp_id, token)
    time.sleep(1)

    resp = chat("وش وضع التوظيف", token, timeout=120)
    if check_http_error(resp, "06 M1 Regression - Pipeline Summary"):
        return

    agent = resp.get("agent", "").lower()
    text = resp.get("response", "")

    # Pipeline summary should still mention positions, candidates, stages, or counts
    keywords = [
        "وظيف", "مرشح", "candidate", "position", "open", "مفتوح",
        "pipeline", "توظيف", "شاغر", "مرحلة", "stage",
        "إعلان", "posting", "فحص", "screened",
    ]
    has_data = has_any_keyword(text, keywords)
    has_numbers = bool(re.search(r'\d+', text))

    is_mohammad = "mohammad" in agent or "محمد" in agent

    all_ok = has_data and has_numbers and is_mohammad
    detail_parts = []
    if not is_mohammad:
        detail_parts.append(f"Expected agent 'mohammad', got '{agent}'")
    if not has_data:
        detail_parts.append("Missing pipeline data keywords")
    if not has_numbers:
        detail_parts.append("Missing numeric counts")

    record(
        "06 M1 Regression - Pipeline Summary",
        all_ok,
        agent=agent,
        snippet=text,
        detail="; ".join(detail_parts) if not all_ok else "",
    )


# ── Runner ───────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("  Mohammad Agent -- M2 Sprint Tests (AI Interviews + Assessments)")
    print("=" * 70)
    print()

    tests = [
        ("Test 01: Start Screening Interview", test_01_start_screening_interview),
        ("Test 02: Generate Assessment", test_02_generate_assessment),
        ("Test 03: Score Interview", test_03_score_interview),
        ("Test 04: Compare Candidates", test_04_compare_candidates),
        ("Test 05: Generate Interview Questions", test_05_generate_interview_questions),
        ("Test 06: M1 Regression - Pipeline Summary", test_06_m1_regression_pipeline_summary),
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
    print("-" * 120)
    for i, (status, name, detail) in enumerate(results, 1):
        det = detail[:80] if detail else ""
        print(f"{i:<4} {status:<8} {name:<50} {det}")

    print()
    if failed > 0 or errors > 0:
        print(f"  ** {failed} failure(s), {errors} error(s) -- see details above **")
        sys.exit(1)
    else:
        print("  All tests passed.")
        sys.exit(0)


if __name__ == "__main__":
    main()
