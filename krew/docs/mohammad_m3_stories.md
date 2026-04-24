# Mohammad M3 — Interview Analysis, Offer, and Hire

**Status:** Ready for Architecture + Development
**Depends on:** M1 (13 tools, DONE), M2 (7 tools, DONE)
**Tools in M3:** 4 active + 1 deferred stub = 5 total

---

## M3-01: Analyze Interview Transcript (P0 — Demo-Critical)

> As an HR manager, I want Mohammad to analyze a pasted interview transcript so that I get structured feedback without rewatching the entire recording.

**Tool:** `analyze_interview_recording(candidate_id, transcript_text)`

### Parameters

| Param | Type | Required | Notes |
|-------|------|----------|-------|
| `candidate_id` | string (UUID) | Yes | Must belong to tenant (via JobPosting join) |
| `transcript_text` | string | Yes | Plain text of the interview transcript |

**Phase 1 scope:** Transcript text only. No `recording_url` parameter — Zoom/Whisper integration is deferred to M3-03 (Phase 2). Keep the tool name `analyze_interview_recording` for forward compatibility.

### Acceptance Criteria

- [ ] Given a valid `candidate_id` and `transcript_text`, when the tool is called, then create a new Interview record with `interview_type = zoom_analysis` and `status = completed`
- [ ] Given a valid call, when Claude analyzes the transcript, then the scorecard JSON contains all of these keys:
  - `answer_quality`: list of identified Q&A pairs with scores (1-10) each
  - `communication_skills`: object with `clarity`, `articulation`, `confidence` (1-10 each)
  - `technical_accuracy`: assessment of technical claims with supporting quotes
  - `red_flags`: list of `{flag, quote, severity}` (severity: low/medium/high)
  - `highlights`: list of strongest moments with quotes
  - `overall_recommendation`: enum `strong_hire | hire | no_hire | strong_no_hire` with `justification` string
  - `summary`: bilingual 3-4 sentence executive summary (EN + AR)
- [ ] Given analysis completes, when the Interview is saved, then `overall_score` is set (0-100) and `completed_at` is set to now
- [ ] Given analysis completes, when the Candidate is updated, then `ai_screening_notes` is appended (not overwritten) with a section header `--- Transcript Analysis (YYYY-MM-DD) ---` followed by the summary
- [ ] Given analysis completes, when the Candidate is updated, then `ai_match_score` is recalculated as a weighted average: 40% AI screening + 30% AI interview + 30% transcript analysis (use whatever scores exist; skip missing components)
- [ ] Given `candidate_id` does not exist or belongs to another tenant, when the tool is called, then return bilingual error: "Candidate not found" / "المرشح غير موجود"
- [ ] Given `transcript_text` is empty or missing, when the tool is called, then return bilingual error: "Please provide the interview transcript" / "يرجى تقديم نص المقابلة"
- [ ] Given a bilingual transcript (candidate switches between Arabic and English), when Claude analyzes it, then the analysis handles both languages correctly — the system prompt must instruct Claude to expect code-switching

### Implementation Notes

- Create the Interview record first (in_progress), run analysis, then update to completed. This avoids orphan records if analysis fails.
- The `_inner_claude_call` pattern from M1/M2 applies here. System prompt should include: "You are analyzing a human interview transcript. The candidate may speak in Arabic, English, or both."
- Store the full scorecard in `Interview.scorecard` JSON column.
- Do NOT store the raw transcript in the database (privacy). Only store the analysis.

**Dependencies:** M2-03 scoring pattern, Interview model (zoom_analysis type already exists)
**Saudi-specific:** Bilingual code-switching awareness, cultural communication norms (indirect answers are not necessarily red flags in Saudi context)

---

## M3-02: Get Interview Summary — Aggregated View (P1)

> As an HR manager, I want to see all interviews and assessments for a candidate in one summary so that I have a complete picture before making a hiring decision.

**Tool:** `get_interview_summary(candidate_id)`

### Parameters

| Param | Type | Required | Notes |
|-------|------|----------|-------|
| `candidate_id` | string (UUID) | Yes | Must belong to tenant (via JobPosting join) |

### Acceptance Criteria

- [ ] Given a valid `candidate_id` with interviews, when the tool is called, then return a JSON object with:
  - `candidate`: name, email, stage, job_posting title, `ai_match_score`
  - `timeline`: list of events sorted by date, each with `{date, type, score, summary}` where type is one of: `ai_screening`, `ai_interview`, `transcript_analysis`, `stage_change`
  - `scores`: object with `screening_score`, `interview_score`, `transcript_score`, `composite_score` (weighted average, same weights as M3-01)
  - `consistency`: string — "improving", "declining", "consistent", or "mixed" based on score trend
  - `progression_narrative`: bilingual 2-3 sentence narrative (EN + AR) summarizing the candidate's journey
- [ ] Given a candidate with no interviews and no screening, when the tool is called, then return bilingual message: "No interviews or assessments recorded for this candidate" / "لا توجد مقابلات أو تقييمات مسجلة لهذا المرشح"
- [ ] Given a candidate with only one data point (e.g., only AI screening), when the tool is called, then return whatever exists without failing — `consistency` should be "insufficient_data"
- [ ] Given `candidate_id` not found or wrong tenant, when the tool is called, then return bilingual error

### Implementation Notes

- This is a read-only aggregation tool. No Claude inner call needed — just query and format.
- Pull data from: Candidate.ai_screening_notes, Interview records (all types), Candidate.stage.
- For the timeline, include stage changes if tracked (currently not tracked with timestamps — use Interview.created_at and Candidate.created_at as proxy).

**Dependencies:** M1-08 (screening), M2-01/M2-03 (AI interview), M3-01 (transcript analysis)
**Saudi-specific:** Bilingual output

---

## M3-03: Zoom Integration Setup (DEFERRED — Phase 2)

> As a platform administrator, I want Krew to connect to our Zoom account so that interview recordings are automatically fetched and analyzed.

**Status: DEFERRED to Phase 2 (post-funding). No implementation needed now.**

### What to Implement Now

- [ ] Add the tool definition to `get_tools()` with name `setup_zoom_integration`
- [ ] In the dispatch method, return a static bilingual message: "Zoom integration is coming soon! For now, you can paste interview transcripts directly and I will analyze them." / "تكامل Zoom قادم قريبا! حاليا يمكنك لصق نص المقابلة مباشرة وسأقوم بتحليله."
- [ ] That is all. No OAuth, no webhooks, no recording fetch.

### Phase 2 Scope (for reference only — do NOT implement)

- Zoom OAuth 2.0 per tenant
- Webhook for `recording.completed`
- Auto-match recording to candidate by meeting metadata
- Whisper transcription fallback
- MS Teams and Google Meet support

**Priority:** P2 (deferred)

---

## M3-04: Generate Offer Recommendation (P0 — Demo-Critical)

> As an HR manager, I want Mohammad to recommend a salary and offer package based on all interview data and the job posting range so that I can make competitive, fair offers.

**Tool:** `generate_offer_recommendation(candidate_id, job_posting_id)`

### Parameters

| Param | Type | Required | Notes |
|-------|------|----------|-------|
| `candidate_id` | string (UUID) | Yes | Must belong to tenant |
| `job_posting_id` | string (UUID) | Yes | Must belong to tenant, and candidate must be linked to this posting |

### Acceptance Criteria

- [ ] Given a valid candidate who has been interviewed (stage is `interviewed`, `offer_sent`, or `hired`), when the tool is called, then use Claude to return:
  - `recommended_salary_sar`: integer within the posting's `salary_min_sar` to `salary_max_sar` range
  - `salary_justification`: 2-3 sentences explaining why this number (candidate strength relative to range)
  - `probation_period_days`: 90 (default per Saudi Labor Law Article 53) or 180 if justified with reason
  - `probation_end_date`: calculated from today or provided start_date
  - `start_date_suggestion`: date string, accounting for standard 30-day notice period, not falling on Saudi weekend (Fri/Sat)
  - `benefits_summary`: standard Saudi package (GOSI registration, medical per CCHI, 21 days annual leave per Article 109 for first 5 years)
  - `saudization_impact`: if candidate `is_saudi` data is available, note Nitaqat impact; otherwise state "nationality data not available"
  - `risk_assessment`: flight risk and counter-offer likelihood based on interview signals
  - `overall_recommendation`: bilingual summary (EN + AR)
- [ ] Given the candidate stage is before `interviewed` (e.g., `applied`, `screened`, `shortlisted`), when the tool is called, then return bilingual error: "Candidate must complete interviews before generating an offer recommendation" / "يجب إتمام المقابلات قبل إعداد توصية العرض"
- [ ] Given the job posting has no salary range set (`salary_min_sar` and `salary_max_sar` are both null), when the tool is called, then still generate a recommendation but note: "No salary range defined on the posting — recommendation is based on market context only" and do not constrain the number
- [ ] Given the candidate has no interview scores (only stage was manually advanced), when the tool is called, then generate a recommendation with a caveat: "Limited data available — recommendation is based on screening data only"
- [ ] Given invalid UUIDs or wrong tenant, when the tool is called, then return bilingual error

### Implementation Notes

- Uses `_inner_claude_call`. System prompt should include the salary range, all interview scores, screening notes, and job requirements.
- The Claude prompt should reference Saudi Labor Law articles by number for credibility in the output.
- `start_date_suggestion` logic: today + 30 days, then skip forward if that lands on Friday or Saturday.
- Candidate model does not have `is_saudi` — this data is unknown at candidate stage. The tool should note this and suggest collecting it during offer negotiation.

**Dependencies:** M3-02 (aggregated view feeds into this), JobPosting salary range
**Saudi-specific:** Article 53 (probation), Article 84 (end of service), Article 109 (annual leave), GOSI, CCHI, Nitaqat, Saudi weekend (Fri/Sat), SAR currency

---

## M3-05: Hire Candidate + Waleed Handoff (P0 — Demo WOW Moment)

> As an HR manager, I want to say "hire her" or "وظفها" and have Mohammad create the Employee record and signal Waleed to start onboarding — all in one step.

**Tool:** `hire_candidate(candidate_id, start_date?, salary_sar?)`

### Parameters

| Param | Type | Required | Notes |
|-------|------|----------|-------|
| `candidate_id` | string (UUID) | Yes | Must belong to tenant |
| `start_date` | string (YYYY-MM-DD) | No | Defaults to today; validated not on Saudi weekend |
| `salary_sar` | integer | No | Monthly salary in SAR; if omitted, use M3-04 recommendation or posting midpoint |

### Candidate-to-Employee Field Mapping

This is the critical mapping. The Candidate model has a single `name` field; the Employee model has `first_name` + `last_name`.

| Candidate Field | Employee Field | Mapping Logic |
|----------------|---------------|---------------|
| `name` | `first_name`, `last_name` | Split on first space: everything before first space = `first_name`, everything after = `last_name`. If single word, `last_name = ""`. Log a warning if single word. |
| `email` | `email` | Direct copy |
| `phone` | `phone` | Direct copy |
| (via JobPosting) `department_id` | `department_id` | From `JobPosting.department_id` |
| (via JobPosting) `title` | `job_title` | From `JobPosting.title` |
| (via JobPosting) `title_ar` | `job_title_ar` | From `JobPosting.title_ar` (may be null) |
| (via JobPosting) `tenant_id` | `tenant_id` | From `JobPosting.tenant_id` |
| parameter `start_date` or today | `hire_date` | Parameter or `date.today()` |
| parameter `salary_sar` | `salary_sar` | Parameter, or M3-04 recommendation, or midpoint of posting range |
| — | `status` | `EmployeeStatus.onboarding` |
| — | `employee_number` | Auto-generate: `EMP-{NNN}` where NNN is zero-padded sequential per tenant (query MAX existing, increment) |
| — | `probation_end_date` | `hire_date + 90 days` (Article 53) |
| — | `is_saudi` | Default `True` (unknown at candidate stage; can be corrected during onboarding) |
| — | `preferred_language` | Default `"ar"` |
| — | `gosi_registered` | Default `False` (Waleed handles GOSI during onboarding) |

### Acceptance Criteria

- [ ] Given a valid candidate in stage `interviewed` or `offer_sent`, when `hire_candidate` is called, then:
  1. Candidate.stage is updated to `hired`
  2. A new Employee record is created with all fields per the mapping table above
  3. The employee_number is unique per tenant (format `EMP-001`, `EMP-002`, etc.)
  4. The response includes the new `employee_id` and `employee_number`
- [ ] Given the hire succeeds, when the response is generated, then Mohammad returns a bilingual celebration message:
  - EN: "Congratulations! {name} has been hired as {job_title}. Employee record created (#{employee_number}). Waleed will begin the onboarding process."
  - AR: "مبروك! تم توظيف {name} في وظيفة {job_title}. تم إنشاء سجل الموظف (#{employee_number}). وليد سيبدأ عملية التهيئة."
- [ ] Given the candidate is already in stage `hired`, when the tool is called, then return bilingual error: "This candidate has already been hired" / "تم توظيف هذا المرشح بالفعل"
- [ ] Given the candidate is in stage `rejected` or `withdrawn`, when the tool is called, then return bilingual error: "Cannot hire a candidate who has been {stage}" / "لا يمكن توظيف مرشح تم {stage_ar}"
- [ ] Given the candidate is in stage `applied` or `screened` (not yet interviewed), when the tool is called, then return bilingual error: "Candidate must complete interviews before hiring" / "يجب إتمام المقابلات قبل التوظيف"
- [ ] Given `start_date` falls on a Saudi weekend (Friday or Saturday), when the tool is called, then auto-adjust to the next Sunday and include a note: "Start date adjusted to {date} (original date was a weekend)" / "تم تعديل تاريخ البدء إلى {date} (التاريخ الأصلي يوم عطلة)"
- [ ] Given `salary_sar` is not provided and no offer recommendation exists, when the tool is called, then use the midpoint of `JobPosting.salary_min_sar` and `salary_max_sar`. If both are null, set `salary_sar = None` on the Employee and include a note: "Salary not set — please update before onboarding completes"
- [ ] Given an email that already exists for another Employee in the same tenant, when the tool is called, then return bilingual error: "An employee with this email already exists" / "يوجد موظف بنفس البريد الإلكتروني"
- [ ] Given the hire succeeds, when the Employee is created, then the entire operation (Candidate update + Employee create) is in a single DB transaction — if Employee creation fails, Candidate stage must NOT be updated

### Employee Number Generation Logic

```
Query: SELECT employee_number FROM employees WHERE tenant_id = :tid AND employee_number LIKE 'EMP-%' ORDER BY employee_number DESC LIMIT 1
Parse the numeric suffix, increment by 1, zero-pad to 3 digits (or more if > 999).
If no employees exist, start at EMP-001.
```

### Waleed Handoff Mechanism

For the demo, the handoff is **conversational, not programmatic**. Mohammad's response message includes the phrase "وليد سيبدأ عملية التهيئة" which signals to the user that Waleed is the next step. The orchestrator already routes onboarding keywords to Waleed.

Future enhancement (post-demo): Create a `handoff_events` table or use an in-memory event bus so Waleed can proactively greet the new hire. Not needed for M3.

- [ ] Given the hire succeeds, when Mohammad responds, then the response text must contain both "Waleed" and "وليد" so it works in both language contexts
- [ ] Given the hire succeeds, when the user next says "start onboarding" or "ابدأ التهيئة", then the orchestrator routes to Waleed who can look up the new Employee by status=onboarding

### Implementation Notes

- Use the existing `AdminService.create_employee()` for Employee creation — it already handles email uniqueness checks. Build the data dict and call it.
- The transaction boundary: wrap candidate stage update + employee creation in a single `async with db.begin()` block.
- `_is_saudi_weekend()` helper already exists in Mohammad agent.

**Dependencies:** Employee model, AdminService.create_employee, Waleed agent (for onboarding after handoff), M1-09 (update_candidate_stage)
**Saudi-specific:** Article 53 probation (90 days default), Saudi weekend validation, employee_number generation, GOSI registration flag, Saudization default

---

## Orchestrator Keywords to Add for M3

The orchestrator's `INTENT_KEYWORDS["mohammad"]` list needs these additions for M3 routing:

```python
# M3 additions — add to the existing mohammad keyword list
"transcript", "تحليل مقابلة",     # M3-01
"offer", "عرض وظيفي", "عرض",     # M3-04  (NOTE: check "عرض" doesn't conflict with other agents)
"وظفها", "وظفه", "hire her", "hire him",  # M3-05 demo trigger
"نبي نوظفها", "نبي نوظفه",       # M3-05 Saudi dialect
"zoom",                            # M3-03 (deferred, but route to Mohammad for the stub message)
```

**Important:** Verify that "offer" and "عرض" do not collide with Deema or Norah keywords before adding. Currently they do not appear in any other agent's list.

---

## Coverage Matrix

| Capability | Story | Status |
|-----------|-------|--------|
| Analyze interview transcript (text) | M3-01 | Covered |
| Analyze interview recording (URL/Whisper) | M3-01 | Deferred to Phase 2 |
| Aggregated interview summary | M3-02 | Covered |
| Zoom OAuth integration | M3-03 | Deferred (stub only) |
| MS Teams / Google Meet integration | M3-03 | Deferred to Phase 2 |
| Generate offer recommendation | M3-04 | Covered |
| Salary benchmarking (external data) | M3-04 | Partial — uses posting range + AI; no external API |
| Hire candidate (create Employee) | M3-05 | Covered |
| Waleed handoff (conversational) | M3-05 | Covered |
| Waleed handoff (programmatic event) | — | Gap — Phase 2 |
| Nitaqat impact calculation | M3-04 | Partial — noted but no real Nitaqat API |
| Pipeline analytics (time-to-hire) | M3-05 | Gap — log hire_date vs Candidate.created_at; defer to Norah |

---

## M3 Tool Count Summary

| Tool | Story | Status |
|------|-------|--------|
| `analyze_interview_recording` | M3-01 | New |
| `get_interview_summary` | M3-02 | New |
| `setup_zoom_integration` | M3-03 | New (stub) |
| `generate_offer_recommendation` | M3-04 | New |
| `hire_candidate` | M3-05 | New |

**Total after M3: 13 (M1) + 7 (M2) + 5 (M3) = 25 tools**

---

## Demo Script Hook (M3-05)

The investor demo moment:

1. User says: "وظفها" (hire her) — context: they have been reviewing a candidate
2. Mohammad calls `hire_candidate` — creates Employee, updates Candidate stage
3. Mohammad responds: "مبروك! تم توظيف سارة في وظيفة مهندسة برمجيات. سجل الموظف #EMP-004 جاهز. وليد سيبدأ عملية التهيئة."
4. User says: "وليد، ابدأ التهيئة" — orchestrator routes to Waleed
5. Waleed picks up the new employee and begins onboarding checklist

This is the cross-agent handoff moment that demonstrates the platform vision.
