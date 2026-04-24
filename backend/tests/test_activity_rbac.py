"""Tests for app.security.activity_rbac.

We don't hit the DB — ActivityEvent is constructed by hand as a lightweight
object. The RBAC functions only read attributes, so this is enough.
"""
from __future__ import annotations

import random
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.security.activity_rbac import (
    ROLE_ADMIN,
    ROLE_CHRO,
    ROLE_EMPLOYEE,
    ROLE_HR_MANAGER,
    ROLE_MANAGER,
    ROLE_SYSTEM,
    SENSITIVITY_CONFIDENTIAL,
    SENSITIVITY_NORMAL,
    SENSITIVITY_PUBLIC,
    SENSITIVITY_SENSITIVE,
    ViewerContext,
    can_see,
    mask_event,
)


# ── Fakes ────────────────────────────────────────────────────────
def make_event(
    *,
    tenant_id: str,
    subject_employee_id: str | None = None,
    subject_department_id: str | None = None,
    sensitivity: str = SENSITIVITY_NORMAL,
    action: str = "leave.submit",
    resource_type: str = "leave_request",
    resource_id: str | None = "res-123",
    actor_type: str = "agent",
    actor_id: str = "deema",
    label_en: str = "Sara submitted a leave request",
    label_ar: str = "قدمت سارة طلب إجازة",
    details: dict | None = None,
    created_at: datetime | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        actor_type=actor_type,
        actor_id=actor_id,
        subject_employee_id=subject_employee_id,
        subject_department_id=subject_department_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        label_en=label_en,
        label_ar=label_ar,
        details=details or {"amount_sar": 1500, "note": "vacation"},
        sensitivity=sensitivity,
        created_at=created_at or datetime(2026, 4, 6, 14, 37, 12, tzinfo=timezone.utc),
    )


TENANT_A = "tenant-aaaa"
TENANT_B = "tenant-bbbb"
DEPT_X = "dept-x"
DEPT_Y = "dept-y"
EMP_ALICE = "emp-alice"
EMP_BOB = "emp-bob"
EMP_CARL = "emp-carl"


# ── Tenant boundary ──────────────────────────────────────────────
@pytest.mark.parametrize("role", [
    ROLE_EMPLOYEE, ROLE_MANAGER, ROLE_HR_MANAGER, ROLE_CHRO, ROLE_ADMIN, ROLE_SYSTEM,
])
def test_cross_tenant_always_denied(role):
    event = make_event(
        tenant_id=TENANT_B,
        subject_employee_id=EMP_ALICE,
        subject_department_id=DEPT_X,
    )
    viewer = ViewerContext(
        id=EMP_ALICE,
        tenant_id=TENANT_A,
        role=role,
        direct_report_ids={EMP_ALICE, EMP_BOB},
        scoped_department_ids={DEPT_X, DEPT_Y},
    )
    assert can_see(event, viewer) is False


# ── Employee ─────────────────────────────────────────────────────
def test_employee_sees_own_event():
    event = make_event(tenant_id=TENANT_A, subject_employee_id=EMP_ALICE)
    viewer = ViewerContext(id=EMP_ALICE, tenant_id=TENANT_A, role=ROLE_EMPLOYEE)
    assert can_see(event, viewer) is True


def test_employee_cannot_see_others():
    event = make_event(tenant_id=TENANT_A, subject_employee_id=EMP_BOB)
    viewer = ViewerContext(id=EMP_ALICE, tenant_id=TENANT_A, role=ROLE_EMPLOYEE)
    assert can_see(event, viewer) is False


def test_employee_cannot_see_dept_only_event():
    event = make_event(tenant_id=TENANT_A, subject_department_id=DEPT_X)
    viewer = ViewerContext(id=EMP_ALICE, tenant_id=TENANT_A, role=ROLE_EMPLOYEE)
    assert can_see(event, viewer) is False


# ── Manager ──────────────────────────────────────────────────────
def test_manager_sees_self():
    event = make_event(tenant_id=TENANT_A, subject_employee_id=EMP_ALICE)
    viewer = ViewerContext(
        id=EMP_ALICE, tenant_id=TENANT_A, role=ROLE_MANAGER,
        direct_report_ids={EMP_BOB},
    )
    assert can_see(event, viewer) is True


def test_manager_sees_direct_report():
    event = make_event(tenant_id=TENANT_A, subject_employee_id=EMP_BOB)
    viewer = ViewerContext(
        id=EMP_ALICE, tenant_id=TENANT_A, role=ROLE_MANAGER,
        direct_report_ids={EMP_BOB},
    )
    assert can_see(event, viewer) is True


def test_manager_blocked_for_non_report():
    event = make_event(tenant_id=TENANT_A, subject_employee_id=EMP_CARL)
    viewer = ViewerContext(
        id=EMP_ALICE, tenant_id=TENANT_A, role=ROLE_MANAGER,
        direct_report_ids={EMP_BOB},
    )
    assert can_see(event, viewer) is False


# ── HR Manager ───────────────────────────────────────────────────
@pytest.mark.parametrize("sensitivity", [SENSITIVITY_PUBLIC, SENSITIVITY_NORMAL, SENSITIVITY_SENSITIVE])
def test_hr_manager_sees_in_scoped_dept(sensitivity):
    event = make_event(
        tenant_id=TENANT_A,
        subject_department_id=DEPT_X,
        sensitivity=sensitivity,
    )
    viewer = ViewerContext(
        id="hr-1", tenant_id=TENANT_A, role=ROLE_HR_MANAGER,
        scoped_department_ids={DEPT_X},
    )
    assert can_see(event, viewer) is True


def test_hr_manager_blocked_on_confidential():
    event = make_event(
        tenant_id=TENANT_A,
        subject_department_id=DEPT_X,
        sensitivity=SENSITIVITY_CONFIDENTIAL,
    )
    viewer = ViewerContext(
        id="hr-1", tenant_id=TENANT_A, role=ROLE_HR_MANAGER,
        scoped_department_ids={DEPT_X},
    )
    assert can_see(event, viewer) is False


def test_hr_manager_blocked_outside_scope():
    event = make_event(tenant_id=TENANT_A, subject_department_id=DEPT_Y)
    viewer = ViewerContext(
        id="hr-1", tenant_id=TENANT_A, role=ROLE_HR_MANAGER,
        scoped_department_ids={DEPT_X},
    )
    assert can_see(event, viewer) is False


# ── CHRO / Admin / System ────────────────────────────────────────
@pytest.mark.parametrize("role", [ROLE_CHRO, ROLE_ADMIN, ROLE_SYSTEM])
@pytest.mark.parametrize("sensitivity", [
    SENSITIVITY_PUBLIC, SENSITIVITY_NORMAL, SENSITIVITY_SENSITIVE, SENSITIVITY_CONFIDENTIAL,
])
def test_full_access_roles_see_everything_in_tenant(role, sensitivity):
    event = make_event(
        tenant_id=TENANT_A,
        subject_employee_id=EMP_ALICE,
        subject_department_id=DEPT_X,
        sensitivity=sensitivity,
    )
    viewer = ViewerContext(id="x", tenant_id=TENANT_A, role=role)
    assert can_see(event, viewer) is True


# ── Masking ──────────────────────────────────────────────────────
def test_chro_gets_full_record():
    event = make_event(tenant_id=TENANT_A, subject_employee_id=EMP_ALICE)
    out = mask_event(event, ROLE_CHRO)
    assert out["resource_id"] == "res-123"
    assert out["label_en"] == "Sara submitted a leave request"
    assert out["details"]["amount_sar"] == 1500


def test_employee_self_gets_full_record():
    event = make_event(tenant_id=TENANT_A, subject_employee_id=EMP_ALICE)
    out = mask_event(event, ROLE_EMPLOYEE)
    assert out["resource_id"] == "res-123"
    assert "details" in out


def test_manager_gets_full_record():
    event = make_event(tenant_id=TENANT_A, subject_employee_id=EMP_BOB)
    out = mask_event(event, ROLE_MANAGER)
    assert out["resource_id"] == "res-123"


def test_hr_manager_masking_strips_pii():
    event = make_event(
        tenant_id=TENANT_A,
        subject_employee_id=EMP_ALICE,
        subject_department_id=DEPT_X,
        sensitivity=SENSITIVITY_NORMAL,
        details={"amount_sar": 9000, "national_id": "1234567890"},
    )
    out = mask_event(event, ROLE_HR_MANAGER)

    # No resource_id leak
    assert "resource_id" not in out
    # No individual identity
    assert "subject_employee_id" not in out
    # Department is preserved
    assert out["subject_department_id"] == DEPT_X
    # No raw details (no amounts, no national_id)
    assert "details" not in out
    flat_values = " ".join(str(v) for v in out.values() if v is not None)
    assert "9000" not in flat_values
    assert "1234567890" not in flat_values
    # Default generic label kicks in (specific name "Sara" should not leak)
    assert "Sara" not in out["label_en"]
    # Time rounded to hour (37 minutes -> 00)
    assert out["created_at"].endswith("14:00:00+00:00")


def test_hr_manager_uses_pre_masked_label_when_provided():
    event = make_event(
        tenant_id=TENANT_A,
        subject_department_id=DEPT_X,
        details={"label_en_masked": "Leave request submitted in Engineering",
                 "label_ar_masked": "تم تقديم طلب إجازة في الهندسة"},
    )
    out = mask_event(event, ROLE_HR_MANAGER)
    assert out["label_en"] == "Leave request submitted in Engineering"
    assert out["label_ar"] == "تم تقديم طلب إجازة في الهندسة"


# ── Property-style: 500 random (event, viewer) pairs ────────────
def test_property_hr_manager_never_leaks_confidential_details():
    rng = random.Random(42)
    sensitivities = [SENSITIVITY_PUBLIC, SENSITIVITY_NORMAL, SENSITIVITY_SENSITIVE, SENSITIVITY_CONFIDENTIAL]
    departments = [DEPT_X, DEPT_Y, "dept-z", "dept-w"]
    employees = [EMP_ALICE, EMP_BOB, EMP_CARL, "emp-dora", "emp-erin"]
    actions = ["leave.submit", "leave.approve", "salary.adjust", "policy.acknowledge", "doc.upload"]
    sensitive_keys = {"national_id", "amount_sar", "iban", "salary"}

    for _ in range(500):
        tenant = rng.choice([TENANT_A, TENANT_B])
        viewer_tenant = rng.choice([TENANT_A, TENANT_B])
        event = make_event(
            tenant_id=tenant,
            subject_employee_id=rng.choice(employees + [None]),
            subject_department_id=rng.choice(departments + [None]),
            sensitivity=rng.choice(sensitivities),
            action=rng.choice(actions),
            details={
                "national_id": f"{rng.randint(1000000000, 9999999999)}",
                "amount_sar": rng.randint(100, 100000),
                "iban": "SA0000000000000000000000",
                "label_en_masked": "Action in department",
                "label_ar_masked": "إجراء في القسم",
            },
        )
        viewer = ViewerContext(
            id=rng.choice(employees),
            tenant_id=viewer_tenant,
            role=ROLE_HR_MANAGER,
            scoped_department_ids=set(rng.sample(departments, k=rng.randint(0, len(departments)))),
        )

        if not can_see(event, viewer):
            continue

        # Confidential events must never reach an HR Manager via can_see.
        assert event.sensitivity != SENSITIVITY_CONFIDENTIAL
        # And must always be in-tenant.
        assert event.tenant_id == viewer.tenant_id

        masked = mask_event(event, ROLE_HR_MANAGER)

        # No sensitive keys may surface as keys in the masked dict.
        assert sensitive_keys.isdisjoint(masked.keys())
        # No raw details key
        assert "details" not in masked
        # No resource_id
        assert "resource_id" not in masked
        # No individual employee id
        assert "subject_employee_id" not in masked

        # Belt-and-braces: stringify and ensure raw sensitive values don't leak.
        blob = " ".join(str(v) for v in masked.values() if v is not None)
        assert event.details["national_id"] not in blob
        assert str(event.details["amount_sar"]) not in blob
        assert "SA0000000000000000000000" not in blob


def test_property_cross_tenant_is_unconditional():
    rng = random.Random(123)
    roles = [ROLE_EMPLOYEE, ROLE_MANAGER, ROLE_HR_MANAGER, ROLE_CHRO, ROLE_ADMIN, ROLE_SYSTEM]
    for _ in range(200):
        event = make_event(
            tenant_id=TENANT_B,
            subject_employee_id=rng.choice([EMP_ALICE, EMP_BOB, None]),
            subject_department_id=rng.choice([DEPT_X, DEPT_Y, None]),
            sensitivity=rng.choice([SENSITIVITY_PUBLIC, SENSITIVITY_NORMAL, SENSITIVITY_SENSITIVE, SENSITIVITY_CONFIDENTIAL]),
        )
        viewer = ViewerContext(
            id=rng.choice([EMP_ALICE, EMP_BOB, "hr-1", "chro-1"]),
            tenant_id=TENANT_A,  # always different from event
            role=rng.choice(roles),
            direct_report_ids={EMP_ALICE, EMP_BOB},
            scoped_department_ids={DEPT_X, DEPT_Y},
        )
        assert can_see(event, viewer) is False
