"""Regression test for the FOR UPDATE + aggregate Postgres error in submit_leave_request.

Background
----------
`check_and_submit_leave` previously ran:

    SELECT coalesce(sum(leave_requests.business_days), 0)
    FROM leave_requests
    WHERE ...
    FOR UPDATE

Postgres rejects this with:

    asyncpg.exceptions.FeatureNotSupportedError:
    FOR UPDATE is not allowed with aggregate functions

The fix drops `with_for_update()` from that aggregate. Concurrency is still
correct because the LeaveBalance row for (employee, leave_type, year) is
already locked a few lines above via `with_for_update()`, so any concurrent
submission for the same balance will serialize on that row lock before
reaching the aggregate read.

This test exercises the end-to-end `check_and_submit_leave` path against the
live local DB (same pattern as test_leave_policy_enum_cast.py) to prove the
query shape is accepted by Postgres. It is skipped if the DB is unreachable
or has no employees.
"""
from datetime import date, timedelta

import pytest
from sqlalchemy import and_, func, select

from app.database import async_session, engine

pytestmark = pytest.mark.asyncio


@pytest.mark.asyncio
async def test_submit_leave_request_does_not_use_for_update_with_aggregate():
    """Exercise check_and_submit_leave end-to-end and the raw aggregate query.

    Passing through `check_and_submit_leave` must not trigger
    asyncpg.FeatureNotSupportedError from a `FOR UPDATE` combined with `sum()`.
    """
    from app.models.employee import Employee
    from app.models.leave import LeaveRequest, LeaveStatus, LeaveType
    from app.services.leave import check_and_submit_leave

    try:
        async with async_session() as db:
            emp = (
                await db.execute(select(Employee).limit(1))
            ).scalar_one_or_none()
            if emp is None:
                pytest.skip("No employees in DB — seed data required")

            # --- Path 1: raw aggregate query WITHOUT FOR UPDATE must succeed.
            # This is the exact query shape used in check_and_submit_leave
            # after the fix. If someone re-adds with_for_update() here, Postgres
            # will reject it and this test will fail loudly.
            leave_year = date.today().year
            await db.execute(
                select(func.coalesce(func.sum(LeaveRequest.business_days), 0)).where(
                    and_(
                        LeaveRequest.employee_id == emp.id,
                        LeaveRequest.leave_type == LeaveType.annual,
                        LeaveRequest.status == LeaveStatus.pending,
                        LeaveRequest.start_date <= date(leave_year, 12, 31),
                        LeaveRequest.end_date >= date(leave_year, 1, 1),
                    )
                )
            )

            # --- Path 2: full end-to-end submit_leave_request tool path.
            # We do not care whether the request is accepted or rejected on
            # business grounds (no balance, policy, etc.) — we only care that
            # it does NOT raise asyncpg.FeatureNotSupportedError from the
            # previous `FOR UPDATE + sum()` combination.
            start = date.today() + timedelta(days=30)
            end = start + timedelta(days=2)
            result = await check_and_submit_leave(
                db=db,
                employee_id=emp.id,
                leave_type="annual",  # raw string, like Deema's tool-use JSON
                start_date=start,
                end_date=end,
                reason="regression test: FOR UPDATE + aggregate",
                channel="test",
                agent="test",
                tenant_id=emp.tenant_id,
            )

            # Always a dict with a success key — success/failure doesn't matter,
            # only that the query executed without a Postgres FeatureNotSupported.
            assert isinstance(result, dict)
            assert "success" in result

            # Roll back so we don't pollute the DB with a test leave request.
            await db.rollback()
    except (ConnectionRefusedError, OSError) as e:
        pytest.skip(f"DB not reachable: {e}")
    finally:
        # The project's async engine is module-scoped and its asyncpg
        # connection pool gets attached to whichever event loop first uses
        # it. Dispose it here so the next pytest-asyncio test (which runs
        # in a fresh event loop) can rebuild the pool cleanly. See also
        # test_leave_policy_enum_cast.py for context.
        await engine.dispose()
