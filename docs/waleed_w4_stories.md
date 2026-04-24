# Sprint W4: UX Polish & Demo Readiness -- Detailed User Stories

**Agent:** Waleed (وليد) -- Onboarding & Manager Agent
**Sprint:** W4 (Final sprint before investor demo)
**Product Owner:** Tariq
**Created:** 2026-03-25
**Goal:** Every interaction with Waleed must feel polished, bilingual, and demo-ready.

---

## W4-01: Proactive Context on Conversation Open (P0)

> As a manager, I want Waleed to greet me with pending items summary.
> As a new hire, I want Waleed to greet me with my onboarding progress.

**Acceptance Criteria:**

Manager path (Ahmed):
- [ ] Proactive context returns pending leave approval count
- [ ] Proactive context returns overdue onboarding step count
- [ ] Proactive context mentions new hires in last 30 days
- [ ] Greeting in Arabic is natural and warm
- [ ] DB errors return None (never crash)

New hire path (Rayan):
- [ ] Proactive context returns onboarding progress (X/Y steps)
- [ ] Proactive context mentions overdue steps
- [ ] No-context path returns None for regular employees

**Assigned to:** Rania (Dev), Huda (test)
**Status:** DONE ✅

---

## W4-02: Empty State Messages (P0)

> As a user, I want friendly bilingual messages when there is no data.

**Acceptance Criteria:**

- [ ] view_team (not a manager): bilingual error with helpful suggestion
- [ ] view_pending_approvals (0 pending): warm "all clear" message
- [ ] get_onboarding_checklist (no assignment): explains why and offers help
- [ ] get_onboarding_dashboard (no in-progress): suggests assigning onboarding
- [ ] get_overdue_onboarding_steps (none overdue): celebratory message
- [ ] get_team_leave_calendar (no leaves): clear "no leaves in range"
- [ ] search_employee (no results): suggests re-checking name/number

**Assigned to:** Rania (Dev), Huda (test)
**Status:** DONE ✅ (all tool responses already have bilingual messages)

---

## W4-03: Error Message Polish (P0)

> As a user, I want all errors to explain what went wrong with next steps, in both languages.

**Acceptance Criteria:**

- [ ] UUID validation: bilingual error, Waleed suggests using name instead
- [ ] Ownership denied: bilingual, suggests contacting manager/HR
- [ ] Not a manager: bilingual, suggests contacting HR if error
- [ ] Employee not found: bilingual, suggests re-checking name
- [ ] Step not found: bilingual, offers to show checklist
- [ ] Date format: bilingual, shows correct format example
- [ ] Generic tool failure: bilingual, offers to retry or escalate
- [ ] Raw JSON is NEVER visible in chat

**Assigned to:** Rania (Dev), Huda (test)
**Status:** DONE ✅ (all error paths have error/error_ar)

---

## W4-04: Agent Handoff UX (P1)

> As a user, I want smooth transitions between Deema and Waleed.

**Acceptance Criteria:**

- [ ] Waleed introduces himself on handoff from Deema (one sentence max)
- [ ] Deema introduces herself on handoff from Waleed
- [ ] No re-introduction on subsequent messages with same agent
- [ ] Handoff hint injected via system prompt (orchestrator sets _handoff_from)
- [ ] is_first_message flag triggers greeting on new conversations

**Assigned to:** Faisal (Architect), Rania (Dev), Huda (test)
**Status:** DONE ✅

---

## W4-05: Demo Script -- Investor Presentation (P0)

> As the CTO, I want pre-built conversation flows for a 5-7 minute investor demo.

### Scene 1: New Hire Onboarding (Rayan, Arabic, 2 min)
1. "مرحبا وليد" → Proactive greeting with onboarding progress
2. "وش باقي عليّ في التهيئة؟" → get_onboarding_checklist
3. "خلصت قراءة السياسات" → complete_onboarding_step
4. "وش هي التأمينات الاجتماعية؟" → Saudi domain knowledge

### Scene 2: Manager Dashboard (Ahmed, Arabic, 2 min)
1. "عرض فريقي" → Proactive alerts + view_team
2. "وريني طلبات الإجازة المعلقة" → view_pending_approvals
3. "وافق على إجازة خالد" → approve_leave
4. "كم عدد فريقي وكم نسبة السعودة؟" → get_team_headcount
5. "عرض لوحة التهيئة" → get_onboarding_dashboard

### Scene 3: Agent Handoff (Ahmed, 1 min)
1. "وش رصيد إجازتي السنوية؟" → Routes to Deema
2. "عرض فريقي" → Routes back to Waleed

### Scene 4: English (Turki, optional, 1 min)
1. "What's left on my onboarding?" → get_onboarding_checklist
2. "Who is on my team?" → Friendly non-manager error

### Reset Instructions
1. POST /api/v1/chat/reset/{employee_id} for each actor
2. Re-run seed_demo_data.py if needed

**Assigned to:** Huda (script), Rania (seed data), Layla (timing)
**Status:** TODO

---

## W4-06: Final Regression (P0)

> Run complete regression across W1-W4 before demo.

**Acceptance Criteria:**

- [ ] W1 tools: all 14 tools pass (re-run test_waleed.py)
- [ ] W2 conversations: multi-turn flows work (re-run test_waleed_conversations.py)
- [ ] W3 security: ownership checks hold
- [ ] W4 new features: proactive context, empty states, errors, handoff all work
- [ ] UI: employee dropdown still works after all changes
- [ ] Demo dry run: 3 consecutive runs produce consistent results

**Assigned to:** Layla (QA), Huda (conversation), Zaid (security spot check)
**Status:** TODO

---

## Coverage Matrix

| Capability | Story | Status |
|------------|-------|--------|
| Proactive context -- manager | W4-01 | ✅ Implemented |
| Proactive context -- new hire | W4-01 | ✅ Implemented |
| Empty states -- all 7 tools | W4-02 | ✅ Tool-level done |
| Error polish -- all 7 categories | W4-03 | ✅ Tool-level done |
| Agent handoff UX | W4-04 | ✅ Implemented |
| Demo script | W4-05 | TODO |
| Regression | W4-06 | TODO |
