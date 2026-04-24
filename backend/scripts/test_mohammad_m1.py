"""Mohammad Agent -- M1 Sprint Tests.

Tests all 13 tools and features via the chat API (server must be running at localhost:8000).
Follows the same pattern as test_waleed_w4.py: urllib.request, no 3rd-party HTTP libs.

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


def api_post(path: str, data: dict, token: str | None = None, timeout: int = 90) -> dict:
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
    return api_post("/chat", {"message": message, "language": language}, token=token, timeout=120)


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


# ── Tests ────────────────────────────────────────────────────────────

def test_01_routing_to_mohammad():
    """Send a recruitment-related message. Expect routing to Mohammad agent."""
    flush_rate_limits()
    token, emp_id = login(AHMED_CREDS)
    reset(emp_id, token)
    time.sleep(1)

    resp = chat("وش وضع التوظيف", token)
    if "_http_error" in resp:
        record("01 Routing to Mohammad", False, detail=f"HTTP {resp['_http_error']}: {resp['_detail']}")
        return

    agent = resp.get("agent", "").lower()
    text = resp.get("response", "")

    is_mohammad = agent == "mohammad" or "محمد" in agent
    record(
        "01 Routing to Mohammad",
        is_mohammad,
        agent=agent,
        snippet=text,
        detail=f"Expected agent 'mohammad', got '{agent}'" if not is_mohammad else "",
    )


def test_02_pipeline_summary():
    """Ask for recruitment pipeline summary. Expect data about positions/candidates."""
    flush_rate_limits()
    token, emp_id = login(AHMED_CREDS)
    reset(emp_id, token)
    time.sleep(1)

    resp = chat("عطني ملخص التوظيف", token)
    if "_http_error" in resp:
        record("02 Pipeline Summary", False, detail=f"HTTP {resp['_http_error']}: {resp['_detail']}")
        return

    agent = resp.get("agent", "").lower()
    text = resp.get("response", "")

    # Pipeline summary should mention positions, candidates, stages, or counts
    keywords = [
        "وظيف", "مرشح", "candidate", "position", "open", "مفتوح",
        "pipeline", "توظيف", "شاغر", "مرحلة", "stage",
        "إعلان", "posting", "فحص", "screened",
    ]
    has_data = has_any_keyword(text, keywords)
    # Also check for numbers (counts)
    has_numbers = bool(re.search(r'\d+', text))

    record(
        "02 Pipeline Summary",
        has_data and has_numbers,
        agent=agent,
        snippet=text,
        detail="Response did not contain pipeline data (positions/candidates/counts)." if not (has_data and has_numbers) else "",
    )


def test_03_job_postings_list():
    """Ask to see open job postings. Expect job titles in response."""
    flush_rate_limits()
    token, emp_id = login(AHMED_CREDS)
    reset(emp_id, token)
    time.sleep(1)

    resp = chat("وريني الوظائف الشاغرة", token)
    if "_http_error" in resp:
        record("03 Job Postings List", False, detail=f"HTTP {resp['_http_error']}: {resp['_detail']}")
        return

    agent = resp.get("agent", "").lower()
    text = resp.get("response", "")

    # Should mention seeded job titles or their Arabic equivalents
    job_keywords = [
        "Software Engineer", "مهندس برمجيات", "HR Business Partner",
        "شريك أعمال", "Data Analyst", "محلل بيانات", "Sales",
        "مبيعات", "وظيف", "شاغر", "posting",
    ]
    has_jobs = has_any_keyword(text, job_keywords)

    record(
        "03 Job Postings List",
        has_jobs,
        agent=agent,
        snippet=text,
        detail="Response did not mention any job postings/titles." if not has_jobs else "",
    )


def test_04_job_posting_details():
    """Ask for details of the Software Engineer posting. Expect detailed info."""
    flush_rate_limits()
    token, emp_id = login(AHMED_CREDS)
    reset(emp_id, token)
    time.sleep(1)

    resp = chat("عطني تفاصيل وظيفة مهندس البرمجيات", token)
    if "_http_error" in resp:
        record("04 Job Posting Details", False, detail=f"HTTP {resp['_http_error']}: {resp['_detail']}")
        return

    agent = resp.get("agent", "").lower()
    text = resp.get("response", "")

    # Should include details like salary, requirements, candidate counts, stages
    detail_keywords = [
        "SAR", "ريال", "salary", "راتب", "مرشح", "candidate",
        "متطلبات", "requirement", "Python", "FastAPI",
        "مرحلة", "stage", "فحص", "applied", "screened",
        "Engineering", "هندسة", "تقنية",
    ]
    has_details = has_any_keyword(text, detail_keywords)

    record(
        "04 Job Posting Details",
        has_details,
        agent=agent,
        snippet=text,
        detail="Response did not contain job posting details (salary, requirements, candidates)." if not has_details else "",
    )


def test_05_view_candidates():
    """Ask to see candidates. Expect candidate names from seed data."""
    flush_rate_limits()
    token, emp_id = login(AHMED_CREDS)
    reset(emp_id, token)
    time.sleep(1)

    resp = chat("وريني المرشحين لوظيفة مهندس البرمجيات", token)
    if "_http_error" in resp:
        record("05 View Candidates", False, detail=f"HTTP {resp['_http_error']}: {resp['_detail']}")
        return

    agent = resp.get("agent", "").lower()
    text = resp.get("response", "")

    # Seeded candidate names for Software Engineer posting
    candidate_keywords = [
        "Ahmed", "أحمد", "Sara", "سارة", "Faisal", "فيصل",
        "Nora", "نورة", "Khalid", "خالد", "Maha", "مها",
        "مرشح", "candidate",
    ]
    has_candidates = has_any_keyword(text, candidate_keywords)

    record(
        "05 View Candidates",
        has_candidates,
        agent=agent,
        snippet=text,
        detail="Response did not mention any candidate names from seed data." if not has_candidates else "",
    )


def test_06_create_job_posting():
    """Ask to create a new job posting. Expect confirmation of creation."""
    flush_rate_limits()
    token, emp_id = login(AHMED_CREDS)
    reset(emp_id, token)
    time.sleep(1)

    resp = chat("أنشئ وظيفة محلل بيانات في قسم التقنية", token)
    if "_http_error" in resp:
        record("06 Create Job Posting", False, detail=f"HTTP {resp['_http_error']}: {resp['_detail']}")
        return

    agent = resp.get("agent", "").lower()
    text = resp.get("response", "")

    # Should confirm creation
    creation_keywords = [
        "تم إنشاء", "created", "أنشئ", "تم", "بنجاح",
        "successfully", "draft", "مسودة", "محلل بيانات",
        "Data Analyst", "وظيفة جديدة", "new posting", "إعلان وظيفي",
    ]
    has_creation = has_any_keyword(text, creation_keywords)

    record(
        "06 Create Job Posting",
        has_creation,
        agent=agent,
        snippet=text,
        detail="Response did not confirm job posting creation." if not has_creation else "",
    )


def test_07_generate_job_description():
    """Ask to generate a JD for a frontend developer. Expect AI-generated content."""
    flush_rate_limits()
    token, emp_id = login(AHMED_CREDS)
    reset(emp_id, token)
    time.sleep(1)

    resp = chat("اكتب وصف وظيفي لمطور واجهات أمامية", token)
    if "_http_error" in resp:
        record("07 Generate Job Description", False, detail=f"HTTP {resp['_http_error']}: {resp['_detail']}")
        return

    agent = resp.get("agent", "").lower()
    text = resp.get("response", "")

    # AI-generated JD should include typical JD sections and Saudi context
    jd_keywords = [
        "مسؤوليات", "responsibilities", "متطلبات", "requirements",
        "مؤهلات", "qualifications", "خبرة", "experience",
        "frontend", "واجهات", "React", "JavaScript", "TypeScript",
        "وصف وظيفي", "job description", "راتب", "salary", "SAR",
        "سعودة", "Saudization", "تأمين", "GOSI",
    ]
    has_jd = has_any_keyword(text, jd_keywords)

    record(
        "07 Generate Job Description",
        has_jd,
        agent=agent,
        snippet=text,
        detail="Response did not contain AI-generated job description content." if not has_jd else "",
    )


def test_08_screen_candidate():
    """Ask to screen a candidate. Expect AI screening result with score/recommendation."""
    flush_rate_limits()
    token, emp_id = login(AHMED_CREDS)
    reset(emp_id, token)
    time.sleep(1)

    resp = chat("افحص المرشح أحمد على وظيفة مهندس البرمجيات", token)
    if "_http_error" in resp:
        record("08 Screen Candidate", False, detail=f"HTTP {resp['_http_error']}: {resp['_detail']}")
        return

    agent = resp.get("agent", "").lower()
    text = resp.get("response", "")

    # Screening result should mention score, strengths/gaps, recommendation
    screen_keywords = [
        "score", "درجة", "نقاط", "تقييم", "فحص", "screening",
        "نقاط القوة", "strength", "gap", "فجو", "توصية", "recommendation",
        "مناسب", "fit", "مقابلة", "interview", "proceed",
        "يوصى", "review", "مراجعة", "%", "نسبة",
    ]
    has_screening = has_any_keyword(text, screen_keywords)

    record(
        "08 Screen Candidate",
        has_screening,
        agent=agent,
        snippet=text,
        detail="Response did not contain screening results (score, recommendation)." if not has_screening else "",
    )


def test_09_update_candidate_stage():
    """Ask to move a candidate to shortlist. Expect stage update confirmation."""
    flush_rate_limits()
    token, emp_id = login(AHMED_CREDS)
    reset(emp_id, token)
    time.sleep(1)

    # Use a candidate who is in 'screened' stage and can be shortlisted
    resp = chat("حول سارة للقائمة المختصرة", token)
    if "_http_error" in resp:
        record("09 Update Candidate Stage", False, detail=f"HTTP {resp['_http_error']}: {resp['_detail']}")
        return

    agent = resp.get("agent", "").lower()
    text = resp.get("response", "")

    # Should confirm stage update
    stage_keywords = [
        "تم تحديث", "updated", "المختصرة", "shortlist",
        "مرحلة", "stage", "تم", "بنجاح", "successfully",
        "سارة", "Sara", "تحويل", "نقل", "moved",
    ]
    has_update = has_any_keyword(text, stage_keywords)

    record(
        "09 Update Candidate Stage",
        has_update,
        agent=agent,
        snippet=text,
        detail="Response did not confirm stage update to shortlist." if not has_update else "",
    )


def test_10_schedule_interview():
    """Ask to schedule an interview. Expect scheduling confirmation."""
    flush_rate_limits()
    token, emp_id = login(AHMED_CREDS)
    reset(emp_id, token)
    time.sleep(1)

    resp = chat("جدول مقابلة لنورة يوم الأحد الجاي الساعة 10 صباحا", token)
    if "_http_error" in resp:
        record("10 Schedule Interview", False, detail=f"HTTP {resp['_http_error']}: {resp['_detail']}")
        return

    agent = resp.get("agent", "").lower()
    text = resp.get("response", "")

    # Should confirm scheduling with date/time details
    schedule_keywords = [
        "مقابلة", "interview", "جدول", "schedule",
        "تم", "بنجاح", "successfully", "أحد", "Sunday",
        "10", "نورة", "Nora", "تم جدولة", "scheduled",
        "موعد", "appointment", "تاريخ", "date",
    ]
    has_schedule = has_any_keyword(text, schedule_keywords)

    record(
        "10 Schedule Interview",
        has_schedule,
        agent=agent,
        snippet=text,
        detail="Response did not confirm interview scheduling." if not has_schedule else "",
    )


# ── Runner ───────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("  Mohammad Agent -- M1 Sprint Tests")
    print("=" * 70)
    print()

    tests = [
        ("Test 01: Routing to Mohammad", test_01_routing_to_mohammad),
        ("Test 02: Pipeline Summary", test_02_pipeline_summary),
        ("Test 03: Job Postings List", test_03_job_postings_list),
        ("Test 04: Job Posting Details", test_04_job_posting_details),
        ("Test 05: View Candidates", test_05_view_candidates),
        ("Test 06: Create Job Posting", test_06_create_job_posting),
        ("Test 07: Generate Job Description", test_07_generate_job_description),
        ("Test 08: Screen Candidate", test_08_screen_candidate),
        ("Test 09: Update Candidate Stage", test_09_update_candidate_stage),
        ("Test 10: Schedule Interview", test_10_schedule_interview),
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

    print(f"{'#':<4} {'Result':<8} {'Test':<45} {'Detail'}")
    print("-" * 110)
    for i, (status, name, detail) in enumerate(results, 1):
        det = detail[:70] if detail else ""
        print(f"{i:<4} {status:<8} {name:<45} {det}")

    print()
    if failed > 0 or errors > 0:
        print(f"  ** {failed} failure(s), {errors} error(s) -- see details above **")
        sys.exit(1)
    else:
        print("  All tests passed.")
        sys.exit(0)


if __name__ == "__main__":
    main()
