"""Regression test suite for Deema agent — end-to-end via the chat API."""
import asyncio
import json
import time
import sys
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime

import httpx

BASE_URL = "http://localhost:8000"
API = f"{BASE_URL}/api/v1/chat"

# Employee IDs from seed data
AHMED = "2d0c6b8e-eadf-4c58-aacb-3b8c9bbc62ad"     # Arabic, VP Eng, 5 annual used
OMAR = "9fe87ed2-869b-4f80-8750-9c898604bffb"        # English, Senior Dev, 0 used
SARA = "c12d12fb-c0d3-427c-bd5d-b462d6a8103f"        # Arabic, Sales, 2 sick used
KHALID = "038d334e-61bd-4a1e-a943-38576806cd9e"      # Arabic, Backend Dev


@dataclass
class TestResult:
    name: str
    category: str
    passed: bool
    duration_ms: int
    details: str = ""
    response: str = ""
    error: str = ""


@dataclass
class TestReport:
    results: list[TestResult] = field(default_factory=list)
    start_time: float = 0.0
    end_time: float = 0.0

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed(self) -> int:
        return self.total - self.passed

    @property
    def duration_s(self) -> float:
        return self.end_time - self.start_time


report = TestReport()


async def chat(employee_id: str, message: str, timeout: float = 45.0) -> dict:
    """Send a chat message and return the response."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        res = await client.post(API, json={
            "employee_id": employee_id,
            "message": message,
        })
        res.raise_for_status()
        return res.json()


async def reset(employee_id: str):
    """Reset conversation for clean test state."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        await client.post(f"{API}/reset/{employee_id}")


async def run_test(name: str, category: str, coro, checks: list):
    """Run a single test with timing and validation."""
    start = time.time()
    try:
        result = await coro
        duration = int((time.time() - start) * 1000)

        response_text = result.get("response", "") if isinstance(result, dict) else str(result)
        agent = result.get("agent", "?") if isinstance(result, dict) else "?"

        all_passed = True
        details = []
        for check_name, check_fn in checks:
            try:
                ok = check_fn(result)
                status = "PASS" if ok else "FAIL"
                if not ok:
                    all_passed = False
                details.append(f"  [{status}] {check_name}")
            except Exception as e:
                all_passed = False
                details.append(f"  [FAIL] {check_name} — Exception: {e}")

        report.results.append(TestResult(
            name=name,
            category=category,
            passed=all_passed,
            duration_ms=duration,
            details="\n".join(details),
            response=response_text[:200],
        ))

    except Exception as e:
        duration = int((time.time() - start) * 1000)
        report.results.append(TestResult(
            name=name,
            category=category,
            passed=False,
            duration_ms=duration,
            error=str(e),
        ))


# ──────────────────────────────────────────
# TEST CASES
# ──────────────────────────────────────────

async def test_health():
    """T0: API health check."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        res = await client.get(f"{BASE_URL}/health")
        return res.json()


async def test_employees_list():
    """T1: Employee list endpoint."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        res = await client.get(f"{API}/employees")
        return res.json()


async def test_leave_balance_english():
    """T2: Leave balance — English (Omar)."""
    await reset(OMAR)
    return await chat(OMAR, "How many leave days do I have?")


async def test_leave_balance_arabic():
    """T3: Leave balance — Arabic (Ahmed)."""
    await reset(AHMED)
    return await chat(AHMED, "كم رصيد إجازاتي؟")


async def test_leave_balance_accuracy_ahmed():
    """T4: Leave balance accuracy — Ahmed should have 16 annual remaining."""
    await reset(AHMED)
    return await chat(AHMED, "What is my annual leave balance? Reply in English please.")


async def test_leave_balance_accuracy_sara():
    """T5: Leave balance accuracy — Sara should have 28 sick remaining."""
    await reset(SARA)
    return await chat(SARA, "كم يوم مرضي باقي عندي؟")


async def test_employee_info():
    """T6: Employee info lookup."""
    await reset(OMAR)
    return await chat(OMAR, "Can you show me my employee information?")


async def test_leave_request():
    """T7: Leave request submission."""
    await reset(KHALID)
    return await chat(KHALID, "أبغى أقدم إجازة سنوية من 2026-04-06 إلى 2026-04-10")


async def test_routing_to_deema():
    """T8: Orchestrator routes leave query to Deema."""
    await reset(OMAR)
    return await chat(OMAR, "I want to check my vacation balance")


async def test_greeting():
    """T9: General greeting — Deema should respond warmly."""
    await reset(OMAR)
    return await chat(OMAR, "Hello!")


async def test_invalid_employee():
    """T10: Invalid employee ID should return 404."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        res = await client.post(API, json={
            "employee_id": "00000000-0000-0000-0000-000000000000",
            "message": "hello",
        })
        return {"status_code": res.status_code, "detail": res.json().get("detail", "")}


async def test_empty_message():
    """T11: Empty message should return 400."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        res = await client.post(API, json={
            "employee_id": OMAR,
            "message": "   ",
        })
        return {"status_code": res.status_code, "detail": res.json().get("detail", "")}


async def test_conversation_memory():
    """T12: Conversation memory — follow-up question."""
    await reset(OMAR)
    await chat(OMAR, "How many annual leave days do I have?")
    return await chat(OMAR, "And what about sick leave?")


async def test_bilingual_response():
    """T13: Arabic employee gets Arabic response."""
    await reset(AHMED)
    return await chat(AHMED, "مرحبا")


async def test_english_response():
    """T14: English employee gets English response."""
    await reset(OMAR)
    return await chat(OMAR, "Hi there")


# ──────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────

async def main():
    report.start_time = time.time()

    print("=" * 60)
    print("  KREW — Deema Agent Regression Tests")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print()

    # ── Infrastructure ──
    print("[Infrastructure]")

    await run_test("API Health Check", "Infrastructure",
        test_health(),
        [("Returns healthy", lambda r: r.get("status") == "healthy")])

    await run_test("Employee List", "Infrastructure",
        test_employees_list(),
        [
            ("Returns list", lambda r: isinstance(r, list)),
            ("Has 6 employees", lambda r: len(r) == 6),
            ("Contains Ahmed", lambda r: any(e["name"] == "Ahmed Al-Rashidi" for e in r)),
        ])

    # ── Leave Balance ──
    print("[Leave Balance]")

    await run_test("Leave Balance — English (Omar)", "Leave Balance",
        test_leave_balance_english(),
        [
            ("Routes to Deema", lambda r: r["agent"] == "deema"),
            ("Contains leave info", lambda r: any(w in r["response"].lower() for w in ["annual", "sick", "leave", "21", "30"])),
            ("Has response", lambda r: len(r["response"]) > 20),
        ])

    await run_test("Leave Balance — Arabic (Ahmed)", "Leave Balance",
        test_leave_balance_arabic(),
        [
            ("Routes to Deema", lambda r: r["agent"] == "deema"),
            ("Contains Arabic", lambda r: any(c >= '\u0600' and c <= '\u06FF' for c in r["response"])),
            ("Has response", lambda r: len(r["response"]) > 20),
        ])

    await run_test("Balance Accuracy — Ahmed (16 annual)", "Leave Balance",
        test_leave_balance_accuracy_ahmed(),
        [
            ("Routes to Deema", lambda r: r["agent"] == "deema"),
            ("Shows 16 remaining", lambda r: "16" in r["response"]),
            ("Shows 5 used", lambda r: "5" in r["response"]),
        ])

    await run_test("Balance Accuracy — Sara (28 sick)", "Leave Balance",
        test_leave_balance_accuracy_sara(),
        [
            ("Routes to Deema", lambda r: r["agent"] == "deema"),
            ("Shows 28 remaining", lambda r: "28" in r["response"]),
        ])

    # ── Employee Info ──
    print("[Employee Info]")

    await run_test("Employee Info Lookup", "Employee Info",
        test_employee_info(),
        [
            ("Routes to Deema", lambda r: r["agent"] == "deema"),
            ("Contains name", lambda r: "omar" in r["response"].lower() or "Omar" in r["response"]),
            ("Contains job title", lambda r: any(w in r["response"].lower() for w in ["developer", "senior"])),
        ])

    # ── Leave Request ──
    print("[Leave Request]")

    await run_test("Submit Leave Request", "Leave Request",
        test_leave_request(),
        [
            ("Routes to Deema", lambda r: r["agent"] == "deema"),
            ("Acknowledges request", lambda r: any(w in r["response"].lower() for w in ["submit", "request", "إجازة", "طلب", "تم", "approved", "pending"])),
            ("Has response", lambda r: len(r["response"]) > 20),
        ])

    # ── Routing ──
    print("[Routing]")

    await run_test("Routes Leave Query to Deema", "Routing",
        test_routing_to_deema(),
        [("Routes to Deema", lambda r: r["agent"] == "deema")])

    await run_test("Handles General Greeting", "Routing",
        test_greeting(),
        [
            ("Has response", lambda r: len(r["response"]) > 5),
            ("Defaults to Deema", lambda r: r["agent"] == "deema"),
        ])

    # ── Error Handling ──
    print("[Error Handling]")

    await run_test("Invalid Employee ID → 404", "Error Handling",
        test_invalid_employee(),
        [("Returns 404", lambda r: r["status_code"] == 404)])

    await run_test("Empty Message → 400", "Error Handling",
        test_empty_message(),
        [("Returns 400", lambda r: r["status_code"] == 400)])

    # ── Conversation ──
    print("[Conversation]")

    await run_test("Conversation Memory (Follow-up)", "Conversation",
        test_conversation_memory(),
        [
            ("Routes to Deema", lambda r: r["agent"] == "deema"),
            ("Mentions sick leave", lambda r: any(w in r["response"].lower() for w in ["sick", "مرض", "30"])),
        ])

    # ── Language ──
    print("[Language]")

    await run_test("Arabic Employee → Arabic Response", "Language",
        test_bilingual_response(),
        [
            ("Contains Arabic characters", lambda r: any(c >= '\u0600' and c <= '\u06FF' for c in r["response"])),
        ])

    await run_test("English Employee → English Response", "Language",
        test_english_response(),
        [
            ("Mostly English", lambda r: sum(1 for c in r["response"] if c.isascii()) > len(r["response"]) * 0.5),
        ])

    report.end_time = time.time()
    print_report()


def print_report():
    """Print formatted test report."""
    print()
    print("=" * 70)
    print("  TEST REPORT — Deema Agent Regression")
    print("=" * 70)
    print()

    # Group by category
    categories = {}
    for r in report.results:
        categories.setdefault(r.category, []).append(r)

    for cat, tests in categories.items():
        cat_pass = sum(1 for t in tests if t.passed)
        cat_total = len(tests)
        cat_icon = "PASS" if cat_pass == cat_total else "FAIL"
        print(f"  [{cat_icon}] {cat} ({cat_pass}/{cat_total})")
        print(f"  {'─' * 60}")

        for t in tests:
            icon = "PASS" if t.passed else "FAIL"
            print(f"    [{icon}] {t.name} ({t.duration_ms}ms)")
            if t.details:
                for line in t.details.split("\n"):
                    print(f"      {line.strip()}")
            if t.error:
                print(f"        Error: {t.error}")
            if not t.passed and t.response:
                print(f"        Response: {t.response[:120]}...")
        print()

    # Summary
    print("=" * 70)
    pass_rate = (report.passed / report.total * 100) if report.total > 0 else 0
    print(f"  TOTAL: {report.passed}/{report.total} passed ({pass_rate:.0f}%)")
    print(f"  Duration: {report.duration_s:.1f}s")

    if report.failed == 0:
        print(f"  Status: ALL TESTS PASSED")
    else:
        print(f"  Status: {report.failed} FAILED")
        failed = [r.name for r in report.results if not r.passed]
        for f in failed:
            print(f"    - {f}")

    print("=" * 70)

    # Exit code
    sys.exit(0 if report.failed == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
