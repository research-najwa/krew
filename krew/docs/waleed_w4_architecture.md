# Waleed W4 -- UX Polish & Demo Readiness: Technical Architecture

**Author**: Faisal (System Architect)
**Date**: 2026-03-24
**Status**: Design Review
**Sprint**: W4 (final sprint before investor demo)

---

## 1. Proactive Context (`get_proactive_context` override)

### 1.1 Design Decision: Manager Detection

Use the existing `_verify_is_manager(employee_id)` method already in `waleed.py` (line 416). It queries `SELECT id FROM employees WHERE manager_id = :id AND status = 'active' LIMIT 1`. Cheap indexed FK lookup. No `is_manager` boolean column — the source of truth is the relationship graph.

### 1.2 Design Decision: Service Instantiation

Instantiate inline: `ManagerService(self.db, self.tenant_id, emp_uuid)`. The constructor does zero I/O (just stores references), identical to what every manager tool already does.

### 1.3 Design Decision: Error Handling

Yes — wrap the entire body in `try/except Exception`, log a warning, return `None`. Proactive context is enrichment, not critical path. Matches Deema's pattern.

### 1.4 Implementation Outline

```python
async def get_proactive_context(self, employee_id: str) -> str | None:
    if not employee_id:
        return None
    try:
        emp_uuid = UUID(employee_id)
    except ValueError:
        return None

    context_parts: list[str] = []
    try:
        is_manager = await self._verify_is_manager(emp_uuid)
        if is_manager:
            await self._build_manager_context(emp_uuid, context_parts)
        else:
            await self._build_employee_context(emp_uuid, context_parts)
    except Exception as exc:
        logger.warning("Waleed proactive context failed for %s: %s", employee_id, exc)
        return None

    if not context_parts:
        return None
    return "\n\nProactive context for this employee:\n" + "\n".join(f"- {p}" for p in context_parts)
```

**Manager Context Builder** — three queries, all indexed:

```python
async def _build_manager_context(self, emp_uuid, parts):
    svc = ManagerService(self.db, self.tenant_id, emp_uuid)

    # 1. Pending leave approvals
    pending = await svc.get_pending_approvals()
    if pending:
        parts.append(f"This manager has {len(pending)} pending leave approval(s). Proactively mention this.")

    # 2. Overdue onboarding steps
    onb_svc = OnboardingService(self.db, self.tenant_id)
    overdue = await onb_svc.get_overdue_steps(requesting_employee_id=emp_uuid)
    if overdue:
        parts.append(f"There are {len(overdue)} overdue onboarding step(s). Suggest reviewing the dashboard.")

    # 3. New hires in last 30 days
    from datetime import date, timedelta
    cutoff = date.today() - timedelta(days=30)
    result = await self.db.execute(
        select(Employee.first_name, Employee.last_name, Employee.hire_date)
        .where(
            Employee.tenant_id == self.tenant_id,
            Employee.manager_id == emp_uuid,
            Employee.status == EmployeeStatus.active,
            Employee.hire_date >= cutoff,
        )
        .order_by(Employee.hire_date.desc())
    )
    new_hires = result.all()
    if new_hires:
        names = [f"{r.first_name} {r.last_name}" for r in new_hires]
        parts.append(f"{len(new_hires)} new team member(s) in last 30 days: {', '.join(names)}. Offer to check onboarding.")
```

**Employee Context Builder**:

```python
async def _build_employee_context(self, emp_uuid, parts):
    onb_svc = OnboardingService(self.db, self.tenant_id)
    onboarding = await onb_svc.get_employee_onboarding(emp_uuid)
    if not onboarding:
        return
    progress = onboarding["progress_pct"]
    total = onboarding["total_steps"]
    completed = onboarding["completed_steps"]
    overdue_count = sum(1 for s in onboarding["steps"] if s["is_overdue"])

    parts.append(f"Active onboarding: {completed}/{total} steps ({progress}%).")
    if overdue_count > 0:
        parts.append(f"{overdue_count} step(s) overdue. Gently remind and offer to help.")
    elif progress < 100:
        parts.append("All remaining steps on schedule. Encourage them.")
    if progress == 100:
        parts.append("Onboarding fully complete! Congratulate them.")
```

---

## 2. Agent Handoff UX

### 2.1 Mechanism: Instance Attributes (Selected)

Rejected: changing `respond()` signature (breaks all agents) or checking history (fragile).

Selected: Orchestrator sets instance attributes on agent before `respond()`.

### 2.2 Orchestrator Changes (+6 lines in handle_message)

```python
is_handoff = current_agent is not None and current_agent != agent_name
is_first_message = current_agent is None and len(conversation_history) == 0
agent._handoff_from = current_agent if is_handoff else None
agent._is_first_message = is_first_message
```

### 2.3 Base Agent Defaults (+2 lines in __init__)

```python
self._handoff_from: str | None = None
self._is_first_message: bool = False
```

### 2.4 Waleed System Prompt Override

```python
def get_system_prompt(self, employee_name, employee_id, language="ar"):
    base_prompt = super().get_system_prompt(employee_name, employee_id, language)
    handoff_from = getattr(self, "_handoff_from", None)
    is_first = getattr(self, "_is_first_message", False)

    if handoff_from:
        agent_display = {"deema": "ديمة", "mohammad": "محمد", "yara": "يارا", "norah": "نورة", "sarah": "سارة"}
        from_name = agent_display.get(handoff_from, handoff_from)
        base_prompt += (
            f"\n\nIMPORTANT — Agent handoff: Transferred from {from_name}. "
            "Introduce yourself briefly then address their request directly."
        )
    elif is_first:
        base_prompt += "\n\nNew conversation. Greet warmly and introduce yourself briefly."
    return base_prompt
```

---

## 3. Demo Scripts

### Flow A — Manager Dashboard (Ahmed, 6 turns)

1. "السلام عليكم" → Proactive context: pending approvals, overdue steps, new hires (NO tools called)
2. "وريني طلبات الإجازة" → view_pending_approvals
3. "وافق على إجازة فاطمة" → search_employee + approve_leave
4. "وش الوضع في أبريل؟" → get_team_leave_calendar
5. "كم عدد فريقي وكم نسبة السعودة؟" → get_team_headcount
6. "كيف تسير التهيئة؟" → get_onboarding_dashboard

### Flow B — New Hire Journey (Rayan, 5 turns)

1. "مرحبا" → Proactive context: onboarding 3/7, 1 overdue (NO tools called)
2. "وريني القائمة كاملة" → get_onboarding_checklist
3. "خلصت التدريب الأمني" → complete_onboarding_step
4. "كم باقي علي؟" → get_onboarding_checklist
5. "مين مديري؟" → get_new_hire_info

---

## 4. Files to Modify

| File | Changes | Lines |
|------|---------|-------|
| `backend/app/agents/waleed.py` | proactive context + system prompt override | ~80 |
| `backend/app/agents/orchestrator.py` | handoff flags | ~6 |
| `backend/app/agents/base.py` | default attributes | ~2 |

No migrations needed. All application-level code.
