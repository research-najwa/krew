"""Test suite for leave request balance deduction.

Tests the _submit_leave_request and _get_leave_balance tool functions
directly against the DB — no LLM involved, so results are deterministic
and fast.
"""
import asyncio
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select, update
from app.database import async_session
from app.models.employee import Employee
from app.models.leave import LeaveBalance, LeaveRequest, LeaveType, LeaveStatus
from app.agents.deema import DeemaAgent

# ─── Employees ───
KHALID = "038d334e-61bd-4a1e-a943-38576806cd9e"   # annual:21, sick:30, emergency:5, hajj:15
NOURA  = "2666c9aa-ca9a-429d-9c8a-1aeb1a1f1f1c"   # annual:21, sick:30, emergency:5, hajj:15
OMAR   = "9fe87ed2-869b-4f80-8750-9c898604bffb"   # annual:21, sick:30, emergency:5, NO hajj

passed = 0
failed = 0
results = []


def test(name, condition, detail=""):
    global passed, failed
    ok = bool(condition)
    status = "PASS" if ok else "FAIL"
    passed += ok
    failed += (not ok)
    results.append((status, name, detail))
    icon = "  ✅" if ok else "  ❌"
    print(f"{icon} {name}")
    if detail and not ok:
        print(f"      {detail}")


async def reset_balances(db, employee_id, overrides=None):
    """Reset an employee's balances to seed defaults."""
    defaults = {
        LeaveType.annual: 21,
        LeaveType.sick: 30,
        LeaveType.emergency: 5,
        LeaveType.hajj: 15,
    }
    if overrides:
        defaults.update(overrides)

    for ltype, total in defaults.items():
        result = await db.execute(
            select(LeaveBalance).where(
                LeaveBalance.employee_id == UUID(employee_id),
                LeaveBalance.leave_type == ltype,
                LeaveBalance.year == 2026,
            )
        )
        bal = result.scalar_one_or_none()
        if bal:
            bal.used_days = 0
            bal.total_days = total

    # Delete any test leave requests
    result = await db.execute(
        select(LeaveRequest).where(LeaveRequest.employee_id == UUID(employee_id))
    )
    for req in result.scalars().all():
        await db.delete(req)

    await db.commit()


async def get_balance(db, employee_id, leave_type):
    """Get current balance from DB."""
    result = await db.execute(
        select(LeaveBalance).where(
            LeaveBalance.employee_id == UUID(employee_id),
            LeaveBalance.leave_type == leave_type,
            LeaveBalance.year == 2026,
        )
    )
    bal = result.scalar_one_or_none()
    return bal


async def count_requests(db, employee_id):
    """Count leave requests for employee."""
    result = await db.execute(
        select(LeaveRequest).where(LeaveRequest.employee_id == UUID(employee_id))
    )
    return len(result.scalars().all())


def next_sunday():
    """Find the next Sunday (a business day in Saudi)."""
    d = date.today()
    while d.weekday() != 6:  # 6 = Sunday
        d += timedelta(days=1)
    return d


async def main():
    start_time = time.time()

    print("=" * 70)
    print("  BALANCE DEDUCTION TEST SUITE")
    print(f"  Direct tool-level tests (no LLM) — deterministic")
    print("=" * 70)
    print()

    async with async_session() as db:
        # Get tenant_id for the agent
        result = await db.execute(select(Employee).where(Employee.id == UUID(KHALID)))
        emp = result.scalar_one()
        tenant_id = emp.tenant_id

        agent = DeemaAgent(db, tenant_id)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 1. BASIC DEDUCTION
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        print("─── 1. Basic Deduction ───")
        await reset_balances(db, KHALID)

        # Verify starting balance
        bal = await get_balance(db, KHALID, LeaveType.annual)
        test("1.1 Khalid starts with 21 annual, 0 used", bal.remaining_days == 21 and bal.used_days == 0)

        # Submit 3-day request (Sun-Tue)
        sun = next_sunday()
        result_json = await agent._submit_leave_request({
            "employee_id": KHALID,
            "leave_type": "annual",
            "start_date": sun.isoformat(),
            "end_date": (sun + timedelta(days=2)).isoformat(),
        })
        data = json.loads(result_json)
        test("1.2 Request submitted successfully", data.get("status") == "submitted", f"Got: {data}")

        bdays = data.get("business_days", 0)
        test("1.3 Business days calculated correctly", bdays > 0, f"business_days={bdays}")

        # Check DB balance updated
        await db.refresh(bal)
        test(
            f"1.4 Balance deducted: used={bal.used_days}, remaining={bal.remaining_days}",
            bal.used_days == bdays and bal.remaining_days == 21 - bdays,
            f"Expected used={bdays}, remaining={21 - bdays}. Got used={bal.used_days}, remaining={bal.remaining_days}"
        )

        # Check leave request record exists
        req_count = await count_requests(db, KHALID)
        test("1.5 Leave request record created in DB", req_count == 1, f"Found {req_count} requests")

        print()

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 2. MULTIPLE REQUESTS ACCUMULATE
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        print("─── 2. Multiple Requests Accumulate ───")
        await reset_balances(db, NOURA)

        # First request: 2 days
        sun = next_sunday()
        r1 = json.loads(await agent._submit_leave_request({
            "employee_id": NOURA,
            "leave_type": "annual",
            "start_date": sun.isoformat(),
            "end_date": (sun + timedelta(days=1)).isoformat(),
        }))
        days1 = r1.get("business_days", 0)
        test("2.1 First request submitted", r1.get("status") == "submitted")

        # Second request: different week
        sun2 = sun + timedelta(days=14)
        r2 = json.loads(await agent._submit_leave_request({
            "employee_id": NOURA,
            "leave_type": "annual",
            "start_date": sun2.isoformat(),
            "end_date": (sun2 + timedelta(days=2)).isoformat(),
        }))
        days2 = r2.get("business_days", 0)
        test("2.2 Second request submitted", r2.get("status") == "submitted")

        total_used = days1 + days2
        bal = await get_balance(db, NOURA, LeaveType.annual)
        await db.refresh(bal)
        test(
            f"2.3 Cumulative deduction: used={bal.used_days} (expected {total_used})",
            bal.used_days == total_used,
            f"days1={days1}, days2={days2}, total={total_used}, actual_used={bal.used_days}"
        )
        test(
            f"2.4 Remaining correct: {bal.remaining_days} (expected {21 - total_used})",
            bal.remaining_days == 21 - total_used,
        )

        req_count = await count_requests(db, NOURA)
        test("2.5 Two request records in DB", req_count == 2, f"Found {req_count}")

        print()

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 3. INSUFFICIENT BALANCE REJECTED
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        print("─── 3. Insufficient Balance Rejected ───")
        await reset_balances(db, KHALID)

        # Set used to 19 so only 2 remaining
        bal = await get_balance(db, KHALID, LeaveType.annual)
        bal.used_days = 19
        await db.commit()
        await db.refresh(bal)
        test("3.1 Setup: Khalid has 2 annual remaining", bal.remaining_days == 2)

        # Try to request 5 days — should fail
        sun = next_sunday()
        r = json.loads(await agent._submit_leave_request({
            "employee_id": KHALID,
            "leave_type": "annual",
            "start_date": sun.isoformat(),
            "end_date": (sun + timedelta(days=6)).isoformat(),
        }))
        test("3.2 Excess request rejected", "error" in r, f"Got: {r}")
        test("3.3 Error mentions insufficient", "insufficient" in r.get("error", "").lower(), f"Error: {r.get('error')}")
        test("3.4 Shows remaining days", r.get("remaining_days") == 2, f"remaining_days={r.get('remaining_days')}")

        # Verify balance unchanged
        await db.refresh(bal)
        test("3.5 Balance unchanged after rejection", bal.used_days == 19 and bal.remaining_days == 2)

        # No new request record
        req_count = await count_requests(db, KHALID)
        test("3.6 No request record created", req_count == 0, f"Found {req_count}")

        print()

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 4. DIFFERENT LEAVE TYPES INDEPENDENT
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        print("─── 4. Different Leave Types Independent ───")
        await reset_balances(db, KHALID)

        sun = next_sunday()

        # Submit annual leave
        r1 = json.loads(await agent._submit_leave_request({
            "employee_id": KHALID,
            "leave_type": "annual",
            "start_date": sun.isoformat(),
            "end_date": (sun + timedelta(days=2)).isoformat(),
        }))
        annual_days = r1.get("business_days", 0)
        test("4.1 Annual request submitted", r1.get("status") == "submitted")

        # Submit sick leave (different dates)
        sun2 = sun + timedelta(days=14)
        r2 = json.loads(await agent._submit_leave_request({
            "employee_id": KHALID,
            "leave_type": "sick",
            "start_date": sun2.isoformat(),
            "end_date": (sun2 + timedelta(days=1)).isoformat(),
        }))
        sick_days = r2.get("business_days", 0)
        test("4.2 Sick request submitted", r2.get("status") == "submitted")

        # Check each balance independently
        ann_bal = await get_balance(db, KHALID, LeaveType.annual)
        sick_bal = await get_balance(db, KHALID, LeaveType.sick)
        emg_bal = await get_balance(db, KHALID, LeaveType.emergency)
        await db.refresh(ann_bal)
        await db.refresh(sick_bal)
        await db.refresh(emg_bal)

        test(f"4.3 Annual used={ann_bal.used_days} (expected {annual_days})", ann_bal.used_days == annual_days)
        test(f"4.4 Sick used={sick_bal.used_days} (expected {sick_days})", sick_bal.used_days == sick_days)
        test("4.5 Emergency untouched: used=0", emg_bal.used_days == 0)

        print()

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 5. PAST DATE REJECTED, BALANCE UNCHANGED
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        print("─── 5. Past Date Rejected ───")
        await reset_balances(db, KHALID)

        r = json.loads(await agent._submit_leave_request({
            "employee_id": KHALID,
            "leave_type": "annual",
            "start_date": "2025-06-01",
            "end_date": "2025-06-05",
        }))
        test("5.1 Past date rejected", "error" in r)
        test("5.2 Error mentions past", "past" in r.get("error", "").lower(), f"Error: {r.get('error')}")

        bal = await get_balance(db, KHALID, LeaveType.annual)
        await db.refresh(bal)
        test("5.3 Balance unchanged", bal.used_days == 0)

        print()

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 6. END BEFORE START REJECTED
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        print("─── 6. End Before Start Rejected ───")
        await reset_balances(db, KHALID)

        sun = next_sunday()
        r = json.loads(await agent._submit_leave_request({
            "employee_id": KHALID,
            "leave_type": "annual",
            "start_date": (sun + timedelta(days=5)).isoformat(),
            "end_date": sun.isoformat(),
        }))
        test("6.1 End-before-start rejected", "error" in r)
        test("6.2 Error mentions end date", "end date" in r.get("error", "").lower() or "before" in r.get("error", "").lower())

        bal = await get_balance(db, KHALID, LeaveType.annual)
        await db.refresh(bal)
        test("6.3 Balance unchanged", bal.used_days == 0)

        print()

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 7. WEEKEND-ONLY REQUEST REJECTED
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        print("─── 7. Weekend-Only Dates Rejected ───")
        await reset_balances(db, KHALID)

        # Find next Friday
        d = date.today()
        while d.weekday() != 4:  # 4 = Friday
            d += timedelta(days=1)
        fri = d
        sat = fri + timedelta(days=1)

        r = json.loads(await agent._submit_leave_request({
            "employee_id": KHALID,
            "leave_type": "annual",
            "start_date": fri.isoformat(),
            "end_date": sat.isoformat(),
        }))
        test("7.1 Fri-Sat only request rejected", "error" in r)
        test("7.2 Error mentions weekend", "weekend" in r.get("error", "").lower())

        bal = await get_balance(db, KHALID, LeaveType.annual)
        await db.refresh(bal)
        test("7.3 Balance unchanged", bal.used_days == 0)

        print()

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 8. NON-ELIGIBLE LEAVE TYPE REJECTED
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        print("─── 8. Non-Eligible Leave Type ───")

        sun = next_sunday()
        # Omar has no Hajj balance
        r = json.loads(await agent._submit_leave_request({
            "employee_id": OMAR,
            "leave_type": "hajj",
            "start_date": sun.isoformat(),
            "end_date": (sun + timedelta(days=4)).isoformat(),
        }))
        test("8.1 Hajj for non-Saudi rejected", "error" in r)
        test("8.2 Error mentions no balance", "not available" in r.get("error", "").lower() or "no" in r.get("error", "").lower())

        print()

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 9. EXACT BALANCE REQUEST (use all remaining)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        print("─── 9. Use Exact Remaining Balance ───")
        await reset_balances(db, KHALID)

        # Set emergency to 5 total, 3 used → 2 remaining
        bal = await get_balance(db, KHALID, LeaveType.emergency)
        bal.used_days = 3
        await db.commit()
        await db.refresh(bal)
        test("9.1 Setup: 2 emergency days remaining", bal.remaining_days == 2)

        # Request exactly 2 business days (Sun-Mon)
        sun = next_sunday()
        r = json.loads(await agent._submit_leave_request({
            "employee_id": KHALID,
            "leave_type": "emergency",
            "start_date": sun.isoformat(),
            "end_date": (sun + timedelta(days=1)).isoformat(),
        }))
        bdays = r.get("business_days", 0)
        test("9.2 Exact balance request accepted", r.get("status") == "submitted")

        await db.refresh(bal)
        test(f"9.3 Balance fully used: remaining={bal.remaining_days}", bal.remaining_days == 2 - bdays)

        # Now try one more day — should fail
        sun2 = sun + timedelta(days=14)
        r2 = json.loads(await agent._submit_leave_request({
            "employee_id": KHALID,
            "leave_type": "emergency",
            "start_date": sun2.isoformat(),
            "end_date": sun2.isoformat(),
        }))
        test("9.4 Next request rejected (zero remaining)", "error" in r2)

        print()

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 10. BALANCE CHECK REFLECTS DEDUCTION
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        print("─── 10. get_leave_balance Reflects Deduction ───")
        await reset_balances(db, KHALID)

        # Check before
        before_json = json.loads(await agent._get_leave_balance(UUID(KHALID), "annual"))
        before_remaining = before_json[0]["remaining"] if isinstance(before_json, list) else 0
        test("10.1 Before: annual remaining = 21", before_remaining == 21)

        # Submit 3-day request
        sun = next_sunday()
        r = json.loads(await agent._submit_leave_request({
            "employee_id": KHALID,
            "leave_type": "annual",
            "start_date": sun.isoformat(),
            "end_date": (sun + timedelta(days=2)).isoformat(),
        }))
        bdays = r.get("business_days", 0)
        test("10.2 Request submitted", r.get("status") == "submitted")

        # Check after — must use fresh session query
        after_json = json.loads(await agent._get_leave_balance(UUID(KHALID), "annual"))
        after_remaining = after_json[0]["remaining"] if isinstance(after_json, list) else -1
        expected = 21 - bdays
        test(
            f"10.3 After: annual remaining = {after_remaining} (expected {expected})",
            after_remaining == expected,
            f"before={before_remaining}, deducted={bdays}, after={after_remaining}"
        )

        after_used = after_json[0]["used"] if isinstance(after_json, list) else -1
        test(f"10.4 After: used = {after_used} (expected {bdays})", after_used == bdays)

        print()

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # CLEANUP — reset all test employees
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        print("─── Cleanup ───")
        for eid in [KHALID, NOURA, OMAR]:
            await reset_balances(db, eid)
        print("  Balances and requests reset to seed defaults.")
        print()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # REPORT
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    duration = time.time() - start_time
    total = passed + failed
    pct = (passed / total * 100) if total > 0 else 0

    print("=" * 70)
    print(f"  RESULTS: {passed}/{total} passed ({pct:.0f}%)")
    print(f"  Duration: {duration:.1f}s")

    if failed > 0:
        print()
        print("  FAILURES:")
        for status, name, detail in results:
            if status == "FAIL":
                print(f"    ❌ {name}")
                if detail:
                    print(f"       {detail}")

    print("=" * 70)
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
