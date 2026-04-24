"""Role-based visibility & masking for activity_events.

Two functions, no DB calls — pure logic so it's trivial to property-test:
    - can_see(event, viewer) -> bool
    - mask_event(event, viewer_role) -> dict   (safe-to-send representation)

Hard rule: tenant boundary is non-negotiable. A viewer in tenant A can NEVER
see an event from tenant B regardless of role.

Visibility (within the same tenant):
    employee   : only events where subject_employee_id == viewer.id
    manager    : events about self OR a direct report
    hr_manager : events scoped to a department they own AND sensitivity != "confidential"
    chro       : everything in the tenant
    admin      : everything in the tenant
    system     : everything in the tenant
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.models.activity_event import ActivityEvent


# Allowed sensitivity levels (lowest -> highest)
SENSITIVITY_PUBLIC = "public"
SENSITIVITY_NORMAL = "normal"
SENSITIVITY_SENSITIVE = "sensitive"
SENSITIVITY_CONFIDENTIAL = "confidential"
_ALL_SENSITIVITIES = {
    SENSITIVITY_PUBLIC,
    SENSITIVITY_NORMAL,
    SENSITIVITY_SENSITIVE,
    SENSITIVITY_CONFIDENTIAL,
}

# Roles
ROLE_EMPLOYEE = "employee"
ROLE_MANAGER = "manager"
ROLE_HR_MANAGER = "hr_manager"
ROLE_CHRO = "chro"
ROLE_ADMIN = "admin"
ROLE_SYSTEM = "system"

_FULL_ACCESS_ROLES = {ROLE_CHRO, ROLE_ADMIN, ROLE_SYSTEM}


@dataclass
class ViewerContext:
    id: str
    tenant_id: str
    role: str
    direct_report_ids: set[str] = field(default_factory=set)
    scoped_department_ids: set[str] = field(default_factory=set)


def _to_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def can_see(event: ActivityEvent, viewer: ViewerContext) -> bool:
    """Return True iff `viewer` is allowed to know `event` exists."""
    # Hard tenant boundary
    if _to_str(event.tenant_id) != viewer.tenant_id:
        return False

    role = viewer.role

    if role in _FULL_ACCESS_ROLES:
        return True

    subject_emp = _to_str(event.subject_employee_id)
    subject_dept = _to_str(event.subject_department_id)

    if role == ROLE_EMPLOYEE:
        return subject_emp is not None and subject_emp == viewer.id

    if role == ROLE_MANAGER:
        if subject_emp is None:
            return False
        return subject_emp == viewer.id or subject_emp in viewer.direct_report_ids

    if role == ROLE_HR_MANAGER:
        if event.sensitivity == SENSITIVITY_CONFIDENTIAL:
            return False
        if subject_dept is None:
            return False
        return subject_dept in viewer.scoped_department_ids

    # Unknown role: deny by default
    return False


def _round_to_hour(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    rounded = dt.replace(minute=0, second=0, microsecond=0)
    return rounded.isoformat()


def _full_dict(event: ActivityEvent) -> dict:
    return {
        "id": _to_str(event.id),
        "tenant_id": _to_str(event.tenant_id),
        "actor_type": event.actor_type,
        "actor_id": event.actor_id,
        "subject_employee_id": _to_str(event.subject_employee_id),
        "subject_department_id": _to_str(event.subject_department_id),
        "action": event.action,
        "resource_type": event.resource_type,
        "resource_id": event.resource_id,
        "label_en": event.label_en,
        "label_ar": event.label_ar,
        "details": dict(event.details) if event.details else {},
        "sensitivity": event.sensitivity,
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }


def _hr_manager_masked(event: ActivityEvent) -> dict:
    """HR Manager view: see that *something* happened in their dept, but no PII,
    no resource IDs, no monetary amounts, time rounded to the hour.
    """
    details = event.details or {}
    masked_label_en = details.get("label_en_masked")
    masked_label_ar = details.get("label_ar_masked")
    if not masked_label_en:
        masked_label_en = "Action in department"
    if not masked_label_ar:
        masked_label_ar = "إجراء في القسم"

    return {
        "id": _to_str(event.id),
        "actor_id": event.actor_id,
        "actor_type": event.actor_type,
        "action": event.action,
        "resource_type": event.resource_type,
        # resource_id intentionally omitted
        "subject_department_id": _to_str(event.subject_department_id),
        # subject_employee_id intentionally omitted (no individual)
        "label_en": masked_label_en,
        "label_ar": masked_label_ar,
        "sensitivity": event.sensitivity,
        "created_at": _round_to_hour(event.created_at),
    }


def mask_event(event: ActivityEvent, viewer_role: str) -> dict:
    """Return the dict-shape of `event` appropriate for the viewer's role.

    Caller is expected to have already passed `can_see` — this function does
    not re-check tenant or sensitivity.
    """
    if viewer_role in _FULL_ACCESS_ROLES:
        return _full_dict(event)

    if viewer_role == ROLE_HR_MANAGER:
        return _hr_manager_masked(event)

    # employee (self) and manager (self/report) get the full record.
    if viewer_role in (ROLE_EMPLOYEE, ROLE_MANAGER):
        return _full_dict(event)

    # Unknown role: minimal envelope.
    return {
        "id": _to_str(event.id),
        "action": event.action,
        "created_at": _round_to_hour(event.created_at),
    }
