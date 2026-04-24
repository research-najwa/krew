# Mohammad M1: Technical Architecture

**Architect:** Faisal
**Sprint:** M1 — Core Pipeline + AI JD Writer + Web Search
**Stories:** M1-01 through M1-14
**Date:** 2026-03-25

---

## 1. Tool Inventory (14 Tools)

| # | Tool Name | Story | Type | DB Tables | Description |
|---|-----------|-------|------|-----------|-------------|
| 1 | `get_job_postings` | M1-01 | READ | JobPosting, Department, Candidate | List postings with filters, applicant counts |
| 2 | `get_job_posting` | M1-02 | READ | JobPosting, Department, Candidate | Single posting detail with candidate breakdown |
| 3 | `create_job_posting` | M1-03 | WRITE | JobPosting, Department | Create a new posting (starts as draft) |
| 4 | `generate_job_description` | M1-04 | WRITE* | JobPosting, Department | Inner Claude call to generate bilingual JD; optionally creates posting |
| 5 | `extract_job_keywords` | M1-05 | READ* | JobPosting | Inner Claude call to extract searchable keywords from a JD |
| 6 | `search_candidates_web` | M1-06 | READ | None (external API) | Web search for candidate profiles on Saudi job platforms |
| 7 | `view_candidates` | M1-07 | READ | Candidate, JobPosting | List candidates with optional posting/stage filter |
| 8 | `screen_candidate` | M1-08 | WRITE | Candidate, JobPosting | Inner Claude call for AI screening; stores score + notes + stage update |
| 9 | `update_candidate_stage` | M1-09 | WRITE | Candidate, JobPosting | Move candidate through pipeline stages with transition validation |
| 10 | `schedule_interview` | M1-10 | WRITE | Candidate, JobPosting, Employee | Schedule interview, validate weekend/dates, update stage |
| 11 | `get_pipeline_summary` | M1-11 | READ | JobPosting, Candidate | Aggregated pipeline dashboard stats |
| 12 | `add_candidate` | — | WRITE | Candidate, JobPosting | Add a candidate to a posting (needed for demo completeness) |
| 13 | `search_employee` | — | READ | Employee | Find interviewer by name (reuse Waleed's pattern) |
| 14 | — (proactive context) | M1-12 | READ | JobPosting, Candidate | Not a tool — override of `get_proactive_context()` |

\* Tools 4, 5, and 8 involve inner Claude API calls in addition to DB operations.

**Note on tool #12 (`add_candidate`):** The stories do not explicitly call for this tool, but the demo requires candidates in the pipeline. Without it, there is no way to add a candidate through chat. Adding this tool is cheap (simple INSERT) and closes a functional gap. If the CTO disagrees, we seed all candidates and drop this tool.

**Note on tool #13 (`search_employee`):** M1-10 requires interviewer employee UUIDs. Without a search tool, the user must know UUIDs. Reuse Waleed's `_search_employee` pattern. If the CTO prefers not to duplicate, we can import Waleed's method, but duplicating a 30-line function is cleaner than cross-agent dependencies.

---

## 2. Inner Claude Calls Pattern

### 2.1 Existing Pattern Analysis

The `BaseAgent` class already instantiates an `anthropic.AsyncAnthropic` client in `__init__` as `self.client`. This same client is used for the outer tool-use loop in `respond()`. No existing agent makes inner Claude calls today — Mohammad M1 will be the first.

### 2.2 Design Decision: Reuse `self.client`

- Use the same `self.client` (from BaseAgent) for inner calls. No new client instantiation needed.
- Inner calls use `self.client.messages.create()` directly inside tool handler methods.
- Inner calls use `claude-sonnet-4-6` (same model as outer loop, via `settings.llm_model`).
- Inner calls do NOT use tools — they are pure text-in, structured-text-out.

### 2.3 Inner Call Wrapper

Create a helper method on MohammadAgent to standardize inner calls:

```python
async def _inner_claude_call(
    self,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 2048,
) -> str:
    """Make an inner Claude call for AI-powered tools (JD generation, screening).

    Returns the text response. Raises RuntimeError on failure.
    """
    try:
        response = await self.client.messages.create(
            model=settings.llm_model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return response.content[0].text
    except anthropic.APIError as exc:
        logger.error("Inner Claude call failed: %s", exc)
        raise RuntimeError(f"AI generation failed: {exc}") from exc
```

### 2.4 JD Generation Prompt (M1-04)

System prompt for the inner call:

```
You are a Saudi HR expert writing a job description for a company in Saudi Arabia.

Context:
- Saudi work week: Sunday to Thursday
- Saudi weekend: Friday and Saturday
- Currency: Saudi Riyal (SAR)
- Saudization/Nitaqat: The government requires a percentage of Saudi nationals
  in the workforce. For tech roles, the Nitaqat green zone requires ~25-30% Saudization.
  For non-tech roles, requirements may be higher.
- GOSI: Employer contributes 12% of salary to General Organization for Social Insurance
- Medical insurance: Mandatory per CCHI (Council of Cooperative Health Insurance)
- Annual leave: 21 days for first 5 years, 30 days after (Saudi Labor Law Article 109)
- Probation: Maximum 90 days (extendable to 180 with written agreement)

Generate a professional job description in the following JSON structure:
{
  "title": "...",
  "title_ar": "...",
  "summary": "2-3 sentence overview",
  "summary_ar": "...",
  "responsibilities": ["...", "..."],
  "responsibilities_ar": ["...", "..."],
  "requirements": ["...", "..."],
  "requirements_ar": ["...", "..."],
  "nice_to_have": ["...", "..."],
  "nice_to_have_ar": ["...", "..."],
  "salary_range_suggestion": {"min": 0, "max": 0},
  "saudization_note": "..."
}

Output ONLY valid JSON. No markdown. No explanation.
```

User prompt template:

```
Role: {role_title}
Department: {department or "Not specified"}
Seniority: {seniority or "mid"}
Language: {language}

If language is "en", omit all _ar fields.
If language is "ar", omit all English fields and write everything in Arabic.
If language is "both", include all fields.

Salary benchmarks (SAR/month):
- Junior: 8,000 - 14,000
- Mid: 14,000 - 22,000
- Senior: 22,000 - 35,000
- Lead: 30,000 - 45,000
- Executive: 40,000 - 70,000
```

### 2.5 Candidate Screening Prompt (M1-08)

System prompt:

```
You are an AI recruitment screener for a Saudi company. Analyze the candidate
against the job requirements and provide a structured assessment.

Output ONLY valid JSON in this structure:
{
  "fit_score": 0-100,
  "strengths": ["...", "..."],
  "gaps": ["...", "..."],
  "experience_relevance": "high/medium/low",
  "skills_match_pct": 0-100,
  "recommendation": "proceed_to_interview|review_further|likely_not_a_fit",
  "summary": "2-3 sentence assessment",
  "summary_ar": "..."
}

Scoring guidelines:
- 80-100: Strong match, recommend interview
- 60-79: Partial match, needs further review
- 0-59: Weak match, likely not a fit

Consider Saudi market context:
- Saudi university graduates (King Saud, KFUPM, KAUST) are well-regarded
- Professional certifications (PMP, AWS, CPA) add value
- Bilingual (Arabic+English) is a strong plus
- Saudi nationals may have Saudization priority
```

User prompt:

```
JOB POSTING:
Title: {posting.title}
Description: {posting.description}
Requirements: {posting.requirements}
Salary Range: {salary_range}

CANDIDATE:
Name: {candidate.name}
Email: {candidate.email}
Resume URL: {candidate.resume_url or "No resume on file"}
Current Stage: {candidate.stage}
Previous Screening Notes: {candidate.ai_screening_notes or "None"}

Note: If no resume is available, base the screening on whatever profile data exists.
Be explicit that the assessment is limited without a resume.
```

### 2.6 Keyword Extraction Prompt (M1-05)

System prompt:

```
You are an HR keyword extraction specialist for the Saudi job market.
Extract searchable keywords from the job description.

Output ONLY valid JSON:
{
  "technical_skills": ["...", "..."],
  "soft_skills": ["...", "..."],
  "certifications": ["...", "..."],
  "experience_keywords": ["...", "..."],
  "search_strings": [
    "optimized search query 1 for job platforms",
    "optimized search query 2",
    "optimized search query 3"
  ],
  "platform_suggestions": [
    {"platform": "LinkedIn", "reason": "Best for professional/tech roles"},
    {"platform": "Bayt.com", "reason": "Largest Arab job board"},
    {"platform": "Jadarat", "reason": "Saudi nationals (Saudization compliance)"}
  ]
}
```

### 2.7 Error Handling for Inner Calls

Every tool that makes an inner Claude call wraps it in try/except:

```python
try:
    raw = await self._inner_claude_call(system_prompt, user_prompt)
    result = json.loads(raw)
except RuntimeError:
    return json.dumps({
        "error": "AI analysis temporarily unavailable. Please try again.",
        "error_ar": "التحليل الذكي غير متاح مؤقتاً. يرجى المحاولة مرة أخرى.",
    })
except json.JSONDecodeError:
    logger.error("Inner Claude call returned invalid JSON: %s", raw[:200])
    return json.dumps({
        "error": "AI returned an unexpected format. Please try again.",
        "error_ar": "التحليل الذكي أرجع نتيجة غير متوقعة. يرجى المحاولة مرة أخرى.",
    })
```

### 2.8 Token / Cost Considerations

| Tool | Estimated Input Tokens | Estimated Output Tokens | Cost per Call (~) |
|------|----------------------|------------------------|-------------------|
| `generate_job_description` | ~800 (prompts) | ~1500 (bilingual JD) | ~$0.012 |
| `screen_candidate` | ~600 (prompts + JD + candidate) | ~500 (analysis) | ~$0.005 |
| `extract_job_keywords` | ~500 (prompt + JD text) | ~400 (keywords) | ~$0.004 |

Total inner call cost per full demo (1 JD + 1 screen + 1 extract): ~$0.021. Negligible.

Max tokens for inner calls: 2048 (sufficient for all three use cases).

---

## 3. Service Layer Decision

**Decision: NO separate service layer for M1. Keep everything in the agent.**

Rationale:

1. **Waleed's pattern is the exception, not the rule.** Waleed has `OnboardingService` and `ManagerService` because onboarding has complex multi-step lifecycle logic (template resolution, step assignment, completion cascades, overdue detection). Mohammad M1 tools are simpler — most are single-query reads or single-row writes.

2. **Deema does not have a service layer for most tools.** Deema's tools query models directly in the agent. The only extracted service is `check_and_submit_leave` (in `services/leave.py`) because leave submission involves atomic balance checks + request creation. Mohammad has no equivalent atomicity concern in M1.

3. **No shared logic between tools yet.** The only repeated pattern is tenant-isolated candidate lookup (join Candidate through JobPosting). This is a 3-line query, not worth extracting.

4. **M2/M3 may justify a service.** When we add interview lifecycle (start interview, submit answers, score, compare finalists), that will have enough complexity for a `RecruitmentService`. We can extract then without breaking M1.

**What to extract instead:** A few private helper methods on MohammadAgent:

- `_get_candidate_with_posting(candidate_id) -> tuple[Candidate, JobPosting] | None` — common lookup with tenant isolation
- `_format_salary(min_sar, max_sar) -> str` — SAR formatting with thousand separators
- `_validate_uuid(value, field_name) -> UUID | str` — returns UUID or error JSON string
- `_inner_claude_call(system, user, max_tokens) -> str` — inner call wrapper (section 2.3)

---

## 4. Database Queries

### 4.1 Tenant Isolation Strategy

**Critical:** The `Candidate` table does NOT have a `tenant_id` column. Tenant isolation for candidates MUST go through `JobPosting`:

```python
# Pattern: always join Candidate -> JobPosting for tenant isolation
select(Candidate).join(JobPosting, Candidate.job_posting_id == JobPosting.id).where(
    JobPosting.tenant_id == self.tenant_id,
    ...
)
```

This is safe because every candidate belongs to exactly one job posting, and every job posting has a `tenant_id`.

### 4.2 Query Outlines Per Tool

#### Tool 1: `get_job_postings` (M1-01)

```python
from sqlalchemy import select, func

# Base query with applicant count subquery
applicant_count = (
    select(func.count(Candidate.id))
    .where(Candidate.job_posting_id == JobPosting.id)
    .correlate(JobPosting)
    .scalar_subquery()
    .label("applicant_count")
)

query = (
    select(JobPosting, Department.name.label("dept_name"), applicant_count)
    .outerjoin(Department, JobPosting.department_id == Department.id)
    .where(JobPosting.tenant_id == self.tenant_id)
)

if status:
    # Validate status against PostingStatus enum first
    query = query.where(JobPosting.status == PostingStatus(status))
if department:
    query = query.where(func.lower(Department.name) == department.lower())

query = query.order_by(JobPosting.created_at.desc()).limit(20)
result = await self.db.execute(query)
rows = result.all()
```

**Tables:** JobPosting, Department (LEFT JOIN), Candidate (correlated subquery)
**Indexes needed:** None new — `job_postings.tenant_id` and `candidates.job_posting_id` should already be indexed via FK.

#### Tool 2: `get_job_posting` (M1-02)

```python
# 1. Fetch posting with department
posting_query = (
    select(JobPosting, Department.name.label("dept_name"))
    .outerjoin(Department, JobPosting.department_id == Department.id)
    .where(JobPosting.id == job_posting_id, JobPosting.tenant_id == self.tenant_id)
)
row = (await self.db.execute(posting_query)).one_or_none()

# 2. Candidates by stage (aggregation)
stage_query = (
    select(Candidate.stage, func.count(Candidate.id))
    .where(Candidate.job_posting_id == job_posting_id)
    .group_by(Candidate.stage)
)
stage_rows = (await self.db.execute(stage_query)).all()
candidates_by_stage = {stage.value: count for stage, count in stage_rows}

# 3. Top 5 candidates by AI score
top_query = (
    select(Candidate)
    .where(
        Candidate.job_posting_id == job_posting_id,
        Candidate.ai_match_score.is_not(None),
    )
    .order_by(Candidate.ai_match_score.desc())
    .limit(5)
)
top_candidates = (await self.db.execute(top_query)).scalars().all()
```

**Tables:** JobPosting, Department, Candidate
**Indexes recommended:** `CREATE INDEX ix_candidates_posting_score ON candidates(job_posting_id, ai_match_score DESC NULLS LAST);`

#### Tool 3: `create_job_posting` (M1-03)

```python
# 1. Department lookup (if provided)
if department_name:
    dept_result = await self.db.execute(
        select(Department).where(
            Department.tenant_id == self.tenant_id,
            func.lower(Department.name) == department_name.lower(),
        )
    )
    dept = dept_result.scalar_one_or_none()
    if not dept:
        # Fetch all dept names for the error message
        all_depts = await self.db.execute(
            select(Department.name).where(Department.tenant_id == self.tenant_id)
        )
        dept_names = [r[0] for r in all_depts.all()]
        return json.dumps({
            "error": f"Department '{department_name}' not found.",
            "error_ar": f"القسم '{department_name}' غير موجود.",
            "valid_departments": dept_names,
        })

# 2. Create posting
posting = JobPosting(
    tenant_id=self.tenant_id,
    department_id=dept.id if dept else None,
    title=title,
    title_ar=title_ar,
    description=description or "",
    requirements=requirements,
    salary_min_sar=salary_min,
    salary_max_sar=salary_max,
    status=PostingStatus.draft,
)
self.db.add(posting)
await self.db.commit()
await self.db.refresh(posting)
```

**Tables:** Department (lookup), JobPosting (INSERT)
**Commit:** Yes — write operation.

#### Tool 4: `generate_job_description` (M1-04)

```python
# 1. Inner Claude call (see section 2.4)
raw = await self._inner_claude_call(jd_system_prompt, jd_user_prompt, max_tokens=2048)
jd_data = json.loads(raw)

# 2. If auto_create_posting:
if auto_create_posting:
    posting = JobPosting(
        tenant_id=self.tenant_id,
        department_id=dept_id,  # looked up earlier if department param provided
        title=jd_data.get("title", role_title),
        title_ar=jd_data.get("title_ar"),
        description=jd_data.get("summary", ""),
        requirements="\n".join(jd_data.get("requirements", [])),
        salary_min_sar=jd_data.get("salary_range_suggestion", {}).get("min"),
        salary_max_sar=jd_data.get("salary_range_suggestion", {}).get("max"),
        status=PostingStatus.draft,
    )
    self.db.add(posting)
    await self.db.commit()
    await self.db.refresh(posting)
    jd_data["posting_id"] = str(posting.id)
    jd_data["posting_status"] = "draft"
```

**Tables:** Department (optional lookup), JobPosting (conditional INSERT)

#### Tool 5: `extract_job_keywords` (M1-05)

```python
# 1. If job_posting_id provided, fetch description
if job_posting_id:
    posting = await self.db.execute(
        select(JobPosting).where(
            JobPosting.id == UUID(job_posting_id),
            JobPosting.tenant_id == self.tenant_id,
        )
    )
    p = posting.scalar_one_or_none()
    text = f"{p.description}\n{p.requirements}" if p else None
elif description_text:
    text = description_text
# 2. Inner Claude call
```

**Tables:** JobPosting (conditional READ)

#### Tool 7: `view_candidates` (M1-07)

```python
query = (
    select(Candidate, JobPosting.title.label("job_title"))
    .join(JobPosting, Candidate.job_posting_id == JobPosting.id)
    .where(JobPosting.tenant_id == self.tenant_id)
)

if job_posting_id:
    query = query.where(Candidate.job_posting_id == UUID(job_posting_id))
if stage:
    query = query.where(Candidate.stage == CandidateStage(stage))

query = query.order_by(Candidate.created_at.desc()).limit(50)
```

**Tables:** Candidate, JobPosting (JOIN for tenant isolation + title)
**Indexes:** FK index on `candidates.job_posting_id` (should exist)

#### Tool 8: `screen_candidate` (M1-08)

```python
# 1. Fetch candidate + posting (with tenant check)
result = await self.db.execute(
    select(Candidate, JobPosting)
    .join(JobPosting, Candidate.job_posting_id == JobPosting.id)
    .where(
        Candidate.id == candidate_id,
        JobPosting.tenant_id == self.tenant_id,
    )
)
row = result.one_or_none()
# ... validate both exist ...

candidate, posting = row

# 2. Check if already screened
if candidate.ai_match_score is not None:
    return json.dumps({
        "already_screened": True,
        "message": "This candidate was already screened.",
        "message_ar": "تم فحص هذا المرشح مسبقاً.",
        "ai_match_score": candidate.ai_match_score,
        "ai_screening_notes": candidate.ai_screening_notes,
    })

# 3. Inner Claude call (see section 2.5)
raw = await self._inner_claude_call(screening_system, screening_user, max_tokens=1024)
analysis = json.loads(raw)

# 4. Update candidate record (atomic)
candidate.ai_match_score = analysis["fit_score"]
candidate.ai_screening_notes = json.dumps(analysis, ensure_ascii=False)
if candidate.stage == CandidateStage.applied:
    candidate.stage = CandidateStage.screened
await self.db.commit()
```

**Tables:** Candidate (READ + UPDATE), JobPosting (READ for tenant check + JD context)

#### Tool 9: `update_candidate_stage` (M1-09)

```python
# 1. Fetch candidate with tenant check
result = await self.db.execute(
    select(Candidate, JobPosting.title)
    .join(JobPosting, Candidate.job_posting_id == JobPosting.id)
    .where(
        Candidate.id == candidate_id,
        JobPosting.tenant_id == self.tenant_id,
    )
)

# 2. Validate transition (see transition rules below)
BLOCKED_FROM = {
    CandidateStage.hired: set(),  # cannot move from hired to anything
    CandidateStage.withdrawn: set(),  # cannot move from withdrawn to anything
}
BLOCKED_FROM[CandidateStage.rejected] = {
    s for s in CandidateStage if s != CandidateStage.applied
}  # rejected -> only applied (re-open)

current = candidate.stage
target = CandidateStage(new_stage)

if current in BLOCKED_FROM and (not BLOCKED_FROM[current] or target not in BLOCKED_FROM[current]):
    if current == CandidateStage.hired:
        return json.dumps({...})  # cannot move hired candidate

# 3. Update + optional notes append
old_stage = candidate.stage
candidate.stage = target
if notes:
    timestamp = datetime.now(ZoneInfo("Asia/Riyadh")).strftime("%Y-%m-%d %H:%M")
    note_entry = f"[{timestamp}] {notes}"
    if candidate.ai_screening_notes:
        candidate.ai_screening_notes += f"\n{note_entry}"
    else:
        candidate.ai_screening_notes = note_entry

await self.db.commit()
```

**Tables:** Candidate (READ + UPDATE), JobPosting (JOIN for tenant check)

#### Tool 10: `schedule_interview` (M1-10)

```python
# 1. Validate candidate + posting (tenant isolated)
# 2. Validate interviewer_ids exist as employees in same tenant
for iid in interviewer_ids:
    emp = await self.db.execute(
        select(Employee.id, Employee.first_name, Employee.last_name)
        .where(Employee.id == UUID(iid), Employee.tenant_id == self.tenant_id)
    )
    # ... collect interviewer names or error ...

# 3. Validate date
proposed = date.fromisoformat(proposed_date)
if proposed < date.today():
    return json.dumps({...})  # past date error

# 4. Weekend detection (Friday=4, Saturday=5 in Python weekday())
if proposed.weekday() in (4, 5):
    weekend_warning = {
        "warning": "This date falls on the Saudi weekend (Fri-Sat).",
        "warning_ar": "هذا التاريخ يوافق عطلة نهاية الأسبوع (الجمعة-السبت).",
    }
    # Include warning in response but do NOT block

# 5. Update candidate stage
if candidate.stage in (CandidateStage.applied, CandidateStage.screened, CandidateStage.shortlisted):
    candidate.stage = CandidateStage.interview_scheduled
elif candidate.stage in (CandidateStage.interviewed, CandidateStage.offer_sent,
                          CandidateStage.hired, CandidateStage.rejected):
    return json.dumps({
        "error": "Candidate has already progressed past the interview stage.",
        "error_ar": "المرشح تجاوز مرحلة المقابلة بالفعل.",
    })

await self.db.commit()
```

**Tables:** Candidate (READ + UPDATE), JobPosting (tenant check), Employee (interviewer validation)
**Note:** M1 does NOT create an Interview table/record. The schedule is "soft" — we update the candidate stage and return confirmation. M2 will add a proper Interview model.

#### Tool 11: `get_pipeline_summary` (M1-11)

```python
# 1. Postings by status
posting_status_query = (
    select(JobPosting.status, func.count(JobPosting.id))
    .where(JobPosting.tenant_id == self.tenant_id)
    .group_by(JobPosting.status)
)

# 2. Candidates by stage (tenant-isolated via join)
candidate_stage_query = (
    select(Candidate.stage, func.count(Candidate.id))
    .join(JobPosting, Candidate.job_posting_id == JobPosting.id)
    .where(JobPosting.tenant_id == self.tenant_id)
    .group_by(Candidate.stage)
)

# 3. Stale postings (open > 30 days, < 5 candidates)
thirty_days_ago = datetime.utcnow() - timedelta(days=30)
stale_query = (
    select(JobPosting.id, JobPosting.title, func.count(Candidate.id).label("cand_count"))
    .outerjoin(Candidate, Candidate.job_posting_id == JobPosting.id)
    .where(
        JobPosting.tenant_id == self.tenant_id,
        JobPosting.status == PostingStatus.open,
        JobPosting.created_at < thirty_days_ago,
    )
    .group_by(JobPosting.id, JobPosting.title)
    .having(func.count(Candidate.id) < 5)
)

# 4. Recent hires
recent_hires_query = (
    select(Candidate.name, JobPosting.title, Candidate.created_at)
    .join(JobPosting, Candidate.job_posting_id == JobPosting.id)
    .where(
        JobPosting.tenant_id == self.tenant_id,
        Candidate.stage == CandidateStage.hired,
    )
    .order_by(Candidate.created_at.desc())
    .limit(5)
)
```

**Tables:** JobPosting, Candidate (multiple aggregation queries)

#### Tool 12: `add_candidate` (bonus)

```python
# 1. Verify job posting exists and belongs to tenant
# 2. Check duplicate by email within same posting
existing = await self.db.execute(
    select(Candidate).where(
        Candidate.job_posting_id == job_posting_id,
        func.lower(Candidate.email) == email.lower(),
    )
)
if existing.scalar_one_or_none():
    return json.dumps({"error": "Candidate with this email already exists for this posting.", ...})

# 3. Insert
candidate = Candidate(
    job_posting_id=job_posting_id,
    name=name,
    email=email,
    phone=phone,
    resume_url=resume_url,
    stage=CandidateStage.applied,
)
self.db.add(candidate)
await self.db.commit()
```

**Tables:** Candidate (INSERT), JobPosting (tenant check)

### 4.3 Recommended Indexes

```sql
-- Already exist via ForeignKey constraints (verify):
-- candidates.job_posting_id
-- job_postings.tenant_id
-- job_postings.department_id

-- New indexes for M1 performance:
CREATE INDEX ix_candidates_posting_score
    ON candidates(job_posting_id, ai_match_score DESC NULLS LAST);

CREATE INDEX ix_candidates_posting_stage
    ON candidates(job_posting_id, stage);

CREATE INDEX ix_job_postings_tenant_status
    ON job_postings(tenant_id, status);

CREATE INDEX ix_job_postings_tenant_created
    ON job_postings(tenant_id, created_at DESC);
```

---

## 5. Web Search Integration (M1-06)

### 5.1 API Choice

**Primary option: Tavily Search API**

- Purpose-built for AI agents (returns clean, structured results)
- $0.01 per search (cheap)
- Supports site-specific searches (e.g., `site:linkedin.com`)
- Python SDK: `tavily-python`

**Fallback option: SerpAPI or Google Custom Search**

- More expensive but more reliable for specific platform searches
- Google CSE: $5/1000 queries

**Stub mode for MVP:** If no search API key is configured, return a structured "search unavailable" response with platform links the user can visit manually. This ensures the tool exists and the demo flow works even without API keys.

### 5.2 Configuration

Add to `config.py`:

```python
# Web search (for recruitment sourcing)
tavily_api_key: str = ""  # empty = stub mode
```

### 5.3 Implementation

```python
async def _search_candidates_web(self, keywords: str, location: str, source: str) -> str:
    if not settings.tavily_api_key:
        return self._web_search_stub(keywords, location, source)

    # Build platform-specific queries
    queries = []
    platforms = {
        "linkedin": "site:linkedin.com/in",
        "bayt": "site:bayt.com/en/people",
        "naukrigulf": "site:naukrigulf.com",
    }

    if source == "all":
        for platform, site_prefix in platforms.items():
            queries.append(f"{site_prefix} {keywords} {location}")
    else:
        prefix = platforms.get(source, "")
        queries.append(f"{prefix} {keywords} {location}")

    # Execute searches (max 3 queries, 10 results total)
    from tavily import AsyncTavilyClient
    client = AsyncTavilyClient(api_key=settings.tavily_api_key)

    all_results = []
    for q in queries[:3]:
        try:
            response = await client.search(
                query=q,
                max_results=5,
                search_depth="basic",
            )
            for r in response.get("results", []):
                all_results.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("content", "")[:200],
                    "platform": _detect_platform(r.get("url", "")),
                    "relevance_note": r.get("relevance_score", ""),
                })
        except Exception as exc:
            logger.warning("Web search failed for query '%s': %s", q, exc)

    if not all_results:
        return json.dumps({
            "message": "No candidates found for these keywords. Try broadening your search.",
            "message_ar": "لم يتم العثور على مرشحين. حاول توسيع نطاق البحث.",
            "count": 0,
        })

    return json.dumps({
        "results": all_results[:10],
        "count": len(all_results[:10]),
        "guidance": "These are public profiles found online. Review them and add promising candidates to your pipeline.",
        "guidance_ar": "هذه ملفات شخصية عامة تم العثور عليها. راجعها وأضف المرشحين المناسبين لقائمتك.",
    })
```

### 5.4 Stub Mode

When `tavily_api_key` is empty, return direct search links:

```python
def _web_search_stub(self, keywords: str, location: str, source: str) -> str:
    encoded = urllib.parse.quote(f"{keywords} {location}")
    links = [
        {"platform": "LinkedIn", "url": f"https://www.linkedin.com/search/results/people/?keywords={encoded}"},
        {"platform": "Bayt.com", "url": f"https://www.bayt.com/en/search/?search_query={encoded}"},
        {"platform": "Naukrigulf", "url": f"https://www.naukrigulf.com/search?q={encoded}"},
        {"platform": "Jadarat", "url": "https://jadarat.sa"},
    ]
    return json.dumps({
        "message": "Web search is not configured. Use these direct links to search manually.",
        "message_ar": "البحث على الإنترنت غير مفعل. استخدم هذه الروابط للبحث يدوياً.",
        "search_links": links,
    })
```

### 5.5 Rate Limiting

- Max 3 searches per tool call (one per platform if `source="all"`)
- Max 5 results per platform query
- Total cap: 10 results returned to the user
- If rate limited by the API, return partial results with a note

---

## 6. Orchestrator Changes

### 6.1 New Keywords for Mohammad Routing

Current keywords in `orchestrator.py` line 44-47:

```python
"mohammad": [
    "hire", "recruit", "candidate", "resume", "interview", "job",
    "توظيف", "مرشح", "وظيفة", "مقابلة",
],
```

**Add these keywords:**

```python
"mohammad": [
    # Existing
    "hire", "recruit", "candidate", "resume", "interview", "job",
    "توظيف", "مرشح", "وظيفة", "مقابلة",
    # New for M1
    "posting", "pipeline", "screening", "screen", "shortlist",
    "jd", "job description", "applicant", "source", "sourcing",
    "وصف وظيفي", "مرشحين", "فحص", "تصفية", "إعلان وظيفي",
    "وش وضع التوظيف", "نبي نوظف", "خط التوظيف",
],
```

**Before adding, verify no conflicts with other agents' keyword lists.** The `_validate_keyword_uniqueness()` function at module level will catch conflicts at import time.

### 6.2 Handoff Mechanism

No changes to the handoff mechanism itself. Mohammad already exists in the `AGENTS` registry. The handoff UX is handled via:

1. `get_system_prompt()` override (M1-14) — detects `_handoff_from` and adjusts greeting
2. The orchestrator already sets `_handoff_from` and `_is_first_message` on agent instances

---

## 7. Seed Data Requirements

### 7.1 Job Postings (4 postings)

Create in `backend/scripts/seed_recruitment.py`:

| # | Title | Title AR | Department | Status | Salary Range | Created | Notes |
|---|-------|----------|------------|--------|-------------|---------|-------|
| 1 | Senior Software Engineer | مهندس برمجيات أول | Engineering | open | 22,000-35,000 SAR | 2026-02-15 | Old posting, 6 candidates. Demo Turn 3 target. |
| 2 | HR Business Partner | شريك أعمال الموارد البشرية | Human Resources | open | 18,000-28,000 SAR | 2026-03-20 | New posting, 2 candidates. |
| 3 | Data Analyst | محلل بيانات | Engineering | on_hold | 14,000-22,000 SAR | 2026-01-10 | On hold, 3 candidates. |
| 4 | Sales Executive | تنفيذي مبيعات | Sales | closed | 12,000-18,000 SAR | 2025-11-01 | Closed with 1 hired candidate. |

### 7.2 Candidates (12 candidates)

| # | Name | Email | Posting | Stage | AI Score | Notes |
|---|------|-------|---------|-------|----------|-------|
| 1 | Ahmed Al-Rashid | ahmed.r@email.com | Sr SW Eng | applied | null | Demo Turn 4 target — will be screened live |
| 2 | Sara Al-Dosari | sara.d@email.com | Sr SW Eng | screened | 85 | Strong match, has screening notes |
| 3 | Faisal Al-Otaibi | faisal.o@email.com | Sr SW Eng | shortlisted | 78 | Decent match |
| 4 | Nora Al-Qahtani | nora.q@email.com | Sr SW Eng | interview_scheduled | 91 | Top candidate |
| 5 | Khalid Al-Harbi | khalid.h@email.com | Sr SW Eng | screened | 62 | Below threshold |
| 6 | Maha Al-Zahrani | maha.z@email.com | Sr SW Eng | applied | null | Not screened yet |
| 7 | Omar Al-Ghamdi | omar.g@email.com | HR BP | applied | null | |
| 8 | Layla Al-Shammari | layla.s@email.com | HR BP | screened | 74 | |
| 9 | Turki Al-Mutairi | turki.m@email.com | Data Analyst | applied | null | |
| 10 | Reem Al-Anazi | reem.a@email.com | Data Analyst | screened | 80 | |
| 11 | Yousef Al-Dossary | yousef.d@email.com | Data Analyst | applied | null | |
| 12 | Haya Al-Salem | haya.s@email.com | Sales Exec | hired | 88 | Hired — for pipeline stats |

Candidate #1 (Ahmed Al-Rashid) is specifically designed for the demo: no AI score yet, so the live `screen_candidate` call will generate one.

### 7.3 AI Screening Notes (pre-seeded for candidates with scores)

For candidate #2 (Sara Al-Dosari, score 85):
```json
{
  "fit_score": 85,
  "strengths": ["5+ years Python/FastAPI experience", "Led team of 4 at Elm Company", "Bilingual (AR/EN)"],
  "gaps": ["No cloud certification", "Limited frontend experience"],
  "recommendation": "proceed_to_interview",
  "summary": "Strong backend engineer with Saudi tech company experience. Recommend interview."
}
```

For candidate #12 (Haya Al-Salem, hired, score 88):
```json
{
  "fit_score": 88,
  "strengths": ["7 years B2B sales in Saudi market", "Exceeded targets 3 consecutive years"],
  "gaps": ["No SaaS experience"],
  "recommendation": "proceed_to_interview",
  "summary": "Excellent sales professional with deep Saudi market knowledge. Hired."
}
```

### 7.4 Seed Script Location

`backend/scripts/seed_recruitment.py` — follows the pattern of `seed_demo_data.py`:

- Runs after `seed.py` and `seed_demo_data.py`
- Idempotent (checks if data exists before inserting)
- Uses existing tenant, department, and employee references
- Prints summary of seeded data

---

## 8. Files to Modify / Create

### 8.1 Files to Modify

| File | Changes |
|------|---------|
| `backend/app/agents/mohammad.py` | Complete rewrite: 14 tools, inner Claude calls, proactive context, system prompt override. ~600-800 lines. |
| `backend/app/agents/orchestrator.py` | Lines 44-47: expand Mohammad's keyword list (~15 new keywords). |
| `backend/app/config.py` | Add `tavily_api_key: str = ""` (~1 line, after line 20). |

### 8.2 Files to Create

| File | Purpose | Estimated Size |
|------|---------|---------------|
| `backend/scripts/seed_recruitment.py` | Seed recruitment demo data (4 postings, 12 candidates). | ~200 lines |
| `docs/mohammad_m1_architecture.md` | This document. | — |

### 8.3 Files NOT Modified (explicit)

- `backend/app/models/candidate.py` — No schema changes needed. Existing `JobPosting` and `Candidate` models are sufficient for M1.
- `backend/app/agents/base.py` — No changes. Inner call pattern is agent-local.
- `backend/app/database.py` — No changes.
- No new migration files — no schema changes.
- No new service files — logic stays in the agent (see section 3).

### 8.4 Detailed Change Map for `mohammad.py`

```
Lines 1-10:    Imports (add sqlalchemy, anthropic, logging, datetime, etc.)
Lines 11-30:   Class definition (unchanged header, updated personality)
Lines 31-250:  get_tools() — 14 tool definitions
Lines 251-290: handle_tool_call() — dispatch switch with UUID validation
Lines 291-330: get_system_prompt() override (M1-14)
Lines 331-370: get_proactive_context() override (M1-12)
Lines 371-400: Helper methods (_inner_claude_call, _format_salary, _get_candidate_with_posting)
Lines 401-450: _get_job_postings() (M1-01)
Lines 451-520: _get_job_posting() (M1-02)
Lines 521-570: _create_job_posting() (M1-03)
Lines 571-650: _generate_job_description() (M1-04) — includes inner Claude call
Lines 651-700: _extract_job_keywords() (M1-05) — includes inner Claude call
Lines 701-740: _search_candidates_web() (M1-06) — web search + stub
Lines 741-790: _view_candidates() (M1-07)
Lines 791-870: _screen_candidate() (M1-08) — includes inner Claude call
Lines 871-930: _update_candidate_stage() (M1-09)
Lines 931-1000: _schedule_interview() (M1-10)
Lines 1001-1070: _get_pipeline_summary() (M1-11)
Lines 1071-1110: _add_candidate() (bonus tool)
Lines 1111-1140: _search_employee() (reuse Waleed pattern)
```

---

## 9. Implementation Order

Based on dependencies and demo-critical priority:

| Order | Story | Tool | Rationale |
|-------|-------|------|-----------|
| 1 | — | Scaffold + helpers | Set up imports, `_inner_claude_call`, `_format_salary`, `_get_candidate_with_posting`, UUID validation in `handle_tool_call`. This is the foundation. |
| 2 | M1-13 | Error/empty patterns | Define all bilingual error/empty messages upfront as constants or helpers. Every tool will use these. |
| 3 | M1-01 | `get_job_postings` | First real DB query. Establishes tenant isolation pattern. |
| 4 | M1-02 | `get_job_posting` | Builds on M1-01 pattern. Needed for JD context. |
| 5 | M1-07 | `view_candidates` | Candidate listing — needed before screening. |
| 6 | M1-03 | `create_job_posting` | Write operation. Needed for JD generation. |
| 7 | M1-04 | `generate_job_description` | First inner Claude call. Demo "wow" moment. |
| 8 | M1-08 | `screen_candidate` | Second inner Claude call. Demo Turn 4 depends on this. |
| 9 | M1-09 | `update_candidate_stage` | Stage management. Needed for interview scheduling. |
| 10 | M1-10 | `schedule_interview` | Demo Turn 5 finale. |
| 11 | M1-11 | `get_pipeline_summary` | Aggregation queries. Demo Turn 1. |
| 12 | M1-05 | `extract_job_keywords` | Third inner Claude call. Feeds web search. |
| 13 | M1-06 | `search_candidates_web` | Web search. Can use stub mode. |
| 14 | M1-12 | Proactive context | Override `get_proactive_context()`. |
| 15 | M1-14 | System prompt + handoff | Override `get_system_prompt()`. Polish. |
| 16 | — | `add_candidate` + `search_employee` | Bonus tools for completeness. |
| 17 | — | Orchestrator keywords | Update `orchestrator.py` keyword list. |
| 18 | — | Seed script | `seed_recruitment.py` — can be done in parallel with any step. |

**Critical path for demo:** Steps 1-11 must be complete. Steps 12-18 are polish.

---

## 10. Saudi-Specific Design Decisions

### 10.1 Salary Formatting

All salary values stored as integers in SAR (already the case in `JobPosting.salary_min_sar` / `salary_max_sar`).

Display format: `"22,000 - 35,000 SAR"` (thousand separators, SAR suffix).

```python
def _format_salary(self, min_sar: int | None, max_sar: int | None) -> str:
    if min_sar is None and max_sar is None:
        return "Salary not specified / الراتب غير محدد"
    if min_sar and max_sar:
        return f"{min_sar:,} - {max_sar:,} SAR"
    if min_sar:
        return f"From {min_sar:,} SAR"
    return f"Up to {max_sar:,} SAR"
```

### 10.2 Weekend Detection

Saudi weekend is Friday (weekday=4) and Saturday (weekday=5). Python's `date.weekday()` returns 0=Monday through 6=Sunday.

```python
SAUDI_WEEKEND = {4, 5}  # Friday, Saturday

def _is_saudi_weekend(self, d: date) -> bool:
    return d.weekday() in SAUDI_WEEKEND
```

Used in `schedule_interview` (M1-10) — warn but do not block.

### 10.3 Saudization Awareness in JD Generation

The JD generation prompt (section 2.4) includes explicit Saudization context. The AI will include a `saudization_note` field in generated JDs explaining Nitaqat requirements for the role category.

This is not enforced at the data model level — it is part of the prompt engineering for the inner Claude call.

### 10.4 Bilingual Output Pattern

Every tool response follows this pattern:

```python
# Success with bilingual message
return json.dumps({
    "data": {...},
    "message": "English message",
    "message_ar": "رسالة عربية",
})

# Error with bilingual message
return json.dumps({
    "error": "English error",
    "error_ar": "خطأ بالعربي",
})

# Empty state with bilingual message
return json.dumps({
    "count": 0,
    "message": "No results found.",
    "message_ar": "لم يتم العثور على نتائج.",
})
```

This is consistent with Deema and Waleed's existing patterns. The outer Claude loop reads these JSON strings and formulates natural-language responses in the user's preferred language.

### 10.5 Stage Labels (Bilingual)

```python
STAGE_LABELS = {
    "applied": ("Applied", "تقدم للوظيفة"),
    "screened": ("Screened", "تم الفحص"),
    "shortlisted": ("Shortlisted", "في القائمة المختصرة"),
    "interview_scheduled": ("Interview Scheduled", "تم جدولة المقابلة"),
    "interviewed": ("Interviewed", "تمت المقابلة"),
    "offer_sent": ("Offer Sent", "تم إرسال العرض"),
    "hired": ("Hired", "تم التوظيف"),
    "rejected": ("Rejected", "مرفوض"),
    "withdrawn": ("Withdrawn", "انسحب"),
}
```

### 10.6 Posting Status Labels (Bilingual)

```python
STATUS_LABELS = {
    "draft": ("Draft", "مسودة"),
    "open": ("Open", "مفتوح"),
    "closed": ("Closed", "مغلق"),
    "on_hold": ("On Hold", "معلق"),
}
```

---

## 11. Open Questions for the CTO

1. **`add_candidate` tool — include or drop?** The stories do not explicitly ask for it, but without it there is no way to add candidates through chat. We could rely entirely on seed data for demos. My recommendation: include it — it is cheap to build and closes a real gap.

2. **Web search API key (Tavily vs alternatives)?** I recommend Tavily for its simplicity and AI-agent focus. But if we want to avoid a new dependency, the stub mode works fine for the demo (returns clickable links). Should Rania implement the full Tavily integration or just the stub for M1?

3. **Re-screening behavior.** M1-08 says if a candidate is already screened, show existing results and offer to re-screen. Should re-screening overwrite the previous score, or append to notes? My recommendation: overwrite the score, but preserve previous notes with a timestamp separator.

4. **Interview model.** M1-10 schedules interviews by updating the candidate stage, but does NOT create an Interview record (no Interview table exists). Should we add an `interviews` table in M1 for proper tracking, or defer to M2? My recommendation: defer to M2 — M1 "scheduling" is just a stage change + confirmation. M2 will need a proper interview lifecycle model.

5. **Tavily dependency.** Adding `tavily-python` to requirements. Acceptable? It is a small, well-maintained package. Alternative: use `httpx` directly with Tavily's REST API to avoid the dependency.
