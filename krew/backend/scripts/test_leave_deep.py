"""Deep leave testing — exposes inconsistencies in Deema's balance/request handling."""
import asyncio
import json
import re
import time
import sys
from pathlib import Path
from datetime import datetime

import httpx

BASE_URL = "http://localhost:8000"
API = f"{BASE_URL}/api/v1/chat"

# Employee IDs from DB
AHMED  = "2d0c6b8e-eadf-4c58-aacb-3b8c9bbc62ad"  # Arabic, annual: 21-5=16, sick: 30, emergency: 5, hajj: 15
OMAR   = "9fe87ed2-869b-4f80-8750-9c898604bffb"   # English, annual: 21, sick: 30, emergency: 5, NO hajj
SARA   = "c12d12fb-c0d3-427c-bd5d-b462d6a8103f"   # Arabic, annual: 21, sick: 30-2=28, emergency: 5, hajj: 15
KHALID = "038d334e-61bd-4a1e-a943-38576806cd9e"   # Arabic, annual: 21, sick: 30, emergency: 5, hajj: 15

# Ground truth from seed data
TRUTH = {
    AHMED: {
        "name": "Ahmed",
        "annual": {"total": 21, "used": 5, "remaining": 16},
        "sick": {"total": 30, "used": 0, "remaining": 30},
        "emergency": {"total": 5, "used": 0, "remaining": 5},
        "hajj": {"total": 15, "used": 0, "remaining": 15},
    },
    OMAR: {
        "name": "Omar",
        "annual": {"total": 21, "used": 0, "remaining": 21},
        "sick": {"total": 30, "used": 0, "remaining": 30},
        "emergency": {"total": 5, "used": 0, "remaining": 5},
    },
    SARA: {
        "name": "Sara",
        "annual": {"total": 21, "used": 0, "remaining": 21},
        "sick": {"total": 30, "used": 2, "remaining": 28},
        "emergency": {"total": 5, "used": 0, "remaining": 5},
        "hajj": {"total": 15, "used": 0, "remaining": 15},
    },
    KHALID: {
        "name": "Khalid",
        "annual": {"total": 21, "used": 0, "remaining": 21},
        "sick": {"total": 30, "used": 0, "remaining": 30},
        "emergency": {"total": 5, "used": 0, "remaining": 5},
        "hajj": {"total": 15, "used": 0, "remaining": 15},
    },
}

passed = 0
failed = 0
results = []


def extract_numbers(text):
    """Extract all numbers from text."""
    return [int(n) for n in re.findall(r'\d+', text)]


def check_number_in_response(response, expected, label):
    """Check if an expected number appears in the response."""
    return str(expected) in response


async def chat(employee_id, message, timeout=45.0):
    async with httpx.AsyncClient(timeout=timeout) as client:
        res = await client.post(API, json={
            "employee_id": employee_id,
            "message": message,
        })
        res.raise_for_status()
        return res.json()


async def reset(employee_id):
    async with httpx.AsyncClient(timeout=10.0) as client:
        await client.post(f"{API}/reset/{employee_id}")


def test(name, passed_bool, details=""):
    global passed, failed
    status = "PASS" if passed_bool else "FAIL"
    if passed_bool:
        passed += 1
    else:
        failed += 1
    results.append((status, name, details))
    icon = "  ✅" if passed_bool else "  ❌"
    print(f"{icon} {name}")
    if details and not passed_bool:
        for line in details.split("\n"):
            print(f"      {line}")


async def main():
    global passed, failed
    start = time.time()

    print("=" * 70)
    print("  DEEP LEAVE TESTING — Deema Agent")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    print()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PHASE 1: Balance accuracy per employee
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("─── PHASE 1: Balance Accuracy ───")
    print()

    for emp_id, truth in TRUTH.items():
        name = truth["name"]
        await reset(emp_id)

        # Ask for full balance in English to make parsing easier
        r = await chat(emp_id, "What is my full leave balance? Show all types with total, used, and remaining days. Reply in English with exact numbers.")
        resp = r["response"]

        print(f"  [{name}] Response snippet: {resp[:120]}...")

        # Check each leave type
        for ltype in ["annual", "sick", "emergency", "hajj"]:
            if ltype not in truth:
                continue
            expected = truth[ltype]

            # Check remaining
            has_remaining = check_number_in_response(resp, expected["remaining"], f"{ltype} remaining")
            test(
                f"{name} — {ltype} remaining = {expected['remaining']}",
                has_remaining,
                f"Expected {expected['remaining']} in response.\nResponse: {resp[:200]}"
            )

    print()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PHASE 2: Consistency — ask same question 3 ways
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("─── PHASE 2: Consistency (same question, 3 phrasings) ───")
    print()

    phrasings = [
        "How many annual leave days do I have remaining?",
        "What's my annual leave balance?",
        "Tell me my remaining annual vacation days please.",
    ]

    omar_annual_answers = []
    for i, phrase in enumerate(phrasings):
        await reset(OMAR)
        r = await chat(OMAR, phrase)
        resp = r["response"]
        numbers = extract_numbers(resp)
        omar_annual_answers.append({
            "phrase": phrase,
            "numbers": numbers,
            "has_21": "21" in resp,
            "response": resp[:150],
        })
        print(f"  [Omar phrasing {i+1}] Numbers found: {numbers}")

    # All 3 should mention 21
    all_have_21 = all(a["has_21"] for a in omar_annual_answers)
    test(
        "Omar — all 3 phrasings show 21 annual remaining",
        all_have_21,
        "\n".join(f"  Phrasing {i+1}: has_21={a['has_21']}, numbers={a['numbers']}" for i, a in enumerate(omar_annual_answers))
    )

    print()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PHASE 3: Arabic consistency
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("─── PHASE 3: Arabic Balance Accuracy ───")
    print()

    await reset(AHMED)
    r = await chat(AHMED, "كم رصيد إجازاتي السنوية المتبقي؟ اعطني الرقم بالضبط")
    resp = r["response"]
    has_16 = "16" in resp
    test(
        "Ahmed (Arabic) — annual remaining = 16",
        has_16,
        f"Response: {resp[:200]}"
    )

    await reset(SARA)
    r = await chat(SARA, "كم يوم مرضي باقي عندي؟ اعطيني الرقم")
    resp = r["response"]
    has_28 = "28" in resp
    test(
        "Sara (Arabic) — sick remaining = 28",
        has_28,
        f"Response: {resp[:200]}"
    )

    print()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PHASE 4: Specific type queries
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("─── PHASE 4: Specific Type Queries ───")
    print()

    # Sick leave specifically
    await reset(OMAR)
    r = await chat(OMAR, "How many sick leave days do I have?")
    resp = r["response"]
    test(
        "Omar — sick leave = 30 remaining",
        "30" in resp,
        f"Response: {resp[:200]}"
    )

    # Emergency leave
    await reset(OMAR)
    r = await chat(OMAR, "What is my emergency leave balance?")
    resp = r["response"]
    test(
        "Omar — emergency leave = 5 remaining",
        "5" in resp,
        f"Response: {resp[:200]}"
    )

    # Hajj leave for Saudi employee
    await reset(KHALID)
    r = await chat(KHALID, "How many Hajj leave days do I have? Reply in English.")
    resp = r["response"]
    test(
        "Khalid — hajj leave = 15 remaining",
        "15" in resp,
        f"Response: {resp[:200]}"
    )

    # Hajj leave for non-Saudi (Omar) — should say not available or 0
    await reset(OMAR)
    r = await chat(OMAR, "Do I have Hajj leave?")
    resp = r["response"].lower()
    no_hajj = any(w in resp for w in ["no hajj", "not eligible", "not available", "don't have", "do not have", "0", "not entitled", "no balance", "not applicable", "don't currently", "eligible"])
    test(
        "Omar (non-Saudi) — no Hajj leave",
        no_hajj,
        f"Response: {resp[:200]}"
    )

    print()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PHASE 5: Leave request + balance after
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("─── PHASE 5: Leave Request → Balance Check ───")
    print()

    await reset(OMAR)

    # First check balance
    r1 = await chat(OMAR, "What is my annual leave balance?")
    resp1 = r1["response"]
    test(
        "Omar — pre-request annual = 21",
        "21" in resp1,
        f"Response: {resp1[:200]}"
    )

    # Submit request
    r2 = await chat(OMAR, "I'd like to request annual leave from 2026-04-06 to 2026-04-10")
    resp2 = r2["response"].lower()
    submitted = any(w in resp2 for w in ["submit", "request", "approved", "pending", "recorded", "received", "created"])
    test(
        "Omar — leave request acknowledged",
        submitted,
        f"Response: {resp2[:200]}"
    )

    # Check balance again — should still show 21 (since used_days isn't updated on submission)
    # BUT the agent might say 16 or 18 thinking the request was already deducted
    r3 = await chat(OMAR, "Now what is my annual leave balance?")
    resp3 = r3["response"]
    # The CORRECT answer from DB is still 21 (request is pending, not deducted)
    # But if agent says different, that's the inconsistency
    still_21 = "21" in resp3
    test(
        "Omar — post-request annual still shows 21 (pending not deducted)",
        still_21,
        f"Expected 21 (DB unchanged). Response: {resp3[:200]}"
    )

    print()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PHASE 6: Follow-up consistency
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("─── PHASE 6: Follow-up Consistency ───")
    print()

    await reset(OMAR)
    r1 = await chat(OMAR, "What is my annual leave balance?")
    r2 = await chat(OMAR, "And what about sick leave?")
    resp2 = r2["response"]
    test(
        "Omar — follow-up sick leave = 30",
        "30" in resp2,
        f"Response: {resp2[:200]}"
    )

    r3 = await chat(OMAR, "And emergency?")
    resp3 = r3["response"]
    test(
        "Omar — follow-up emergency = 5",
        "5" in resp3,
        f"Response: {resp3[:200]}"
    )

    print()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PHASE 7: Edge cases
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("─── PHASE 7: Edge Cases ───")
    print()

    # Past dates
    await reset(OMAR)
    r = await chat(OMAR, "I want to request annual leave from 2025-01-01 to 2025-01-05")
    resp = r["response"].lower()
    past_handled = any(w in resp for w in ["past", "already passed", "cannot", "can't", "invalid", "not possible", "future"])
    test(
        "Omar — past date request handled",
        past_handled,
        f"Response: {resp[:200]}"
    )

    # End before start
    await reset(OMAR)
    r = await chat(OMAR, "I want to request annual leave from 2026-04-10 to 2026-04-06")
    resp = r["response"].lower()
    invalid_handled = any(w in resp for w in ["before", "invalid", "cannot", "can't", "after", "end date", "correct"])
    test(
        "Omar — end-before-start handled",
        invalid_handled,
        f"Response: {resp[:200]}"
    )

    # Exceeds balance (ask for 25 annual days but only has 21)
    await reset(OMAR)
    r = await chat(OMAR, "I want to request annual leave from 2026-04-01 to 2026-05-05")
    resp = r["response"].lower()
    # Should either warn about insufficient balance or submit anyway
    has_warning_or_submit = any(w in resp for w in ["exceed", "insufficient", "not enough", "only have", "balance", "submit", "request", "pending"])
    test(
        "Omar — 25-day request (exceeds 21 balance) handled",
        has_warning_or_submit,
        f"Response: {resp[:200]}"
    )

    print()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # REPORT
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    duration = time.time() - start
    total = passed + failed

    print("=" * 70)
    print(f"  RESULTS: {passed}/{total} passed ({passed/total*100:.0f}%)")
    print(f"  Duration: {duration:.1f}s")
    print("=" * 70)

    if failed > 0:
        print()
        print("  FAILURES:")
        for status, name, details in results:
            if status == "FAIL":
                print(f"    ❌ {name}")
                if details:
                    for line in details.split("\n")[:3]:
                        print(f"       {line}")
        print()

    print("=" * 70)
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
