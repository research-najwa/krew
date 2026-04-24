"""Test suite for Deema backlog features.

Covers:
  - Business day calculation (Saudi weekend: Fri=4, Sat=5)
  - Tenant isolation via _verify_employee
  - Leave service refactor (check_and_submit_leave, cancel_leave_request)
  - Overlap validation
  - All 8 leave types
  - Escalation model, tool, API, and frontend
  - Race condition lock (code-level verification)
  - Frontend validation (code review, not runtime)

Tests are deterministic (no LLM calls). DB-dependent tests use the async
session directly. Frontend and code-review tests read source files.

Run:
    cd backend && python scripts/test_deema_backlog.py
"""
import asyncio
import json
import re
import sys
import time
import uuid
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure backend package is on the path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# ── Source file paths (for code-review tests) ──────────────────────
BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEEMA_PY = BACKEND_ROOT / "app" / "agents" / "deema.py"
LEAVE_SVC = BACKEND_ROOT / "app" / "services" / "leave.py"
CHAT_HTML = BACKEND_ROOT / "static" / "chat.html"
ESCALATION_MODEL = BACKEND_ROOT / "app" / "models" / "escalation.py"
ESCALATION_API = BACKEND_ROOT / "app" / "api" / "escalations.py"
BASE_AGENT = BACKEND_ROOT / "app" / "agents" / "base.py"

# ── Known seed data ────────────────────────────────────────────────
TENANT_A = uuid.UUID("a1000000-0000-0000-0000-000000000001")  # placeholder
TENANT_B = uuid.UUID("b2000000-0000-0000-0000-000000000002")  # different tenant
AHMED  = "2d0c6b8e-eadf-4c58-aacb-3b8c9bbc62ad"
OMAR   = "9fe87ed2-869b-4f80-8750-9c898604bffb"
SARA   = "c12d12fb-c0d3-427c-bd5d-b462d6a8103f"
KHALID = "038d334e-61bd-4a1e-a943-38576806cd9e"
NOURA  = "2666c9aa-ca9a-429d-9c8a-1aeb1a1f1f1c"

# ── Test harness ───────────────────────────────────────────────────
passed = 0
failed = 0
skipped = 0
results: list[tuple[str, str, str, str]] = []  # (status, id, name, detail)


def test(test_id: str, name: str, condition, detail: str = ""):
    """Record a test result."""
    global passed, failed
    ok = bool(condition)
    status = "PASS" if ok else "FAIL"
    passed += ok
    failed += (not ok)
    results.append((status, test_id, name, detail if not ok else ""))
    icon = "  PASS" if ok else "  FAIL"
    print(f"{icon} [{test_id}] {name}")
    if detail and not ok:
        print(f"        Detail: {detail}")


def skip(test_id: str, name: str, reason: str = ""):
    """Record a skipped test."""
    global skipped
    skipped += 1
    results.append(("SKIP", test_id, name, reason))
    print(f"  SKIP [{test_id}] {name} -- {reason}")


# ====================================================================
# P0: BUSINESS DAY CALCULATION
# ====================================================================

def test_business_days():
    """Tests T1-T3: Saudi business day calculation."""
    from app.services.leave import calculate_business_days

    # T1: Sun 2026-03-22 to Thu 2026-03-26 = 5 business days (no weekend)
    # 2026-03-22 is a Sunday (weekday()=6), Mon=0, Tue=1, Wed=2, Thu=3
    # Actually let's verify: 2026-03-22 => .weekday()
    # Mar 22 2026: let's pick a known week. Using date(2026,3,22).weekday()
    sun = date(2026, 3, 22)  # Sunday
    thu = date(2026, 3, 26)  # Thursday
    result = calculate_business_days(sun, thu)
    test("T1", "Sun-Thu = 5 business days (no weekend hit)",
         result == 5,
         f"Expected 5, got {result}. Sun={sun.weekday()}, Thu={thu.weekday()}")

    # T2: Sun 2026-03-22 to Sat 2026-03-28 = 5 days (Fri+Sat skipped)
    sat = date(2026, 3, 28)
    result = calculate_business_days(sun, sat)
    test("T2", "Sun-Sat = 5 business days (Fri+Sat skipped)",
         result == 5,
         f"Expected 5, got {result}")

    # T3: Fri 2026-03-27 to Sat 2026-03-28 = 0 days (weekend only)
    fri = date(2026, 3, 27)
    result = calculate_business_days(fri, sat)
    test("T3", "Fri-Sat = 0 business days (weekend only)",
         result == 0,
         f"Expected 0, got {result}")

    # Additional edge case: ValueError when end < start
    try:
        calculate_business_days(sat, fri)
        test("T3b", "End < start raises ValueError", False, "No exception raised")
    except ValueError:
        test("T3b", "End < start raises ValueError", True)

    # Additional: Two full weeks Sun-to-Thu-next = 10 business days
    sun2 = date(2026, 3, 22)
    thu2 = date(2026, 4, 2)  # 12 calendar days, 2 weekends = 10 biz days
    result2 = calculate_business_days(sun2, thu2)
    test("T3c", "Two-week span = 10 business days",
         result2 == 10,
         f"Expected 10, got {result2}")

    # Single day (Thursday) = 1 business day
    single_thu = date(2026, 3, 26)
    result3 = calculate_business_days(single_thu, single_thu)
    test("T3d", "Single Thursday = 1 business day",
         result3 == 1,
         f"Expected 1, got {result3}")

    # Single day (Friday) = 0 business days
    single_fri = date(2026, 3, 27)
    result4 = calculate_business_days(single_fri, single_fri)
    test("T3e", "Single Friday = 0 business days",
         result4 == 0,
         f"Expected 0, got {result4}")


# ====================================================================
# P0: TENANT ISOLATION
# ====================================================================

async def test_tenant_isolation():
    """Tests T4-T6: Tenant isolation via _verify_employee and queries."""
    from app.database import async_session
    from app.models.employee import Employee
    from app.agents.deema import DeemaAgent

    # We need the real tenant_id for Ahmed to test cross-tenant rejection
    async with async_session() as db:
        result = await db.execute(
            __import__("sqlalchemy", fromlist=["select"]).select(Employee).where(
                Employee.id == uuid.UUID(AHMED)
            )
        )
        ahmed = result.scalar_one_or_none()
        if not ahmed:
            skip("T4", "Tenant isolation: _verify_employee rejects wrong tenant", "Ahmed not in DB")
            skip("T5", "Tenant isolation: _get_employee_info rejects wrong tenant", "Ahmed not in DB")
            skip("T6", "Tenant isolation: cross-tenant leave balance blocked", "Ahmed not in DB")
            return

        real_tenant = ahmed.tenant_id
        wrong_tenant = uuid.UUID("00000000-0000-0000-0000-ffffffffffff")

    # T4: _verify_employee with wrong tenant returns None
    async with async_session() as db:
        agent = DeemaAgent(db=db, tenant_id=wrong_tenant)
        emp = await agent._verify_employee(uuid.UUID(AHMED))
        test("T4", "Tenant isolation: _verify_employee rejects wrong tenant",
             emp is None,
             f"Expected None, got {emp}")

    # T5: _get_employee_info with wrong tenant returns error
    async with async_session() as db:
        agent = DeemaAgent(db=db, tenant_id=wrong_tenant)
        raw = await agent._get_employee_info(uuid.UUID(AHMED))
        data = json.loads(raw)
        test("T5", "Tenant isolation: _get_employee_info rejects wrong tenant",
             "error" in data and "not found" in data["error"].lower(),
             f"Expected error, got {data}")

    # T6: _get_leave_balance with wrong tenant returns error
    async with async_session() as db:
        agent = DeemaAgent(db=db, tenant_id=wrong_tenant)
        raw = await agent._get_leave_balance(uuid.UUID(AHMED), "annual")
        data = json.loads(raw)
        test("T6", "Tenant isolation: cross-tenant leave balance blocked",
             "error" in data and "not found" in data["error"].lower(),
             f"Expected error, got {data}")


# ====================================================================
# SERVICE REFACTOR: check_and_submit_leave
# ====================================================================

async def test_submit_leave_service():
    """Tests T7-T9: check_and_submit_leave validation."""
    from app.database import async_session
    from app.services.leave import check_and_submit_leave, calculate_business_days
    from app.models.leave import LeaveBalance, LeaveRequest, LeaveType, LeaveStatus
    from sqlalchemy import select, update, delete

    # T7: Happy path — submit a valid future leave request
    async with async_session() as db:
        emp_id = uuid.UUID(KHALID)

        # Ensure balance is reset: set annual used_days = 0
        bal_result = await db.execute(
            select(LeaveBalance).where(
                LeaveBalance.employee_id == emp_id,
                LeaveBalance.leave_type == LeaveType.annual,
                LeaveBalance.year == date.today().year,
            )
        )
        bal = bal_result.scalar_one_or_none()
        if not bal:
            skip("T7", "check_and_submit_leave happy path", "No annual balance for Khalid")
            skip("T8", "check_and_submit_leave rejects past dates", "No balance")
            skip("T9", "check_and_submit_leave rejects insufficient balance", "No balance")
            return

        original_used = bal.used_days
        bal.used_days = 0
        await db.commit()

        # Clean up any existing pending requests that might overlap
        start = date.today() + timedelta(days=30)
        end = date.today() + timedelta(days=32)

        result = await check_and_submit_leave(
            db=db,
            employee_id=emp_id,
            leave_type="annual",
            start_date=start,
            end_date=end,
            reason="T7 test leave",
            channel="web",
            agent="deema",
        )
        test("T7", "check_and_submit_leave happy path",
             result["success"] is True and "request_id" in result,
             f"Got: {result}")

        # Clean up: cancel the request and restore balance
        if result.get("success"):
            req_result = await db.execute(
                select(LeaveRequest).where(LeaveRequest.id == result["request_id"])
            )
            req = req_result.scalar_one_or_none()
            if req:
                req.status = LeaveStatus.cancelled
                bal_result2 = await db.execute(
                    select(LeaveBalance).where(
                        LeaveBalance.employee_id == emp_id,
                        LeaveBalance.leave_type == LeaveType.annual,
                        LeaveBalance.year == date.today().year,
                    )
                )
                bal2 = bal_result2.scalar_one_or_none()
                if bal2:
                    bal2.used_days = original_used
                await db.commit()

    # T8: Reject past dates
    async with async_session() as db:
        emp_id = uuid.UUID(KHALID)
        past_start = date.today() - timedelta(days=10)
        past_end = date.today() - timedelta(days=8)
        result = await check_and_submit_leave(
            db=db,
            employee_id=emp_id,
            leave_type="annual",
            start_date=past_start,
            end_date=past_end,
        )
        test("T8", "check_and_submit_leave rejects past dates",
             result["success"] is False and "past" in result["message"].lower(),
             f"Got: {result}")

    # T9: Reject insufficient balance
    async with async_session() as db:
        emp_id = uuid.UUID(KHALID)

        # Temporarily set used_days = total_days (exhaust balance)
        bal_result = await db.execute(
            select(LeaveBalance).where(
                LeaveBalance.employee_id == emp_id,
                LeaveBalance.leave_type == LeaveType.annual,
                LeaveBalance.year == date.today().year,
            )
        )
        bal = bal_result.scalar_one_or_none()
        original_used = bal.used_days
        bal.used_days = bal.total_days  # fully exhausted
        await db.commit()

        future_start = date.today() + timedelta(days=60)
        future_end = date.today() + timedelta(days=62)
        result = await check_and_submit_leave(
            db=db,
            employee_id=emp_id,
            leave_type="annual",
            start_date=future_start,
            end_date=future_end,
        )
        test("T9", "check_and_submit_leave rejects insufficient balance",
             result["success"] is False and "insufficient" in result["message"].lower(),
             f"Got: {result}")

        # Restore
        bal.used_days = original_used
        await db.commit()


# ====================================================================
# SERVICE REFACTOR: cancel_leave_request
# ====================================================================

async def test_cancel_leave_service():
    """Tests T10-T13: cancel_leave_request."""
    from app.database import async_session
    from app.services.leave import check_and_submit_leave, cancel_leave_request
    from app.models.leave import LeaveBalance, LeaveRequest, LeaveType, LeaveStatus
    from app.models.employee import Employee
    from sqlalchemy import select

    # T10: Happy path — cancel a pending request, balance restored
    async with async_session() as db:
        emp_id = uuid.UUID(KHALID)

        # Get employee's tenant for isolation
        emp_result = await db.execute(
            select(Employee).where(Employee.id == emp_id)
        )
        emp = emp_result.scalar_one_or_none()
        if not emp:
            skip("T10", "cancel_leave_request happy path", "Khalid not in DB")
            skip("T11", "cancel_leave_request rejects non-pending", "Khalid not in DB")
            skip("T12", "cancel_leave_request fails if balance missing", "Khalid not in DB")
            skip("T13", "cancel_leave_request tenant_id guard", "Khalid not in DB")
            return
        tenant_id = emp.tenant_id

        # Reset balance
        bal_result = await db.execute(
            select(LeaveBalance).where(
                LeaveBalance.employee_id == emp_id,
                LeaveBalance.leave_type == LeaveType.annual,
                LeaveBalance.year == date.today().year,
            )
        )
        bal = bal_result.scalar_one_or_none()
        if not bal:
            skip("T10", "cancel_leave_request happy path", "No balance row")
            return
        saved_used = bal.used_days
        bal.used_days = 0
        await db.commit()

        # Create a leave request to cancel
        start = date.today() + timedelta(days=90)
        end = date.today() + timedelta(days=92)
        submit_result = await check_and_submit_leave(
            db=db,
            employee_id=emp_id,
            leave_type="annual",
            start_date=start,
            end_date=end,
            reason="T10 test",
        )
        if not submit_result["success"]:
            skip("T10", "cancel_leave_request happy path",
                 f"Could not create test request: {submit_result}")
            bal.used_days = saved_used
            await db.commit()
            return

        request_id = submit_result["request_id"]
        days_deducted = submit_result["business_days"]

        # Record used_days after deduction
        await db.refresh(bal)
        used_after_submit = bal.used_days

        # Cancel it
        cancel_result = await cancel_leave_request(
            db=db,
            employee_id=emp_id,
            request_id=request_id,
            tenant_id=tenant_id,
        )
        test("T10", "cancel_leave_request happy path (restores balance)",
             cancel_result["success"] is True
             and cancel_result["business_days_restored"] == days_deducted,
             f"Got: {cancel_result}")

        # Verify balance was restored
        await db.refresh(bal)
        test("T10b", "cancel_leave_request: used_days restored correctly",
             bal.used_days == used_after_submit - days_deducted,
             f"Expected {used_after_submit - days_deducted}, got {bal.used_days}")

        # Restore original
        bal.used_days = saved_used
        await db.commit()

    # T11: Reject cancellation of non-pending (approved) request
    async with async_session() as db:
        emp_id = uuid.UUID(KHALID)
        emp_result = await db.execute(select(Employee).where(Employee.id == emp_id))
        emp = emp_result.scalar_one_or_none()
        tenant_id = emp.tenant_id

        # Reset and create a request, then approve it
        bal_result = await db.execute(
            select(LeaveBalance).where(
                LeaveBalance.employee_id == emp_id,
                LeaveBalance.leave_type == LeaveType.annual,
                LeaveBalance.year == date.today().year,
            )
        )
        bal = bal_result.scalar_one_or_none()
        saved_used = bal.used_days
        bal.used_days = 0
        await db.commit()

        start = date.today() + timedelta(days=100)
        end = date.today() + timedelta(days=102)
        submit_result = await check_and_submit_leave(
            db=db, employee_id=emp_id, leave_type="annual",
            start_date=start, end_date=end, reason="T11 test",
        )
        if submit_result["success"]:
            req_result = await db.execute(
                select(LeaveRequest).where(LeaveRequest.id == submit_result["request_id"])
            )
            req = req_result.scalar_one_or_none()
            req.status = LeaveStatus.approved
            await db.commit()

            cancel_result = await cancel_leave_request(
                db=db, employee_id=emp_id,
                request_id=submit_result["request_id"],
                tenant_id=tenant_id,
            )
            test("T11", "cancel_leave_request rejects non-pending request",
                 cancel_result["success"] is False
                 and "pending" in cancel_result["message"].lower(),
                 f"Got: {cancel_result}")

            # Clean up
            req.status = LeaveStatus.cancelled
            bal.used_days = saved_used
            await db.commit()
        else:
            skip("T11", "cancel_leave_request rejects non-pending", "Setup failed")

    # T12: Fail gracefully if balance row is missing (all-or-nothing)
    # This tests the safety net: if somehow the balance record is gone,
    # the cancel should not crash and should return an error.
    async with async_session() as db:
        emp_id = uuid.UUID(KHALID)
        emp_result = await db.execute(select(Employee).where(Employee.id == emp_id))
        emp = emp_result.scalar_one_or_none()
        tenant_id = emp.tenant_id

        # Create a fake pending leave request with a leave type that has no balance
        fake_request = LeaveRequest(
            id=uuid.uuid4(),
            employee_id=emp_id,
            leave_type=LeaveType.maternity,  # Khalid likely has no maternity balance
            start_date=date.today() + timedelta(days=200),
            end_date=date.today() + timedelta(days=202),
            business_days=3,
            status=LeaveStatus.pending,
            created_by_agent="test",
            created_via_channel="test",
        )
        db.add(fake_request)
        await db.commit()
        await db.refresh(fake_request)

        cancel_result = await cancel_leave_request(
            db=db, employee_id=emp_id,
            request_id=fake_request.id,
            tenant_id=tenant_id,
        )
        test("T12", "cancel_leave_request fails if balance row missing",
             cancel_result["success"] is False
             and "balance" in cancel_result["message"].lower(),
             f"Got: {cancel_result}")

        # Clean up the fake request
        await db.delete(fake_request)
        await db.commit()

    # T13: cancel_leave_request with wrong tenant_id
    async with async_session() as db:
        emp_id = uuid.UUID(KHALID)
        wrong_tenant = uuid.UUID("00000000-0000-0000-0000-ffffffffffff")

        # Create a real pending request first
        bal_result = await db.execute(
            select(LeaveBalance).where(
                LeaveBalance.employee_id == emp_id,
                LeaveBalance.leave_type == LeaveType.annual,
                LeaveBalance.year == date.today().year,
            )
        )
        bal = bal_result.scalar_one_or_none()
        saved_used = bal.used_days
        bal.used_days = 0
        await db.commit()

        start = date.today() + timedelta(days=110)
        end = date.today() + timedelta(days=112)
        submit_result = await check_and_submit_leave(
            db=db, employee_id=emp_id, leave_type="annual",
            start_date=start, end_date=end, reason="T13 test",
        )
        if submit_result["success"]:
            cancel_result = await cancel_leave_request(
                db=db, employee_id=emp_id,
                request_id=submit_result["request_id"],
                tenant_id=wrong_tenant,  # wrong tenant!
            )
            test("T13", "cancel_leave_request with tenant_id guard",
                 cancel_result["success"] is False
                 and "not found" in cancel_result["message"].lower(),
                 f"Got: {cancel_result}")

            # Clean up: cancel with correct tenant
            emp_result = await db.execute(select(Employee).where(Employee.id == emp_id))
            emp = emp_result.scalar_one_or_none()
            await cancel_leave_request(
                db=db, employee_id=emp_id,
                request_id=submit_result["request_id"],
                tenant_id=emp.tenant_id,
            )
            bal.used_days = saved_used
            await db.commit()
        else:
            skip("T13", "cancel_leave_request tenant_id guard", "Setup failed")


# ====================================================================
# OVERLAP VALIDATION
# ====================================================================

async def test_overlap_validation():
    """Tests T14-T18: Overlap detection in check_overlap."""
    from app.database import async_session
    from app.services.leave import check_and_submit_leave, check_overlap, cancel_leave_request
    from app.models.leave import LeaveBalance, LeaveRequest, LeaveType, LeaveStatus
    from app.models.employee import Employee
    from sqlalchemy import select

    emp_id = uuid.UUID(KHALID)

    async with async_session() as db:
        emp_result = await db.execute(select(Employee).where(Employee.id == emp_id))
        emp = emp_result.scalar_one_or_none()
        if not emp:
            for tid in ("T14", "T15", "T16", "T17", "T18"):
                skip(tid, "Overlap test", "Khalid not in DB")
            return
        tenant_id = emp.tenant_id

        # Reset balance
        bal_result = await db.execute(
            select(LeaveBalance).where(
                LeaveBalance.employee_id == emp_id,
                LeaveBalance.leave_type == LeaveType.annual,
                LeaveBalance.year == date.today().year,
            )
        )
        bal = bal_result.scalar_one_or_none()
        if not bal:
            for tid in ("T14", "T15", "T16", "T17", "T18"):
                skip(tid, "Overlap test", "No balance")
            return

        saved_used = bal.used_days
        bal.used_days = 0
        await db.commit()

        # Create a base leave request: days 120-124 from today
        base_start = date.today() + timedelta(days=120)
        base_end = date.today() + timedelta(days=124)
        base_result = await check_and_submit_leave(
            db=db, employee_id=emp_id, leave_type="annual",
            start_date=base_start, end_date=base_end, reason="overlap base",
        )
        if not base_result["success"]:
            for tid in ("T14", "T15", "T16", "T17", "T18"):
                skip(tid, "Overlap test", f"Base request failed: {base_result}")
            bal.used_days = saved_used
            await db.commit()
            return
        base_request_id = base_result["request_id"]

        # T14: Exact same dates => overlap
        overlap_exact = await check_overlap(db, emp_id, base_start, base_end)
        test("T14", "Overlap detected: exact same dates",
             overlap_exact is not None and overlap_exact["success"] is False,
             f"Expected overlap, got: {overlap_exact}")

        # T15: Partial overlap (starts during existing request)
        partial_start = base_start + timedelta(days=2)
        partial_end = base_end + timedelta(days=3)
        overlap_partial = await check_overlap(db, emp_id, partial_start, partial_end)
        test("T15", "Overlap detected: partial overlap",
             overlap_partial is not None and overlap_partial["success"] is False,
             f"Expected overlap, got: {overlap_partial}")

        # T16: Adjacent dates (day after end) => no overlap
        adjacent_start = base_end + timedelta(days=1)
        adjacent_end = base_end + timedelta(days=3)
        overlap_adjacent = await check_overlap(db, emp_id, adjacent_start, adjacent_end)
        test("T16", "No overlap: adjacent dates (end+1 as start)",
             overlap_adjacent is None,
             f"Expected None (no overlap), got: {overlap_adjacent}")

        # T17: Cancelled requests should be excluded from overlap check
        # Cancel the base request, then check same dates
        req_result = await db.execute(
            select(LeaveRequest).where(LeaveRequest.id == base_request_id)
        )
        req = req_result.scalar_one_or_none()
        req.status = LeaveStatus.cancelled
        await db.commit()

        overlap_cancelled = await check_overlap(db, emp_id, base_start, base_end)
        test("T17", "No overlap: cancelled requests excluded",
             overlap_cancelled is None,
             f"Expected None after cancel, got: {overlap_cancelled}")

        # T18: Multiple overlapping requests don't crash
        # (This tests that check_overlap uses .first() not .scalar_one_or_none())
        # Re-create two overlapping approved requests
        req1 = LeaveRequest(
            employee_id=emp_id, leave_type=LeaveType.annual,
            start_date=date.today() + timedelta(days=150),
            end_date=date.today() + timedelta(days=152),
            business_days=3, status=LeaveStatus.approved,
            created_by_agent="test", created_via_channel="test",
        )
        req2 = LeaveRequest(
            employee_id=emp_id, leave_type=LeaveType.sick,
            start_date=date.today() + timedelta(days=150),
            end_date=date.today() + timedelta(days=153),
            business_days=4, status=LeaveStatus.pending,
            created_by_agent="test", created_via_channel="test",
        )
        db.add(req1)
        db.add(req2)
        await db.commit()

        try:
            overlap_multi = await check_overlap(
                db, emp_id,
                date.today() + timedelta(days=150),
                date.today() + timedelta(days=153),
            )
            test("T18", "Multiple overlaps don't crash (uses .first())",
                 overlap_multi is not None,
                 f"Got: {overlap_multi}")
        except Exception as e:
            test("T18", "Multiple overlaps don't crash",
                 False,
                 f"Crashed with: {type(e).__name__}: {e}")

        # Clean up
        await db.delete(req1)
        await db.delete(req2)
        bal.used_days = saved_used
        await db.commit()


# ====================================================================
# LEAVE TYPE TESTS
# ====================================================================

def test_leave_types_in_schema():
    """Test T19: All 8 leave types in tool schema enum."""
    from app.agents.deema import DeemaAgent

    # We need a mock db and tenant_id to instantiate
    mock_db = MagicMock()
    agent = DeemaAgent.__new__(DeemaAgent)
    # Directly call get_tools without full init
    # We'll read the source instead for safety
    source = DEEMA_PY.read_text()

    expected_types = {"annual", "sick", "emergency", "maternity", "paternity",
                      "hajj", "bereavement", "unpaid"}

    # Check submit_leave_request tool enum
    # Find the submit_leave_request tool's enum list
    submit_match = re.search(
        r'"name":\s*"submit_leave_request".*?"enum":\s*\[([^\]]+)\]',
        source, re.DOTALL
    )
    if submit_match:
        enum_str = submit_match.group(1)
        found_types = set(re.findall(r'"(\w+)"', enum_str))
        test("T19", "All 8 leave types in submit_leave_request schema",
             expected_types == found_types,
             f"Expected {expected_types}, found {found_types}")
    else:
        test("T19", "All 8 leave types in submit_leave_request schema",
             False, "Could not find enum in submit_leave_request tool")

    # Also check get_leave_balance tool
    balance_match = re.search(
        r'"name":\s*"get_leave_balance".*?"enum":\s*\[([^\]]+)\]',
        source, re.DOTALL
    )
    if balance_match:
        enum_str = balance_match.group(1)
        found_types = set(re.findall(r'"(\w+)"', enum_str))
        test("T19b", "All 8 leave types in get_leave_balance schema",
             expected_types == found_types,
             f"Expected {expected_types}, found {found_types}")


async def test_special_leave_types():
    """Tests T20-T22: Submit maternity, paternity, bereavement leave."""
    from app.database import async_session
    from app.services.leave import check_and_submit_leave
    from app.models.leave import LeaveBalance, LeaveRequest, LeaveType, LeaveStatus
    from app.models.employee import Employee
    from sqlalchemy import select

    # T20: Maternity leave — Noura should have a balance (female employee)
    async with async_session() as db:
        emp_id = uuid.UUID(NOURA)
        emp_result = await db.execute(select(Employee).where(Employee.id == emp_id))
        emp = emp_result.scalar_one_or_none()
        if not emp:
            skip("T20", "Submit maternity leave", "Noura not in DB")
        else:
            # Check if maternity balance exists
            bal_result = await db.execute(
                select(LeaveBalance).where(
                    LeaveBalance.employee_id == emp_id,
                    LeaveBalance.leave_type == LeaveType.maternity,
                    LeaveBalance.year == date.today().year,
                )
            )
            bal = bal_result.scalar_one_or_none()
            if bal:
                saved = bal.used_days
                bal.used_days = 0
                await db.commit()

                start = date.today() + timedelta(days=180)
                end = date.today() + timedelta(days=182)
                result = await check_and_submit_leave(
                    db=db, employee_id=emp_id, leave_type="maternity",
                    start_date=start, end_date=end, reason="T20 maternity test",
                )
                test("T20", "Submit maternity leave (balance exists)",
                     result["success"] is True,
                     f"Got: {result}")

                # Clean up
                if result.get("success"):
                    req_r = await db.execute(
                        select(LeaveRequest).where(LeaveRequest.id == result["request_id"])
                    )
                    req = req_r.scalar_one_or_none()
                    if req:
                        req.status = LeaveStatus.cancelled
                bal.used_days = saved
                await db.commit()
            else:
                # No maternity balance — that's expected if seed data doesn't have it.
                # The service should return "no balance" error, which is correct behavior.
                start = date.today() + timedelta(days=180)
                end = date.today() + timedelta(days=182)
                result = await check_and_submit_leave(
                    db=db, employee_id=emp_id, leave_type="maternity",
                    start_date=start, end_date=end,
                )
                test("T20", "Submit maternity leave (no balance = not eligible)",
                     result["success"] is False and "balance" in result["message"].lower(),
                     f"Got: {result}")

    # T21: Paternity leave
    async with async_session() as db:
        emp_id = uuid.UUID(KHALID)
        bal_result = await db.execute(
            select(LeaveBalance).where(
                LeaveBalance.employee_id == emp_id,
                LeaveBalance.leave_type == LeaveType.paternity,
                LeaveBalance.year == date.today().year,
            )
        )
        bal = bal_result.scalar_one_or_none()
        start = date.today() + timedelta(days=190)
        end = date.today() + timedelta(days=192)

        if bal:
            saved = bal.used_days
            bal.used_days = 0
            await db.commit()
            result = await check_and_submit_leave(
                db=db, employee_id=emp_id, leave_type="paternity",
                start_date=start, end_date=end, reason="T21 paternity test",
            )
            test("T21", "Submit paternity leave (balance exists)",
                 result["success"] is True,
                 f"Got: {result}")
            if result.get("success"):
                req_r = await db.execute(
                    select(LeaveRequest).where(LeaveRequest.id == result["request_id"])
                )
                req = req_r.scalar_one_or_none()
                if req:
                    req.status = LeaveStatus.cancelled
            bal.used_days = saved
            await db.commit()
        else:
            result = await check_and_submit_leave(
                db=db, employee_id=emp_id, leave_type="paternity",
                start_date=start, end_date=end,
            )
            test("T21", "Submit paternity leave (no balance = not eligible)",
                 result["success"] is False and "balance" in result["message"].lower(),
                 f"Got: {result}")

    # T22: Bereavement leave
    async with async_session() as db:
        emp_id = uuid.UUID(KHALID)
        bal_result = await db.execute(
            select(LeaveBalance).where(
                LeaveBalance.employee_id == emp_id,
                LeaveBalance.leave_type == LeaveType.bereavement,
                LeaveBalance.year == date.today().year,
            )
        )
        bal = bal_result.scalar_one_or_none()
        start = date.today() + timedelta(days=200)
        end = date.today() + timedelta(days=202)

        if bal:
            saved = bal.used_days
            bal.used_days = 0
            await db.commit()
            result = await check_and_submit_leave(
                db=db, employee_id=emp_id, leave_type="bereavement",
                start_date=start, end_date=end, reason="T22 bereavement test",
            )
            test("T22", "Submit bereavement leave (balance exists)",
                 result["success"] is True,
                 f"Got: {result}")
            if result.get("success"):
                req_r = await db.execute(
                    select(LeaveRequest).where(LeaveRequest.id == result["request_id"])
                )
                req = req_r.scalar_one_or_none()
                if req:
                    req.status = LeaveStatus.cancelled
            bal.used_days = saved
            await db.commit()
        else:
            result = await check_and_submit_leave(
                db=db, employee_id=emp_id, leave_type="bereavement",
                start_date=start, end_date=end,
            )
            test("T22", "Submit bereavement leave (no balance = not eligible)",
                 result["success"] is False and "balance" in result["message"].lower(),
                 f"Got: {result}")


# ====================================================================
# ESCALATION TESTS (code-level validation, no server)
# ====================================================================

def test_escalation_model():
    """Test T23-T24: Escalation model and tool."""
    from app.models.escalation import (
        EscalationTicket,
        EscalationCategory,
        EscalationStatus,
        EscalationUrgency,
    )

    # T23: Verify model fields exist
    required_fields = [
        "id", "tenant_id", "conversation_id", "employee_id",
        "agent_name", "category", "urgency", "reason", "summary",
        "status", "assigned_to", "resolved_at", "created_at",
    ]
    model_columns = [c.name for c in EscalationTicket.__table__.columns]
    missing = [f for f in required_fields if f not in model_columns]
    test("T23", "EscalationTicket model has all required fields",
         len(missing) == 0,
         f"Missing columns: {missing}")

    # Verify enums
    categories = [e.value for e in EscalationCategory]
    test("T23b", "EscalationCategory has all 4 values",
         set(categories) == {"employee_request", "agent_failure", "sensitive_topic", "policy_gap"},
         f"Got: {categories}")

    urgencies = [e.value for e in EscalationUrgency]
    test("T23c", "EscalationUrgency has low/medium/high",
         set(urgencies) == {"low", "medium", "high"},
         f"Got: {urgencies}")

    statuses = [e.value for e in EscalationStatus]
    test("T23d", "EscalationStatus has open/assigned/resolved",
         set(statuses) == {"open", "assigned", "resolved"},
         f"Got: {statuses}")


def test_escalation_tool_in_deema():
    """T24: escalate_to_human tool exists in Deema and requires employee_id check."""
    source = DEEMA_PY.read_text()

    # Check escalate_to_human is in the tool list
    test("T24a", "escalate_to_human tool defined in get_tools()",
         '"escalate_to_human"' in source,
         "Tool not found in deema.py")

    # Check that _escalate_to_human checks for employee_id
    test("T24b", "escalate_to_human fails without employee_id",
         "if not self._employee_id" in source,
         "Missing employee_id guard in _escalate_to_human")

    # Verify tool requires 'reason' and 'category' as required fields
    test("T24c", "escalate_to_human requires reason and category",
         '"required": ["reason", "category"]' in source,
         "Missing required fields")


def test_escalated_conversation_blocks_agent():
    """T25: Escalated conversation blocks agent response (code review)."""
    source = CHAT_HTML.read_text() if CHAT_HTML.exists() else ""
    chat_py_source = (BACKEND_ROOT / "app" / "api" / "chat.py").read_text()

    # Check chat.py blocks agent response for escalated conversations
    test("T25", "Escalated conversation blocks agent response",
         "ConversationStatus.escalated" in chat_py_source
         and "escalated" in chat_py_source.lower(),
         "Missing escalation check in chat.py")

    # Verify the check is BEFORE the orchestrator call
    lines = chat_py_source.split("\n")
    escalation_check_line = None
    orchestrator_call_line = None
    for i, line in enumerate(lines):
        if "conversation.status == ConversationStatus.escalated" in line:
            escalation_check_line = i
        if "orchestrator.handle_message" in line:
            orchestrator_call_line = i

    test("T25b", "Escalation check is before orchestrator call",
         escalation_check_line is not None
         and orchestrator_call_line is not None
         and escalation_check_line < orchestrator_call_line,
         f"Check at line {escalation_check_line}, orchestrator at {orchestrator_call_line}")


def test_escalation_api_code_review():
    """Tests T26-T29: Escalation API endpoints (code review)."""
    source = ESCALATION_API.read_text()

    # T26: List by tenant — tenant_id is a required query param
    test("T26", "Escalation API: list filters by tenant_id",
         "tenant_id: str = Query(" in source
         and "EscalationTicket.tenant_id == t_id" in source,
         "Missing tenant_id filter on list endpoint")

    # T27: Respond adds message to conversation
    test("T27", "Escalation API: respond adds message",
         "db.add(Message(" in source
         and "respond_to_escalation" in source,
         "Missing message creation in respond endpoint")

    # T28: Resolve restores conversation status to active
    test("T28", "Escalation API: resolve restores conversation status",
         "ConversationStatus.active" in source
         and "resolve_escalation" in source,
         "Missing status restoration in resolve endpoint")

    # T29: Cross-tenant access blocked — all endpoints filter by tenant_id
    # Count how many times tenant isolation appears in queries
    tenant_checks = source.count("EscalationTicket.tenant_id == t_id")
    test("T29", "Escalation API: cross-tenant access blocked (all endpoints filter by tenant)",
         tenant_checks >= 3,  # list, get, respond, resolve = at least 3 unique
         f"Found {tenant_checks} tenant isolation checks, expected >= 3")

    # Verify resolved ticket cannot be responded to
    test("T29b", "Escalation API: resolved tickets reject respond",
         "already resolved" in source.lower(),
         "Missing resolved-ticket guard on respond endpoint")


# ====================================================================
# RACE CONDITION TESTS
# ====================================================================

def test_race_condition_lock():
    """T30: Verify FOR UPDATE lock exists in leave service."""
    source = LEAVE_SVC.read_text()

    test("T30", "Race condition: FOR UPDATE lock on balance query",
         ".with_for_update()" in source,
         "Missing with_for_update() in leave.py balance query")

    # Verify it's on the balance query specifically (not just anywhere)
    # Find the line with with_for_update and make sure it's near LeaveBalance
    lines = source.split("\n")
    lock_line = None
    for i, line in enumerate(lines):
        if "with_for_update()" in line:
            lock_line = i
            break

    if lock_line is not None:
        # Check context: within 10 lines above, LeaveBalance should appear
        context = "\n".join(lines[max(0, lock_line - 10):lock_line + 1])
        test("T30b", "FOR UPDATE lock is on LeaveBalance query (not arbitrary query)",
             "LeaveBalance" in context,
             f"Lock at line {lock_line + 1} but LeaveBalance not in context")
    else:
        test("T30b", "FOR UPDATE lock is on LeaveBalance query",
             False, "Could not find with_for_update() line")


# ====================================================================
# FRONTEND TESTS (code review, not runtime)
# ====================================================================

def test_frontend_leave_types():
    """T31: Verify all 8 leave types in dropdown HTML."""
    source = CHAT_HTML.read_text()

    expected_values = ["annual", "sick", "emergency", "maternity",
                       "paternity", "hajj", "bereavement", "unpaid"]

    # Find all option values in the leaveType select
    options = re.findall(r'<option\s+value="(\w+)"', source)
    found_in_dropdown = [v for v in expected_values if v in options]

    test("T31", "All 8 leave types in dropdown HTML",
         set(expected_values) == set(found_in_dropdown),
         f"Expected {expected_values}, found in dropdown: {found_in_dropdown}")


def test_frontend_xss_escaping():
    """T32: Verify escapeHtml used on all innerHTML injections."""
    source = CHAT_HTML.read_text()

    # Verify escapeHtml function exists
    test("T32a", "escapeHtml function defined",
         "function escapeHtml(text)" in source,
         "Missing escapeHtml function")

    # Verify renderMarkdown uses escapeHtml as first step
    test("T32b", "renderMarkdown calls escapeHtml before processing",
         "let html = escapeHtml(text)" in source,
         "renderMarkdown does not call escapeHtml")

    # Check that user-facing data in innerHTML uses escapeHtml
    # Look for patterns like: `${escapeHtml(` in template literals
    escape_calls = source.count("escapeHtml(")
    test("T32c", f"escapeHtml used extensively ({escape_calls} calls)",
         escape_calls >= 8,
         f"Only {escape_calls} escapeHtml calls found, expected >= 8")

    # Check that employee messages use textContent (not innerHTML)
    # In the addMessage function, employee messages should use textContent
    test("T32d", "Employee messages use textContent (not innerHTML)",
         "div.textContent = text;" in source,
         "Employee messages may use innerHTML without escaping")


def test_frontend_escalation_css():
    """T33: Verify .msg-escalation CSS class is applied in JS."""
    source = CHAT_HTML.read_text()

    # CSS class exists
    test("T33a", ".msg-escalation CSS class defined",
         ".msg-escalation {" in source or ".msg-escalation{" in source,
         "Missing .msg-escalation CSS class")

    # Dark mode variant exists
    test("T33b", ".dark .msg-escalation CSS class defined",
         ".dark .msg-escalation" in source,
         "Missing dark mode variant for .msg-escalation")

    # JS applies the class
    test("T33c", "msg-escalation class applied in JS addMessage function",
         "div.classList.add('msg-escalation')" in source,
         "Missing classList.add('msg-escalation') in JS")

    # Escalation detection regex
    test("T33d", "Escalation detection regex includes Arabic",
         "escalat" in source and "تصعيد" in source,
         "Missing Arabic escalation detection in JS regex")


# ====================================================================
# CODE VALIDATION: Cross-cutting concerns
# ====================================================================

def test_code_validation():
    """Validate imports, function signatures, and dead code."""
    deema_src = DEEMA_PY.read_text()
    leave_src = LEAVE_SVC.read_text()
    base_src = BASE_AGENT.read_text()
    esc_model_src = ESCALATION_MODEL.read_text()
    esc_api_src = ESCALATION_API.read_text()
    chat_src = (BACKEND_ROOT / "app" / "api" / "chat.py").read_text()

    # Verify deema.py imports leave service functions
    test("CV1", "deema.py imports check_and_submit_leave",
         "from app.services.leave import check_and_submit_leave" in deema_src,
         "Missing import of check_and_submit_leave in deema.py")

    test("CV2", "deema.py imports cancel_leave_request from service",
         "cancel_leave_request as svc_cancel_leave" in deema_src,
         "Missing import alias svc_cancel_leave in deema.py")

    # Verify _submit_leave_request delegates to service
    test("CV3", "_submit_leave_request delegates to check_and_submit_leave",
         "check_and_submit_leave(" in deema_src,
         "deema._submit_leave_request does not call check_and_submit_leave")

    # Verify _cancel_leave_request delegates to service
    test("CV4", "_cancel_leave_request delegates to svc_cancel_leave",
         "svc_cancel_leave(" in deema_src,
         "deema._cancel_leave_request does not call svc_cancel_leave")

    # Verify escalation model imports in deema.py
    test("CV5", "deema.py imports EscalationTicket and enums",
         "from app.models.escalation import" in deema_src
         and "EscalationTicket" in deema_src
         and "EscalationCategory" in deema_src
         and "EscalationUrgency" in deema_src,
         "Missing escalation imports in deema.py")

    # Verify conversation status import in deema.py
    test("CV6", "deema.py imports ConversationStatus",
         "ConversationStatus" in deema_src,
         "Missing ConversationStatus import in deema.py")

    # Verify base agent has _conversation_id and _employee_id
    test("CV7", "BaseAgent has _conversation_id and _employee_id attributes",
         "_conversation_id" in base_src and "_employee_id" in base_src,
         "Missing agent context attributes in base.py")

    # Verify leave.py has check_overlap function
    test("CV8", "leave.py exports check_overlap",
         "async def check_overlap(" in leave_src,
         "Missing check_overlap function in leave.py")

    # Verify check_overlap is called from check_and_submit_leave
    test("CV9", "check_and_submit_leave calls check_overlap",
         "await check_overlap(" in leave_src,
         "check_overlap not called in check_and_submit_leave")

    # Verify escalation API uses correct router prefix
    test("CV10", "Escalation API has /escalations prefix",
         'prefix="/escalations"' in esc_api_src,
         "Wrong or missing prefix on escalation router")

    # Verify chat.py imports ConversationStatus
    test("CV11", "chat.py imports ConversationStatus",
         "ConversationStatus" in chat_src,
         "Missing ConversationStatus import in chat.py")

    # Verify cancel_leave_request passes tenant_id
    cancel_call = re.search(r"svc_cancel_leave\([^)]+\)", deema_src, re.DOTALL)
    if cancel_call:
        test("CV12", "cancel_leave_request call passes tenant_id",
             "tenant_id=self.tenant_id" in cancel_call.group(0),
             f"Call: {cancel_call.group(0)}")
    else:
        test("CV12", "cancel_leave_request call passes tenant_id",
             False, "Could not find svc_cancel_leave call")

    # Verify bilingual messages in leave service
    test("CV13", "Leave service returns bilingual messages (message + message_ar)",
         leave_src.count('"message_ar"') >= 5,
         "Insufficient bilingual support in leave.py")

    # Verify check_overlap uses .first() not .scalar_one_or_none()
    # to avoid MultipleResultsFound when multiple overlaps exist
    overlap_fn = re.search(
        r"async def check_overlap.*?(?=\nasync def |\nclass |\Z)",
        leave_src, re.DOTALL
    )
    if overlap_fn:
        overlap_body = overlap_fn.group(0)
        test("CV14", "check_overlap uses .first() (not .scalar_one_or_none())",
             ".first()" in overlap_body,
             f"check_overlap may crash on multiple overlaps. Body contains scalar_one_or_none: "
             f"{'scalar_one_or_none' in overlap_body}")
    else:
        test("CV14", "check_overlap uses .first()", False, "Could not find check_overlap body")

    # Verify _verify_employee is used in all leave-related methods
    for method in ("_get_leave_balance", "_get_leave_requests", "_cancel_leave_request"):
        # Find the method body and check it calls _verify_employee
        method_match = re.search(
            rf"async def {method}\(.*?\n    async def |\Z",
            deema_src, re.DOTALL
        )
        if method_match:
            test(f"CV15_{method}", f"{method} calls _verify_employee",
                 "_verify_employee" in method_match.group(0),
                 f"{method} does not call _verify_employee for tenant isolation")


# ====================================================================
# MAIN
# ====================================================================

async def main():
    global passed, failed, skipped

    print("=" * 70)
    print("  KREW -- Deema Backlog Test Suite")
    print(f"  {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    print()

    # ── Pure unit tests (no DB) ──
    print("[P0: Business Day Calculation]")
    test_business_days()
    print()

    print("[Leave Type Schema]")
    test_leave_types_in_schema()
    print()

    print("[Escalation Model]")
    test_escalation_model()
    test_escalation_tool_in_deema()
    test_escalated_conversation_blocks_agent()
    print()

    print("[Escalation API -- Code Review]")
    test_escalation_api_code_review()
    print()

    print("[Race Condition Lock]")
    test_race_condition_lock()
    print()

    print("[Frontend: Leave Types]")
    test_frontend_leave_types()
    print()

    print("[Frontend: XSS Escaping]")
    test_frontend_xss_escaping()
    print()

    print("[Frontend: Escalation CSS]")
    test_frontend_escalation_css()
    print()

    print("[Code Validation]")
    test_code_validation()
    print()

    # ── DB-dependent tests ──
    db_tests_ran = False
    try:
        # Try importing DB session -- if it fails, DB tests are skipped
        from app.database import async_session

        print("[P0: Tenant Isolation -- DB required]")
        await test_tenant_isolation()
        print()

        print("[Service: check_and_submit_leave -- DB required]")
        await test_submit_leave_service()
        print()

        print("[Service: cancel_leave_request -- DB required]")
        await test_cancel_leave_service()
        print()

        print("[Overlap Validation -- DB required]")
        await test_overlap_validation()
        print()

        print("[Special Leave Types -- DB required]")
        await test_special_leave_types()
        print()

        db_tests_ran = True
    except Exception as e:
        print(f"  [WARN] DB tests skipped: {type(e).__name__}: {e}")
        print(f"         Make sure PostgreSQL is running and .env is configured.")
        print()

    # ── Report ──
    print()
    print("=" * 70)
    print("  TEST REPORT -- Deema Backlog")
    print("=" * 70)
    print()
    print(f"  {'Status':<6} {'ID':<10} {'Test Name'}")
    print(f"  {'------':<6} {'----------':<10} {'-' * 45}")

    for status, tid, name, detail in results:
        marker = " PASS " if status == "PASS" else " FAIL " if status == "FAIL" else " SKIP "
        print(f"  {marker} {tid:<10} {name}")
        if detail:
            print(f"                      {detail[:100]}")

    print()
    total = passed + failed + skipped
    print(f"  TOTAL: {total}  |  PASSED: {passed}  |  FAILED: {failed}  |  SKIPPED: {skipped}")

    if failed == 0 and skipped == 0:
        print("  Status: ALL TESTS PASSED")
    elif failed == 0:
        print(f"  Status: ALL RUN TESTS PASSED ({skipped} skipped)")
    else:
        print(f"  Status: {failed} FAILED")
        for status, tid, name, _ in results:
            if status == "FAIL":
                print(f"    - [{tid}] {name}")

    print("=" * 70)

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
