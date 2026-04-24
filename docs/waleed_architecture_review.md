# Waleed Agent — Architecture Review & Security Remediation

**Author:** Faisal (System Architect)
**Date:** 2026-03-24
**Inputs:** Tariq's sprint plan (`docs/waleed_sprint_plan.md`), risk register items R1/R2/R5
**Audience:** Rania (Dev), Zaid (Red Team), Layla (QA)
**Status:** Ready for Implementation

---

## 1. Risk Assessment Confirmation

Tariq identified three critical issues. All three confirmed after code review, plus one additional finding.

### Risk R1 + R5: Onboarding Tools Have No Ownership Checks (CONFIRMED — HIGH)

**Affected tools (5):**

| Tool | Current Check | Gap |
|------|---------------|-----|
| `get_onboarding_checklist` | None | Any employee can view any other employee's onboarding |
| `complete_onboarding_step` | None | Any employee can mark any step complete for any assignment |
| `assign_onboarding` | None | Any employee can assign onboarding to any other employee |
| `send_checkin` | None | Any employee can send check-in notifications to any employee |
| `get_new_hire_info` | None | Any employee can view any new hire's profile and onboarding status |

**Contrast with manager tools (6):** `view_team`, `view_pending_approvals`, `approve_leave`, `reject_leave`, `get_team_leave_calendar`, `get_team_headcount` — all correctly enforce `str(employee_id) != str(self._employee_id)`.

**Dashboard tools (2):** `get_onboarding_dashboard` and `get_overdue_onboarding_steps` return tenant-wide data. Acceptable for MVP, should be role-gated post-MVP.

### Risk R5 Detail: `complete_onboarding_step` employee_id Misuse (CONFIRMED — HIGH)

The `employee_id` parameter is passed to `OnboardingService.complete_step()` as `completed_by` only — never validated against assignment ownership. Employee A can complete steps on Employee B's onboarding.

### Risk R2: "headcount" Keyword Routing Overlap (CONFIRMED — MEDIUM)

`"headcount"` is in Norah's keywords but `get_team_headcount` lives in Waleed. The sticky routing logic makes it worse — even an active Waleed conversation bounces to Norah on "headcount."

### Additional Finding: Attack Chain via `search_employee` (MEDIUM)

Any employee can: `search_employee("Rayan")` → get UUID → `get_onboarding_checklist(uuid)` → `complete_onboarding_step(uuid, ...)`. Fix belongs in onboarding tools, not search.

---

## 2. Ownership Policy for Onboarding Tools

| Tool | Self | Manager | HR (post-MVP) | Other |
|------|------|---------|---------------|-------|
| `get_onboarding_checklist` | ALLOW | ALLOW | ALLOW | DENY |
| `complete_onboarding_step` | ALLOW | ALLOW | ALLOW | DENY |
| `get_new_hire_info` | ALLOW | ALLOW | ALLOW | DENY |
| `send_checkin` | DENY | ALLOW | ALLOW | DENY |
| `assign_onboarding` | DENY | ALLOW | ALLOW | DENY |
| `get_onboarding_dashboard` | Own data | Own reports | Tenant-wide | DENY |
| `get_overdue_onboarding_steps` | Own data | Own reports | Tenant-wide | DENY |

---

## 3. Fix Recommendations

### Fix 1: Add `_verify_onboarding_access` Helper (P0)

```python
async def _verify_onboarding_access(self, target_employee_id: UUID) -> bool:
    """Check if current user can access target employee's onboarding.
    Returns True if self-access or manager of target.
    """
    if not self._employee_id:
        return False
    current_id = str(self._employee_id)
    target_id = str(target_employee_id)
    # Self-access
    if current_id == target_id:
        return True
    # Manager access
    result = await self.db.execute(
        select(Employee.manager_id).where(
            Employee.id == target_employee_id,
            Employee.tenant_id == self.tenant_id,
            Employee.status == EmployeeStatus.active,
        )
    )
    manager_id = result.scalar_one_or_none()
    return manager_id is not None and str(manager_id) == current_id
```

### Fix 2: Apply Access Checks to Onboarding Tool Dispatches (P0)

For `get_onboarding_checklist`, `get_new_hire_info`, `complete_onboarding_step` — self or manager:
```python
elif tool_name == "get_onboarding_checklist":
    employee_id = UUID(tool_input["employee_id"])
    if not await self._verify_onboarding_access(employee_id):
        return self._ownership_error()
    return await self._get_onboarding_checklist(employee_id)
```

For `send_checkin`, `assign_onboarding` — manager only (deny self-service).

### Fix 3: Validate Assignment Ownership in Service Layer (P0)

Defense-in-depth: add `employee_id` param to `OnboardingService.complete_step()` and filter by it.

### Fix 4: Resolve "headcount" Routing Keyword Conflict (P0)

Move `"headcount"` from Norah to Waleed. Add `"عدد الموظفين"`. Remove from Norah entirely.

### Fix 5: Scope Dashboard/Overdue Tools to Caller's Visibility (P1)

Add `requesting_employee_id` param to `get_onboarding_dashboard()` and `get_overdue_steps()`. Filter to show only own data + own reports.

### Fix 6: UUID Validation at Dispatch Boundary (P1)

Validate all UUID fields at top of `handle_tool_call` with friendly bilingual error.

### Fix 7: Cache `_verify_is_manager` per Turn (P1)

Avoid repeated DB queries when Claude calls multiple manager tools in one turn.

### Fix 8: Keyword Uniqueness Validation (P1)

Add startup assertion that no keyword appears in multiple agents' lists.

### Fix 9: Structured Audit Logging for Write Operations (P2)

Log `tenant_id`, `actor`, `target`, `action` for all state-changing operations.

---

## 4. Implementation Summary for Rania

| Priority | File | Change | Effort |
|----------|------|--------|--------|
| P0 | `waleed.py` | Add `_verify_onboarding_access()` helper | 30 min |
| P0 | `waleed.py` | Add ownership checks to 5 onboarding tool dispatches | 45 min |
| P0 | `onboarding.py` | Add `employee_id` param to `complete_step()` | 15 min |
| P0 | `orchestrator.py` | Move "headcount" to Waleed, add "عدد الموظفين" | 5 min |
| P1 | `waleed.py` | UUID validation at top of `handle_tool_call` | 15 min |
| P1 | `waleed.py` | Cache `_verify_is_manager` per turn | 15 min |
| P1 | `onboarding.py` | Scope dashboard/overdue to caller visibility | 30 min |
| P1 | `orchestrator.py` | Keyword uniqueness validation at module load | 10 min |
| P2 | `waleed.py` | Structured audit logging | 15 min |

**Total: ~3 hours**

---

## 5. Open Questions for CTO

1. **HR Role field:** No `role`/`is_hr` on Employee model. Post-MVP: dedicated field or RBAC roles table?
2. **Dashboard scope vs demo data:** Scoping to manager's reports may affect demo showing "5 onboarding assignments" — confirm all 5 are Ahmed's reports.
3. **`search_employee` scope:** Recommend keeping open within tenant (corporate directory pattern).
4. **Keyword uniqueness rule:** Recommend enforcing startup assertion. Adds coordination cost but prevents silent misrouting.
