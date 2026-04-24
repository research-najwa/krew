# Mohammad (محمد) — AI Recruitment Agent: Full Activation Plan

**Agent:** Mohammad (محمد) — Recruitment Operations Agent
**Product Owner:** Tariq
**Created:** 2026-03-25
**Last Updated:** 2026-03-25

---

## Vision

Mohammad is not a job board. He is not a database viewer. Mohammad is an **AI hiring department** — an agent that writes job descriptions with Saudi market intelligence, sources candidates from the open web, screens resumes with real analysis, conducts AI interviews, analyzes Zoom recordings, and closes the loop by handing hired candidates to Waleed for onboarding.

The activation happens in three phases:

| Phase | Name | What Mohammad Becomes | Stories |
|-------|------|----------------------|---------|
| **M1** | Core Pipeline + AI JD Writer + Web Search | A real recruiter who manages postings, screens candidates with AI, writes JDs, and searches for talent online | M1-01 through M1-14 |
| **M2** | AI Interviews + Assessments | An AI interviewer who conducts screening calls, generates assessments, scores candidates, and compares finalists | M2-01 through M2-05 |
| **M3** | Zoom Integration + Interview Analysis + Hiring | A full-cycle recruiter who analyzes Zoom recordings, recommends offers, hires candidates, and hands off to Waleed | M3-01 through M3-05 |

By M3 completion, a hiring manager can say "نبي مهندس برمجيات" and Mohammad will write the JD, post it, source candidates, screen them, interview them, analyze their Zoom calls, recommend an offer, mark them as hired, and trigger Waleed's onboarding flow. That is the product.

---

# Phase M1: Core Pipeline + AI JD Writer + Web Search

**Goal:** Replace all stub/hardcoded tools with real SQLAlchemy queries. Add AI-powered JD generation, keyword extraction, and web sourcing. Demo-ready in 5 turns.

**Estimated effort:** 8-10 implementation sessions
**Recommended build order:** M1-01 > M1-13 > M1-02 > M1-03 > M1-04 > M1-05 > M1-06 > M1-07 > M1-08 > M1-09 > M1-10 > M1-11 > M1-12 > M1-14

---

## M1-01: Wire `get_job_postings` to Real DB (P0 — Demo-Critical)

> As an HR manager, I want Mohammad to show real job postings from our database so that I can trust the data I see in chat.

**Tool:** `get_job_postings(department?, status?)`

**Acceptance Criteria:**

- [ ] Query `JobPosting` table with `tenant_id == self.tenant_id`
- [ ] Optional filter by `status` (PostingStatus enum value)
- [ ] Optional filter by department: join `Department` table on `department_id` and match by name (case-insensitive)
- [ ] Return list with: `id`, `title`, `title_ar`, `department` (name from join), `status`, `applicant_count` (count of related candidates), `salary_range` (formatted as "X,000 - Y,000 SAR"), `created_at`
- [ ] Sort by `created_at` descending (newest first)
- [ ] Limit to 20 results
- [ ] Empty state: "No job postings found matching your criteria." / "لا توجد وظائف شاغرة تطابق معايير البحث."
- [ ] Invalid status value: bilingual error listing valid options
- [ ] All responses via `json.dumps(...)` with bilingual keys

**Priority:** P0 (demo-blocking)
**Dependencies:** None — uses existing models
**Saudi-specific:** Salary in SAR with thousand separators, bilingual title/title_ar

---

## M1-02: New Tool — Get Job Posting Details (P0 — Demo-Critical)

> As an HR manager, I want to see full details of a specific job posting including its candidate breakdown so that I can assess how a role is progressing.

**Tool:** `get_job_posting(job_posting_id)`

**Acceptance Criteria:**

- [ ] Add tool definition to `get_tools()` with `job_posting_id` (required)
- [ ] Add dispatch in `handle_tool_call()` and private `_get_job_posting()` method
- [ ] Validate UUID with bilingual error
- [ ] Verify posting exists and belongs to `tenant_id`
- [ ] Return all fields: `id`, `title`, `title_ar`, `description`, `requirements`, `salary_min_sar`, `salary_max_sar`, `status`, `ai_readiness_score`, `created_at`
- [ ] Include `department` name (from join)
- [ ] Include `candidates_by_stage`: dict of stage -> count for this posting
- [ ] Include `total_candidates`: total count for this posting
- [ ] Include `top_candidates`: top 5 candidates by `ai_match_score` (descending), each with name, score, stage
- [ ] Salary formatted as range string: "X,000 - Y,000 SAR" (with thousand separators)
- [ ] If posting not found: "Job posting not found" / "الوظيفة غير موجودة"
- [ ] Null salary: "Salary not specified" / "الراتب غير محدد"

**Priority:** P0 (demo-blocking — investor Turn 2 depends on this)
**Dependencies:** M1-01 (tenant isolation pattern established)
**Saudi-specific:** Salary in SAR with proper formatting, bilingual title

---

## M1-03: New Tool — Create Job Posting (P0 — Demo-Critical)

> As an HR manager, I want to create a new job posting through chat so that I can open a role without leaving the conversation.

**Tool:** `create_job_posting(title, title_ar?, department?, description?, requirements?, salary_min?, salary_max?)`

**Acceptance Criteria:**

- [ ] Add tool definition to `get_tools()` with `title` (required), all others optional
- [ ] Add dispatch in `handle_tool_call()` and private `_create_job_posting()` method
- [ ] `title` is required; bilingual error if missing or empty
- [ ] If `department` provided as string name, look up `Department` by name (case-insensitive) under `tenant_id`; bilingual error if not found with list of valid departments
- [ ] If `salary_min` > `salary_max`, bilingual error: "Minimum salary cannot exceed maximum" / "الحد الأدنى للراتب لا يمكن أن يتجاوز الحد الأعلى"
- [ ] Default `status` to `draft` (new postings start as drafts)
- [ ] Create `JobPosting` record with `tenant_id = self.tenant_id`
- [ ] Return the created posting with all fields and a bilingual success message: "Job posting created successfully" / "تم إنشاء الإعلان الوظيفي بنجاح"
- [ ] Include a prompt in the response: "Would you like me to generate a full job description for this role?" / "هل تريدني أكتب وصف وظيفي كامل لهذه الوظيفة؟"
- [ ] Commit to DB within the tool (follow existing write patterns)

**Priority:** P0 (demo-critical — feeds into JD generation demo flow)
**Dependencies:** M1-01 (tenant isolation)
**Saudi-specific:** `title_ar` support, salary in SAR, department lookup

---

## M1-04: New Tool — AI Job Description Generator (P0 — Demo-Critical)

> As an HR manager, I want Mohammad to write a professional job description for me so that I can post high-quality bilingual JDs without spending hours writing them.

**Tool:** `generate_job_description(role_title, department?, seniority?, language?, auto_create_posting?)`

**Acceptance Criteria:**

- [ ] Add tool definition to `get_tools()` with `role_title` (required), `department` (optional), `seniority` (optional: "junior", "mid", "senior", "lead", "executive"), `language` (optional: "en", "ar", "both"; default "both"), `auto_create_posting` (optional boolean, default false)
- [ ] Add dispatch in `handle_tool_call()` and private `_generate_job_description()` method
- [ ] Use Claude (via Anthropic SDK inner call or prompt-within-tool pattern) to generate the JD
- [ ] The generation prompt MUST include Saudi market context:
  - Saudization/Nitaqat requirements for the role category
  - GOSI compliance note (employer covers 12% contribution)
  - Typical Saudi salary benchmarks for the seniority level
  - Saudi work week (Sun-Thu) and standard benefits (medical insurance per CCHI, annual leave per Labor Law Article 109)
- [ ] Output structure: `title`, `title_ar`, `summary`, `summary_ar`, `responsibilities` (list), `responsibilities_ar` (list), `requirements` (list), `requirements_ar` (list), `nice_to_have` (list), `nice_to_have_ar` (list), `salary_range_suggestion` (dict with `min` and `max` in SAR), `saudization_note`
- [ ] If `language` is "en", omit Arabic fields; if "ar", omit English fields; if "both", include all
- [ ] If `auto_create_posting` is true, also create a `JobPosting` record in the DB using the generated content and return the posting ID
- [ ] Response includes bilingual success: "Job description generated" / "تم إنشاء الوصف الوظيفي"
- [ ] Handle inner-call failures gracefully with bilingual error

**Priority:** P0 (demo-critical — this is the "wow" moment, the first tool where Mohammad uses AI to create, not just query)
**Dependencies:** M1-03 (if auto_create_posting is used)
**Saudi-specific:** Saudization notes, GOSI, CCHI, Saudi Labor Law references, salary in SAR, bilingual output

---

## M1-05: New Tool — Extract Job Keywords (P1)

> As an HR manager, I want to extract searchable keywords from a job description so that I can use them to source candidates on job platforms.

**Tool:** `extract_job_keywords(job_posting_id?, description_text?)`

**Acceptance Criteria:**

- [ ] Add tool definition to `get_tools()` with `job_posting_id` (optional) and `description_text` (optional); at least one required
- [ ] Add dispatch in `handle_tool_call()` and private `_extract_job_keywords()` method
- [ ] If `job_posting_id` provided, fetch the posting's description and requirements from DB (validate UUID, tenant isolation)
- [ ] If `description_text` provided, use it directly
- [ ] If neither provided, bilingual error: "Please provide a job posting ID or description text" / "يرجى تقديم معرف الوظيفة أو نص الوصف الوظيفي"
- [ ] Use Claude to extract: `technical_skills` (list), `soft_skills` (list), `certifications` (list), `experience_keywords` (list), `search_strings` (list of 3-5 optimized search queries for job platforms)
- [ ] Return keywords in both English and Arabic where applicable
- [ ] Include `platform_suggestions`: which Saudi job platforms are best for this role type (Bayt.com for general, LinkedIn for professional, Naukrigulf for expat roles, Jadarat for Saudi nationals)

**Priority:** P1 (feeds into web search, but not demo-blocking)
**Dependencies:** M1-02 (posting detail fetch)
**Saudi-specific:** Platform suggestions specific to Saudi market, Jadarat for Saudization compliance

---

## M1-06: New Tool — Web Search for Candidates (P1)

> As an HR manager, I want Mohammad to search the web for potential candidates so that I can source talent beyond our existing applicant pool.

**Tool:** `search_candidates_web(keywords, location?, source?)`

**Acceptance Criteria:**

- [ ] Add tool definition to `get_tools()` with `keywords` (required string or list), `location` (optional, default "Saudi Arabia"), `source` (optional: "linkedin", "bayt", "naukrigulf", "all"; default "all")
- [ ] Add dispatch in `handle_tool_call()` and private `_search_candidates_web()` method
- [ ] Construct search queries targeting the specified platforms
- [ ] Use a web search API (or Claude's web search tool if available) to find candidate profiles
- [ ] Return results as a list: `name` (if visible), `title`, `url`, `platform`, `snippet`, `relevance_note`
- [ ] Limit to 10 results per search
- [ ] Include bilingual guidance: "These are public profiles found online. Review them and add promising candidates to your pipeline." / "هذه ملفات شخصية عامة تم العثور عليها. راجعها وأضف المرشحين المناسبين لقائمتك."
- [ ] If no results found, bilingual empty state with suggestions to broaden keywords
- [ ] Handle API failures gracefully with bilingual error

**Priority:** P1 (impressive for demo but not blocking core pipeline)
**Dependencies:** M1-05 (keyword extraction feeds better search queries)
**Saudi-specific:** Default location Saudi Arabia, Saudi job platform awareness (Bayt.com, Naukrigulf, Jadarat)

---

## M1-07: Wire `view_candidates` to Real DB (P0 — Demo-Critical)

> As an HR manager, I want to see all candidates for a job posting so that I can review the pipeline at a glance.

**Tool:** `view_candidates(job_posting_id?, stage?)`

**Acceptance Criteria:**

- [ ] Add tool definition to `get_tools()` with `job_posting_id` (optional) and `stage` (optional, enum of CandidateStage values)
- [ ] Add dispatch in `handle_tool_call()` and private `_view_candidates()` method
- [ ] If `job_posting_id` provided: validate UUID, verify posting exists under `tenant_id`
- [ ] If `job_posting_id` provided: filter candidates by that posting
- [ ] If `job_posting_id` not provided: return all candidates across all postings for `tenant_id` (join through JobPosting for tenant isolation)
- [ ] If `stage` provided: validate against CandidateStage enum, filter accordingly
- [ ] If invalid stage: bilingual error listing valid stage values
- [ ] Return list with: `id`, `name`, `email`, `stage`, `ai_match_score`, `applied_date` (created_at), `job_title` (from posting join)
- [ ] Sort by `created_at` descending
- [ ] Limit to 50 results
- [ ] Include summary: `total_count`, `showing` (in case of limit)
- [ ] Empty state: "No candidates found" / "لا يوجد مرشحون" with context (e.g., "for this posting" / "in this stage")
- [ ] Null `ai_match_score` displayed as "Not screened" / "لم يتم الفحص"

**Priority:** P0 (demo-blocking — investor Turn 3 depends on this)
**Dependencies:** M1-01 (tenant-isolated posting queries)
**Saudi-specific:** None beyond bilingual output

---

## M1-08: Wire `screen_candidate` to Real DB + AI Analysis (P0 — Demo-Critical)

> As an HR manager, I want Mohammad to analyze a candidate's resume against the job requirements using AI — not just return a number from the database, but actually reason about the fit.

**Tool:** `screen_candidate(candidate_id, job_posting_id)`

**Acceptance Criteria:**

- [ ] Validate both UUIDs with bilingual error on invalid format
- [ ] Look up `Candidate` by id, verify its `job_posting_id` matches (or allow cross-posting screening)
- [ ] Look up `JobPosting` by id, verify `tenant_id == self.tenant_id`
- [ ] Return candidate not found / posting not found bilingual errors if either is missing
- [ ] Use Claude (inner call) to analyze the candidate's profile against the JD requirements
- [ ] The AI analysis prompt should evaluate: skills match, experience relevance, education fit, potential red flags, culture fit indicators
- [ ] Generate and store `ai_match_score` (0-100) on the `Candidate` record
- [ ] Generate and store `ai_screening_notes` on the `Candidate` record (structured text with strengths, gaps, recommendation)
- [ ] Update candidate `stage` from `applied` to `screened` (only if currently `applied`)
- [ ] Return: candidate `name`, `email`, `stage`, `ai_match_score`, `ai_screening_notes`, `resume_url`, job posting `title`, and recommendation
- [ ] Recommendation thresholds: >= 80 "proceed_to_interview" / "يوصى بالمقابلة", 60-79 "review_further" / "يحتاج مراجعة إضافية", < 60 "likely_not_a_fit" / "غير مناسب على الأرجح"
- [ ] If candidate has already been screened (score exists), return existing results with note: "This candidate was already screened" / "تم فحص هذا المرشح مسبقاً" and offer to re-screen
- [ ] If `resume_url` is null, note it in the analysis: "No resume on file — screening based on profile data only" / "لا يوجد سيرة ذاتية — الفحص بناء على بيانات الملف فقط"

**Priority:** P0 (demo-critical — AI screening is a key differentiator)
**Dependencies:** M1-01, M1-02
**Saudi-specific:** Saudi qualification recognition (e.g., Saudi universities, professional certifications recognized by Saudi authorities)

---

## M1-09: New Tool — Update Candidate Stage (P0 — Demo-Critical)

> As an HR manager, I want to move a candidate through the pipeline stages so that our recruitment tracking stays current.

**Tool:** `update_candidate_stage(candidate_id, new_stage, notes?)`

**Acceptance Criteria:**

- [ ] Add tool definition to `get_tools()` with `candidate_id` (required), `new_stage` (required, enum of CandidateStage values), `notes` (optional string)
- [ ] Add dispatch in `handle_tool_call()` and private `_update_candidate_stage()` method
- [ ] Validate `candidate_id` UUID with bilingual error
- [ ] Verify candidate exists (via posting join for tenant isolation)
- [ ] Validate `new_stage` against CandidateStage enum; bilingual error on invalid value listing all valid stages
- [ ] Validate stage transition is logical:
  - Cannot move from `hired` to any earlier stage
  - Cannot move from `withdrawn` to any stage
  - Cannot move from `rejected` to any stage except `applied` (re-open candidacy)
  - All other transitions are allowed (forward and limited backward)
- [ ] If invalid transition: bilingual error explaining why (e.g., "Cannot move a hired candidate back to screening" / "لا يمكن إرجاع مرشح تم توظيفه إلى مرحلة الفحص")
- [ ] If `notes` provided, append to `ai_screening_notes` with timestamp prefix: `[2026-03-25 14:30] note text`
- [ ] Update the candidate's `stage` column
- [ ] Return: candidate `name`, previous stage, new stage, job posting title, and timestamp
- [ ] Bilingual success: "Stage updated successfully" / "تم تحديث المرحلة بنجاح"
- [ ] Include bilingual labels for both the old and new stages

**Priority:** P0 (demo-blocking — investor Turn 4 depends on this)
**Dependencies:** M1-01
**Saudi-specific:** None beyond bilingual output

---

## M1-10: Wire `schedule_interview` to Real DB (P0 — Demo-Critical)

> As an HR manager, I want to schedule an interview for a candidate with Saudi weekend awareness so that interviews are never accidentally booked on Friday or Saturday.

**Tool:** `schedule_interview(candidate_id, job_posting_id, interviewer_ids, proposed_date, proposed_time?, interview_type?)`

**Acceptance Criteria:**

- [ ] Validate all UUIDs (candidate_id, job_posting_id, each interviewer_id) with bilingual errors
- [ ] Verify candidate exists and belongs to a posting under `tenant_id`
- [ ] Verify job posting exists and belongs to `tenant_id`
- [ ] Validate `proposed_date` is a valid date in YYYY-MM-DD format, not in the past
- [ ] Validate `proposed_date` does not fall on Friday or Saturday (Saudi weekend) — warn but allow override with bilingual warning: "This date falls on the Saudi weekend (Fri-Sat). Are you sure?" / "هذا التاريخ يوافق عطلة نهاية الأسبوع (الجمعة-السبت). هل أنت متأكد؟"
- [ ] If `proposed_time` provided, validate HH:MM 24h format
- [ ] Default `interview_type` to "video" if not provided; valid types: "phone", "video", "onsite", "panel"
- [ ] Update candidate `stage` to `interview_scheduled` (if currently in an earlier stage)
- [ ] If candidate stage is already `interviewed`, `offer_sent`, `hired`, or `rejected`: return bilingual error "Candidate has already progressed past the interview stage" / "المرشح تجاوز مرحلة المقابلة بالفعل"
- [ ] Return confirmation with: candidate name, job title, date, time, interview type, interviewers count
- [ ] Bilingual response: "Interview scheduled successfully" / "تم جدولة المقابلة بنجاح"

**Priority:** P0 (demo-blocking — investor Turn 5 depends on this)
**Dependencies:** M1-01, M1-09
**Saudi-specific:** Friday-Saturday weekend detection (not Sat-Sun), date validation against Saudi public holidays (Eid al-Fitr, Eid al-Adha, Saudi National Day Sep 23, Founding Day Feb 22)

---

## M1-11: New Tool — Get Pipeline Summary (P0 — Demo-Critical)

> As an HR manager, I want a dashboard summary of our entire recruitment pipeline so that I can report on hiring progress to leadership.

**Tool:** `get_pipeline_summary()`

**Acceptance Criteria:**

- [ ] Add tool definition to `get_tools()` with no required parameters
- [ ] Add dispatch in `handle_tool_call()` and private `_get_pipeline_summary()` method
- [ ] Query all `JobPosting` records for `tenant_id`
- [ ] Return `total_open_positions`: count of postings with status `open`
- [ ] Return `total_postings_by_status`: dict of status -> count (e.g., `{"open": 5, "closed": 3, "draft": 2, "on_hold": 1}`)
- [ ] Query all `Candidate` records (via posting join for tenant isolation)
- [ ] Return `total_candidates`: total count
- [ ] Return `candidates_by_stage`: dict of stage -> count (only stages with > 0 candidates)
- [ ] Return `avg_time_to_hire_days`: average days between `created_at` and reaching `hired` stage, across all hired candidates. Null if no hired candidates.
- [ ] Return `recent_hires`: last 5 candidates with stage `hired`, showing name, job title, and hire date
- [ ] Return `stale_postings`: postings open > 30 days with < 5 candidates (flag as needing more sourcing)
- [ ] Empty state: "No recruitment activity yet. Create a job posting to get started." / "لا يوجد نشاط توظيف بعد. أنشئ إعلان وظيفي للبدء."
- [ ] All counts must respect tenant isolation

**Priority:** P0 (demo-blocking — investor Turn 1 depends on this)
**Dependencies:** M1-01 (tenant isolation pattern)
**Saudi-specific:** None beyond bilingual output

---

## M1-12: Proactive Context Override (P1)

> As an HR manager, I want Mohammad to greet me with a recruitment summary so that I immediately know the state of our hiring pipeline when I open the chat.

**Acceptance Criteria:**

- [ ] Override `get_proactive_context(self, employee_id: str) -> str | None` in `MohammadAgent`
- [ ] Count open positions for tenant: "You have X open position(s)."
- [ ] Count candidates in `applied` stage (awaiting screening): "Y candidate(s) awaiting screening."
- [ ] Count candidates in `interview_scheduled` stage: "Z interview(s) coming up."
- [ ] If any posting has been `open` for > 30 days with < 5 candidates: flag it as "Position [title] may need more sourcing."
- [ ] If any candidates have been in `screened` stage for > 7 days without progressing: flag as "X candidate(s) screened but not yet shortlisted — review recommended."
- [ ] Return None if no recruitment data exists (never crash)
- [ ] Wrap all DB queries in try/except, log warnings, return None on failure
- [ ] Context string format: `"\n\nProactive context for this employee:\n- item1\n- item2"`

**Priority:** P1 (important for first impression, but not blocking core tools)
**Dependencies:** M1-01 (needs real DB queries)
**Saudi-specific:** None

---

## M1-13: Bilingual Empty States + Error Polish (P0 — Demo-Critical)

> As a user, I want all of Mohammad's responses to have friendly bilingual messages when there is no data or an error occurs, so the experience feels polished and complete.

**Acceptance Criteria:**

Empty states (all must include `message` and `message_ar` keys):
- [ ] `get_job_postings` (no results): "No job postings found matching your criteria." / "لا توجد وظائف شاغرة تطابق معايير البحث."
- [ ] `get_job_posting` (not found): "Job posting not found." / "الوظيفة غير موجودة."
- [ ] `view_candidates` (no results): "No candidates found for this posting." / "لا يوجد مرشحون لهذه الوظيفة."
- [ ] `get_pipeline_summary` (no data): "No recruitment activity yet. Create a job posting to get started." / "لا يوجد نشاط توظيف بعد. أنشئ إعلان وظيفي للبدء."
- [ ] `screen_candidate` (no AI score yet): "No AI screening performed yet." / "لم يتم إجراء فحص ذكي بعد."
- [ ] `search_candidates_web` (no results): "No candidates found for these keywords. Try broadening your search." / "لم يتم العثور على مرشحين. حاول توسيع نطاق البحث."

Error states (all must include `error` and `error_ar` keys):
- [ ] Invalid UUID: bilingual error with suggestion to use name or re-check ID
- [ ] Candidate not found: "Candidate not found" / "المرشح غير موجود"
- [ ] Posting not found: "Job posting not found" / "الوظيفة غير موجودة"
- [ ] Invalid stage value: bilingual error listing all valid stages
- [ ] Invalid status value: bilingual error listing all valid statuses
- [ ] Invalid date format: bilingual error showing correct format "YYYY-MM-DD"
- [ ] Past date for interview: "Cannot schedule an interview in the past" / "لا يمكن جدولة مقابلة في الماضي"
- [ ] Weekend date for interview: warning (not blocking error) in both languages
- [ ] Generic unknown tool: bilingual error with fallback
- [ ] Salary min > max: "Minimum salary cannot exceed maximum" / "الحد الأدنى للراتب لا يمكن أن يتجاوز الحد الأعلى"

Pattern requirements:
- [ ] All tool responses use `json.dumps(...)`
- [ ] All errors include both `error` and `error_ar` keys
- [ ] All empty states include both `message` and `message_ar` keys
- [ ] Follow exact pattern from Waleed's implementation
- [ ] Arabic messages use natural, professional tone — not robotic machine translation

**Priority:** P0 (demo-blocking — bad error messages break the illusion)
**Dependencies:** M1-01 through M1-11 (applies to all tools)
**Saudi-specific:** Arabic messages reviewed for natural Saudi professional tone

---

## M1-14: System Prompt Override + Handoff Awareness (P1)

> As a user, I want Mohammad to respond with a recruiter's personality — sharp, data-driven, no fluff — and to be aware when he receives a handoff from another agent.

**Acceptance Criteria:**

- [ ] Override `get_system_prompt()` in `MohammadAgent`
- [ ] System prompt includes Mohammad's personality: sharp, results-driven, data-focused, direct but professional
- [ ] System prompt includes awareness of the recruitment pipeline and available tools
- [ ] System prompt includes Saudi HR context: Saudization awareness, Saudi weekend (Fri-Sat), SAR currency, bilingual expectations
- [ ] If `_handoff_from` attribute is set (agent handoff), acknowledge the handoff naturally: e.g., if from Sarah (Agent Factory): "Sarah determined this role needs a human hire. Let me handle the recruitment."
- [ ] If `_is_first_message` is true, use proactive context to lead with pipeline summary
- [ ] System prompt instructs Mohammad to always provide data to back recommendations (scores, counts, percentages)
- [ ] System prompt instructs Mohammad to suggest next steps proactively (e.g., after viewing candidates: "Want me to screen the top applicants?")

**Priority:** P1 (polish, but important for personality)
**Dependencies:** M1-12 (proactive context)
**Saudi-specific:** Saudi HR terminology, Saudization awareness in system prompt

---

# Phase M1 Demo Script — Investor Presentation

## Scene: HR Manager Hires a Software Engineer (Arabic, 3 minutes)

### Turn 1: Dashboard overview
- **User:** "محمد، وش وضع التوظيف عندنا؟"
- **Expected:** Mohammad calls `get_pipeline_summary()` and presents: open positions, total candidates, breakdown by stage, recent hires, stale postings.
- **Wow factor:** Instant data-driven overview. Proactive context fires on first message.

### Turn 2: Create a new role with AI
- **User:** "نبي نوظف مهندس برمجيات أول، اكتب لي وصف وظيفي"
- **Expected:** Mohammad calls `generate_job_description(role_title="Senior Software Engineer", seniority="senior", language="both", auto_create_posting=true)`. Returns a full bilingual JD with Saudi market salary benchmarks, Saudization note, and GOSI compliance. Auto-creates the posting.
- **Wow factor:** AI writes a complete bilingual JD with Saudi labor context in seconds. The posting is already saved.

### Turn 3: Drill into a posting with candidates
- **User:** "عطني تفاصيل وظيفة مهندس البرمجيات القديمة"
- **Expected:** Mohammad calls `get_job_posting(job_posting_id)` for the existing posting (not the one just created). Shows full details, candidate breakdown by stage, top candidates by AI score.
- **Wow factor:** Rich posting detail with candidate funnel visualization.

### Turn 4: Screen a candidate with AI
- **User:** "افحص لي أحمد على هالوظيفة"
- **Expected:** Mohammad calls `screen_candidate(candidate_id, job_posting_id)`. Returns AI analysis: strengths, gaps, match score, recommendation.
- **Wow factor:** AI actually analyzes the candidate — not just a database lookup. Stores the score.

### Turn 5: Schedule the interview
- **User:** "ممتاز، جدول له مقابلة يوم الأحد الجاي الساعة ١٠"
- **Expected:** Mohammad calls `schedule_interview(...)` with the correct date and time. Updates candidate stage. Detects it is not a weekend day.
- **Wow factor:** Weekend detection, stage update, bilingual confirmation.

### Demo Prerequisites
- [ ] Seed data: at least 3 job postings (1 open with 5+ candidates at various stages, 1 open with few candidates, 1 closed with hired candidates)
- [ ] Seed data: at least 10 candidates across postings with varying stages and AI match scores
- [ ] Seed data: at least 1 hired candidate (for avg time-to-hire stat)
- [ ] Seed data: departments that match posting department_ids
- [ ] All M1 tools return real DB data (M1-01 through M1-11 complete)
- [ ] Bilingual output polished (M1-13 complete)
- [ ] Proactive context fires on first message (M1-12 complete)
- [ ] AI JD generation working (M1-04 complete)
- [ ] AI candidate screening working (M1-08 complete)

---

# Phase M2: AI Interviews + Assessments

**Goal:** Mohammad becomes an AI interviewer — conducts screening interviews via chat, generates role-specific assessments, scores candidates with structured rubrics, and compares finalists side by side.

**Estimated effort:** 5-6 implementation sessions
**Prerequisite:** M1 complete

---

## M2-01: Start AI Screening Interview (P0 — Demo-Critical for M2)

> As an HR manager, I want Mohammad to conduct an AI screening interview with a candidate so that I can evaluate candidates without scheduling human interviewer time for initial rounds.

**Tool:** `start_screening_interview(candidate_id, job_posting_id)`

**Acceptance Criteria:**

- [ ] Add tool definition to `get_tools()` with `candidate_id` (required) and `job_posting_id` (required)
- [ ] Add dispatch in `handle_tool_call()` and private `_start_screening_interview()` method
- [ ] Validate both UUIDs with bilingual errors; verify tenant isolation
- [ ] Verify candidate exists and is in an appropriate stage (`screened` or `shortlisted`)
- [ ] If candidate is in wrong stage: bilingual error "Candidate must be screened before interviewing" / "يجب فحص المرشح قبل المقابلة"
- [ ] Fetch the `JobPosting` description and requirements
- [ ] Use Claude to generate 5-7 role-specific interview questions based on:
  - The JD requirements
  - The candidate's profile and resume
  - A mix of technical, behavioral, and situational questions
  - At least 1 Saudi culture/work-environment question (e.g., team collaboration in Saudi workplace norms)
- [ ] Return the first question along with interview metadata: `interview_id` (generated), `total_questions`, `question_1`
- [ ] Store the interview state (question list, candidate answers as they come) in a session or DB table
- [ ] Update candidate stage to `interview_scheduled` if not already
- [ ] Subsequent conversation turns are treated as candidate answers — Mohammad asks the next question, probes deeper, and eventually wraps up
- [ ] Bilingual opening: "Let's begin the screening interview for [candidate] for the [role] position." / "لنبدأ المقابلة الأولية لـ [مرشح] على وظيفة [الدور]."

**Priority:** P0 (the core M2 feature)
**Dependencies:** M1-08 (candidate must be screened first)
**Saudi-specific:** Include Saudi workplace culture questions, awareness of bilingual candidates

---

## M2-02: Generate Role Assessment (P1)

> As an HR manager, I want Mohammad to generate a structured assessment for a role so that I can evaluate candidates with consistent, fair criteria.

**Tool:** `generate_assessment(job_posting_id, assessment_type)`

**Acceptance Criteria:**

- [ ] Add tool definition with `job_posting_id` (required) and `assessment_type` (required: "technical", "behavioral", "situational", "culture_fit")
- [ ] Add dispatch and private `_generate_assessment()` method
- [ ] Validate UUID and tenant isolation
- [ ] Fetch JD description and requirements from the posting
- [ ] Use Claude to generate an assessment:
  - **Technical:** 8-10 questions testing hard skills from the JD, with expected answers and scoring rubric (1-5 scale)
  - **Behavioral:** 6-8 STAR-method questions targeting competencies from the JD, with evaluation criteria
  - **Situational:** 5-7 scenario-based questions relevant to the role and Saudi business context
  - **Culture_fit:** 5-6 questions about work style, team dynamics, values alignment, Saudi workplace norms
- [ ] Each question includes: `question`, `question_ar`, `expected_answer_guidance`, `scoring_rubric`, `max_score`
- [ ] Return total possible score and passing threshold (70%)
- [ ] Bilingual output for all questions
- [ ] Include assessment metadata: `role`, `type`, `total_questions`, `total_possible_score`, `generated_at`

**Priority:** P1 (valuable but not demo-blocking)
**Dependencies:** M1-02 (posting details)
**Saudi-specific:** Situational questions include Saudi business scenarios; culture fit includes Saudi workplace norms

---

## M2-03: Score Interview (P0 — Demo-Critical for M2)

> As an HR manager, I want Mohammad to score an interview based on notes or transcript so that I get a structured, objective evaluation instead of gut feelings.

**Tool:** `score_interview(candidate_id, interview_notes)`

**Acceptance Criteria:**

- [ ] Add tool definition with `candidate_id` (required) and `interview_notes` (required, string — raw notes or transcript)
- [ ] Add dispatch and private `_score_interview()` method
- [ ] Validate UUID and tenant isolation
- [ ] Fetch the candidate's associated job posting for context
- [ ] Use Claude to analyze the interview notes and produce a structured scorecard:
  - `technical_depth`: score (1-10) + justification
  - `communication_skills`: score (1-10) + justification
  - `problem_solving`: score (1-10) + justification
  - `culture_fit`: score (1-10) + justification
  - `leadership_potential`: score (1-10) + justification (if senior role)
  - `red_flags`: list of concerns with severity (low/medium/high)
  - `strengths`: top 3 strengths observed
  - `overall_score`: weighted average (0-100)
  - `recommendation`: "strong_hire" / "hire" / "no_hire" / "strong_no_hire" with bilingual labels
  - `summary`: 2-3 sentence overall assessment in both languages
- [ ] Store the scorecard in `ai_screening_notes` on the Candidate record (append, don't overwrite)
- [ ] Update `ai_match_score` with the overall score
- [ ] Bilingual output for all fields

**Priority:** P0 (key M2 demo moment)
**Dependencies:** M2-01 (produces interview data to score)
**Saudi-specific:** Culture fit scoring considers Saudi workplace dynamics

---

## M2-04: Compare Candidates Side by Side (P1)

> As an HR manager, I want to compare 2-3 finalists for the same role side by side so that I can make a data-driven hiring decision.

**Tool:** `compare_candidates(candidate_ids, job_posting_id)`

**Acceptance Criteria:**

- [ ] Add tool definition with `candidate_ids` (required, list of 2-5 UUIDs) and `job_posting_id` (required)
- [ ] Add dispatch and private `_compare_candidates()` method
- [ ] Validate all UUIDs, verify all candidates belong to the same posting, tenant isolation
- [ ] If candidates belong to different postings: bilingual error
- [ ] If fewer than 2 candidates: bilingual error "Need at least 2 candidates to compare" / "يجب اختيار مرشحين اثنين على الأقل للمقارنة"
- [ ] Fetch each candidate's `ai_match_score`, `ai_screening_notes`, `stage`
- [ ] Use Claude to generate a comparison:
  - Side-by-side score breakdown (if scored)
  - Strengths and gaps for each candidate relative to the role
  - Head-to-head on key requirements from the JD
  - Risk assessment for each candidate
  - Final ranking with justification
  - Recommended candidate with confidence level (high/medium/low)
- [ ] Output as structured comparison table + narrative recommendation
- [ ] Bilingual output for recommendation and summary
- [ ] If any candidate has not been screened: note it as a gap in the comparison

**Priority:** P1 (valuable for decision-making, strong demo material)
**Dependencies:** M1-08 (candidates need screening scores), M2-03 (interview scores make comparison richer)
**Saudi-specific:** Consider Saudization preference in recommendation if applicable

---

## M2-05: Generate Interview Questions (P2)

> As an HR manager preparing for a panel interview, I want Mohammad to generate targeted interview questions for a specific role so that my interview panel has structured, relevant questions ready.

**Tool:** `generate_interview_questions(job_posting_id, question_type?, count?)`

**Acceptance Criteria:**

- [ ] Add tool definition with `job_posting_id` (required), `question_type` (optional: "technical", "behavioral", "star_method", "culture_fit"; default "behavioral"), `count` (optional integer, default 7, max 15)
- [ ] Add dispatch and private `_generate_interview_questions()` method
- [ ] Validate UUID and tenant isolation
- [ ] Fetch JD from posting
- [ ] Use Claude to generate questions:
  - Each question includes: `question`, `question_ar`, `what_to_look_for`, `follow_up_probes` (list of 2-3 follow-up questions)
  - Questions are tailored to the specific JD requirements
  - STAR-method questions include the expected Situation-Task-Action-Result framework guidance
- [ ] Return questions grouped by category if mixed types
- [ ] Include interviewer guidance: time allocation per question, overall interview duration suggestion
- [ ] Bilingual output

**Priority:** P2 (nice-to-have, helps human interviewers)
**Dependencies:** M1-02 (posting details)
**Saudi-specific:** Include culture-fit questions relevant to Saudi workplace

---

# Phase M2 Demo Script — AI Interview Showcase

## Scene: Mohammad Interviews a Candidate (Arabic, 3 minutes)

### Turn 1: Start the screening interview
- **User:** "محمد، ابدأ مقابلة أولية مع سارة على وظيفة مهندس البرمجيات"
- **Expected:** Mohammad calls `start_screening_interview(candidate_id, job_posting_id)`. Returns first question tailored to the JD.
- **Wow factor:** AI generates role-specific questions on the fly.

### Turn 2: Candidate answers (simulated)
- **User:** (provides answer text as if from candidate)
- **Expected:** Mohammad evaluates the answer, asks follow-up or moves to next question.
- **Wow factor:** Adaptive interview — probes deeper on weak answers, moves on when satisfied.

### Turn 3: Score the interview
- **User:** "قيّم المقابلة"
- **Expected:** Mohammad calls `score_interview()` with the full conversation. Returns structured scorecard.
- **Wow factor:** Objective, structured evaluation with scores, strengths, red flags.

### Turn 4: Compare finalists
- **User:** "قارن لي سارة وأحمد وخالد"
- **Expected:** Mohammad calls `compare_candidates([sarah_id, ahmed_id, khalid_id], job_posting_id)`. Returns side-by-side analysis with ranking.
- **Wow factor:** Data-driven hiring decision support.

---

# Phase M3: Zoom Integration + Interview Analysis + Hiring

**Goal:** Mohammad analyzes real interview recordings from Zoom/Teams, generates offer recommendations based on all data, hires candidates, and hands them off to Waleed for onboarding. This closes the full recruitment lifecycle.

**Estimated effort:** 5-7 implementation sessions
**Prerequisite:** M2 complete

---

## M3-01: Analyze Interview Recording/Transcript (P0 — Demo-Critical for M3)

> As an HR manager, I want Mohammad to analyze a Zoom or Teams interview recording transcript so that I get structured feedback without rewatching the entire recording.

**Tool:** `analyze_interview_recording(candidate_id, transcript_text?, recording_url?)`

**Acceptance Criteria:**

- [ ] Add tool definition with `candidate_id` (required), `transcript_text` (optional string), `recording_url` (optional string); at least one of transcript/URL required
- [ ] Add dispatch and private `_analyze_interview_recording()` method
- [ ] Validate UUID and tenant isolation
- [ ] If `transcript_text` provided, use it directly
- [ ] If `recording_url` provided, fetch and extract transcript (integration with transcription service — Zoom API, Whisper, or similar)
- [ ] If neither provided: bilingual error "Please provide a transcript or recording URL" / "يرجى تقديم نص المقابلة أو رابط التسجيل"
- [ ] Use Claude to analyze the transcript and produce:
  - `answer_quality`: per-question breakdown (if questions are identifiable) with scores (1-10)
  - `communication_skills`: clarity, articulation, confidence assessment
  - `confidence_indicators`: moments of strong confidence vs hesitation, with approximate timestamps or section references
  - `technical_accuracy`: assessment of technical claims and answers
  - `red_flags`: list with context/quotes from the transcript and severity
  - `highlights`: best moments/answers from the interview
  - `body_language_notes`: (if video metadata available) engagement indicators
  - `overall_recommendation`: "strong_hire" / "hire" / "no_hire" / "strong_no_hire" with justification
  - `summary`: bilingual 3-4 sentence executive summary
- [ ] Store analysis in `ai_screening_notes` (append with section header and timestamp)
- [ ] Update `ai_match_score` if this analysis changes the overall picture

**Priority:** P0 (the key M3 differentiator)
**Dependencies:** M2-03 (scoring pattern established)
**Saudi-specific:** Awareness of bilingual interviews (candidate may switch between Arabic and English), cultural communication norms

---

## M3-02: Get Interview Summary — Aggregated View (P1)

> As an HR manager, I want to see all interviews and assessments for a candidate in one place so that I have a complete picture before making a decision.

**Tool:** `get_interview_summary(candidate_id)`

**Acceptance Criteria:**

- [ ] Add tool definition with `candidate_id` (required)
- [ ] Add dispatch and private `_get_interview_summary()` method
- [ ] Validate UUID and tenant isolation
- [ ] Fetch all data points for this candidate:
  - AI screening results (from M1-08)
  - AI interview results (from M2-01/M2-03)
  - Zoom/recording analysis (from M3-01)
  - Manual stage progression notes
  - Assessment scores (from M2-02)
- [ ] Present as a timeline: each event with date, type, score, and summary
- [ ] Include an aggregated overall assessment:
  - Combined score across all evaluations
  - Consistency analysis (did scores go up or down over time?)
  - Progression narrative: "Candidate improved from screening to interview" or "Concerns emerged during technical assessment"
- [ ] Bilingual output for all summaries
- [ ] If no interviews yet: bilingual message "No interviews recorded for this candidate" / "لا توجد مقابلات مسجلة لهذا المرشح"

**Priority:** P1 (important for decision-making)
**Dependencies:** M1-08, M2-01, M2-03, M3-01 (aggregates all previous data)
**Saudi-specific:** None beyond bilingual output

---

## M3-03: Zoom Integration Setup (P2)

> As a platform administrator, I want Krew to connect to our Zoom account so that interview recordings are automatically fetched and analyzed.

**Acceptance Criteria:**

- [ ] Implement Zoom OAuth 2.0 flow for tenant-level connection
- [ ] Store Zoom access/refresh tokens securely per tenant
- [ ] Register a Zoom webhook for "recording.completed" events
- [ ] When a recording completes, check if the meeting title/description contains a candidate ID or job posting ID tag
- [ ] If tagged, automatically fetch the transcript and trigger `analyze_interview_recording` for the matched candidate
- [ ] Store the recording URL and transcript URL on a new `Interview` model (or extend existing data)
- [ ] Admin UI page to connect/disconnect Zoom (or handle via chat with Sarah)
- [ ] Support for Zoom, Microsoft Teams, and Google Meet transcripts via file upload as fallback
- [ ] Bilingual setup instructions

**Priority:** P2 (nice-to-have, manual transcript paste covers 80% of the value)
**Dependencies:** M3-01 (analysis tool must exist first)
**Saudi-specific:** None

---

## M3-04: Generate Offer Recommendation (P0 — Demo-Critical for M3)

> As an HR manager, I want Mohammad to recommend a salary and offer package based on all interview data, market benchmarks, and internal equity so that I can make competitive, fair offers.

**Tool:** `generate_offer_recommendation(candidate_id, job_posting_id)`

**Acceptance Criteria:**

- [ ] Add tool definition with `candidate_id` (required) and `job_posting_id` (required)
- [ ] Add dispatch and private `_generate_offer_recommendation()` method
- [ ] Validate UUIDs and tenant isolation
- [ ] Verify candidate has been through interview process (stage should be `interviewed` or later)
- [ ] If not interviewed: bilingual error "Candidate must complete interviews before offer recommendation" / "يجب إتمام المقابلات قبل توصية العرض"
- [ ] Fetch all candidate data: screening scores, interview scores, recording analysis
- [ ] Fetch job posting salary range (min/max SAR)
- [ ] Use Claude to generate offer recommendation:
  - `recommended_salary_sar`: specific number within the posting's range, justified by candidate strength
  - `salary_justification`: why this number (candidate strength, market position, internal equity)
  - `benefits_recommendation`: standard Saudi benefits package (medical per CCHI, GOSI registration, annual leave per Article 109, end-of-service per Article 84)
  - `probation_period`: recommend 90 days per Saudi Labor Law Article 53 (or 180 days if justified)
  - `start_date_suggestion`: based on standard Saudi notice period (30-60 days)
  - `risk_assessment`: flight risk, counter-offer likelihood, relocation needs
  - `negotiation_guidance`: suggested negotiation range and walk-away point
  - `saudization_impact`: how this hire affects the company's Nitaqat band
- [ ] Bilingual output for all sections
- [ ] Include a draft offer summary that can be shared with the candidate

**Priority:** P0 (critical for closing the loop)
**Dependencies:** M2-03, M3-01 (needs interview/analysis data for quality recommendation)
**Saudi-specific:** Saudi Labor Law Articles 53, 84, 109; GOSI registration; CCHI medical insurance; Nitaqat impact; SAR currency; Saudi notice periods

---

## M3-05: Hire Candidate + Waleed Handoff (P0 — Demo-Critical for M3)

> As an HR manager, I want to mark a candidate as hired, have an Employee record created automatically, and have Waleed start the onboarding process — all from one command.

**Tool:** `hire_candidate(candidate_id, start_date?, salary_sar?)`

**Acceptance Criteria:**

- [ ] Add tool definition with `candidate_id` (required), `start_date` (optional, YYYY-MM-DD), `salary_sar` (optional integer)
- [ ] Add dispatch and private `_hire_candidate()` method
- [ ] Validate UUID and tenant isolation
- [ ] Verify candidate stage is `offer_sent` or `interviewed` (must have gone through process)
- [ ] If candidate is already `hired`: bilingual error "This candidate has already been hired" / "تم توظيف هذا المرشح بالفعل"
- [ ] Update candidate stage to `hired`
- [ ] Create a new `Employee` record from candidate data:
  - `name` from Candidate
  - `email` from Candidate
  - `phone` from Candidate
  - `department_id` from the JobPosting
  - `hire_date` from `start_date` parameter or today
  - `status` set to appropriate initial value
  - `tenant_id` from context
- [ ] Update the `JobPosting`:
  - If all positions filled, change status to `closed`
  - Decrement open headcount if tracked
- [ ] Return the new Employee ID and a bilingual success message:
  - English: "Congratulations! [Name] has been hired as [Title]. Employee record created. Waleed will begin the onboarding process."
  - Arabic: "مبروك! تم توظيف [الاسم] في وظيفة [المسمى]. تم إنشاء سجل الموظف. وليد سيبدأ عملية التهيئة."
- [ ] Trigger a handoff signal to Waleed (set flag or create notification that Waleed's proactive context can pick up)
- [ ] The magic moment in the chat: "تم التوظيف، وليد يبدأ التهيئة" — the candidate just became an employee, and the next agent takes over.
- [ ] Log the hire event for pipeline analytics (time-to-hire calculation)

**Priority:** P0 (this is the culmination of the entire Mohammad pipeline)
**Dependencies:** M1-09 (stage update), Waleed agent (handoff target), Employee model
**Saudi-specific:** Employee record must include fields required for GOSI registration, hire date validation (not on Saudi weekend), Saudization tracking

---

# Phase M3 Demo Script — Full Cycle Closure

## Scene: From Zoom to Hire (Arabic, 3 minutes)

### Turn 1: Analyze a Zoom interview
- **User:** "محمد، حلل مقابلة سارة" (pastes transcript or provides URL)
- **Expected:** Mohammad calls `analyze_interview_recording(candidate_id, transcript_text)`. Returns detailed analysis with scores, highlights, and red flags.
- **Wow factor:** AI breaks down a 45-minute interview into actionable insights in seconds.

### Turn 2: Full candidate summary
- **User:** "عطني ملخص كامل عن سارة"
- **Expected:** Mohammad calls `get_interview_summary(candidate_id)`. Returns timeline of all evaluations: screening, AI interview, Zoom analysis.
- **Wow factor:** Complete candidate dossier from a single command.

### Turn 3: Offer recommendation
- **User:** "وش تقترح نعرض عليها؟"
- **Expected:** Mohammad calls `generate_offer_recommendation(candidate_id, job_posting_id)`. Returns salary recommendation, benefits, probation period, Nitaqat impact.
- **Wow factor:** Market-aware, legally-compliant offer recommendation with negotiation guidance.

### Turn 4: Hire and handoff
- **User:** "وظفها"
- **Expected:** Mohammad calls `hire_candidate(candidate_id, start_date, salary_sar)`. Creates Employee record, closes the loop, triggers Waleed.
- **Wow factor:** "تم التوظيف، وليد يبدأ التهيئة" — one word, and the candidate becomes an employee. The baton passes to Waleed.

---

# Implementation Notes

## Files to Modify

| File | Changes |
|------|---------|
| `backend/app/agents/mohammad.py` | Complete rewrite — all tool implementations, system prompt override, proactive context override |
| `backend/app/models/candidate.py` | No changes for M1. M2 may need an `Interview` model. M3 may need `InterviewRecording` model. |

## Files to Create

| File | Purpose | Phase |
|------|---------|-------|
| `backend/app/services/recruitment.py` | Service layer for complex recruitment logic (AI screening, JD generation, web search). Extract from agent if tools get complex. | M1 |
| `backend/tests/test_mohammad.py` | Unit tests for all Mohammad tools | M1 |
| `scripts/seed_recruitment.py` | Seed script: 3+ job postings, 10+ candidates, 1+ hired candidate, departments | M1 |
| `backend/app/services/interview.py` | Service layer for AI interview logic (question generation, scoring, comparison) | M2 |
| `backend/app/models/interview.py` | Interview model if we need to persist interview sessions, questions, and scores beyond `ai_screening_notes` | M2 |
| `backend/app/services/zoom_integration.py` | Zoom OAuth + webhook handler + transcript fetcher | M3 |

## Database Migrations

| Migration | Phase | Description |
|-----------|-------|-------------|
| None required | M1 | Existing `JobPosting` and `Candidate` models are sufficient |
| `add_interview_model` | M2 | New `Interview` table: id, candidate_id, job_posting_id, type (ai_screening/human/zoom), questions (JSON), answers (JSON), scorecard (JSON), created_at |
| `add_interview_recording` | M3 | New `InterviewRecording` table: id, interview_id, recording_url, transcript_text, analysis (JSON), created_at |

## Patterns to Follow (from Waleed/Deema)

1. UUID validation at the top of `handle_tool_call()` for all UUID fields
2. Private method naming: `_get_job_postings()`, `_screen_candidate()`, etc.
3. All responses via `json.dumps(...)`
4. Bilingual keys: `error`/`error_ar`, `message`/`message_ar`
5. Tenant isolation: always filter by `self.tenant_id` via JobPosting join
6. Empty state messages are warm and helpful, not clinical
7. System prompt override for handoff awareness
8. Proactive context override for first-message intelligence
9. Inner Claude calls for AI-powered tools (JD generation, screening, scoring) — use the same Anthropic client pattern

## Orchestrator Keywords

These keywords route to Mohammad in the orchestrator: `hire`, `recruit`, `candidate`, `resume`, `interview`, `job`, `توظيف`, `مرشح`, `وظيفة`, `مقابلة`

Consider adding for M1+: `JD`, `job description`, `وصف وظيفي`, `فحص`, `screen`, `pipeline`, `posting`

---

# Coverage Matrix — All Phases

| Capability | Story | Phase | Priority | Status |
|-----------|-------|-------|----------|--------|
| List job postings (filtered) | M1-01 | M1 | P0 | Stub exists, wire to DB |
| Get single posting details | M1-02 | M1 | P0 | New tool |
| Create job posting | M1-03 | M1 | P0 | New tool |
| AI job description generation | M1-04 | M1 | P0 | New tool (AI-powered) |
| Extract job keywords | M1-05 | M1 | P1 | New tool (AI-powered) |
| Web search for candidates | M1-06 | M1 | P1 | New tool |
| View candidates (filtered) | M1-07 | M1 | P0 | New tool |
| AI candidate screening | M1-08 | M1 | P0 | Stub exists, wire to DB + AI |
| Update candidate stage | M1-09 | M1 | P0 | New tool |
| Schedule interview | M1-10 | M1 | P0 | Stub exists, wire to DB |
| Pipeline dashboard/summary | M1-11 | M1 | P0 | New tool |
| Proactive context | M1-12 | M1 | P1 | New (pattern from Waleed) |
| Bilingual error/empty polish | M1-13 | M1 | P0 | New (pattern from Waleed) |
| System prompt + handoff | M1-14 | M1 | P1 | New (pattern from Waleed) |
| AI screening interview | M2-01 | M2 | P0 | New tool (AI-powered) |
| Generate role assessment | M2-02 | M2 | P1 | New tool (AI-powered) |
| Score interview | M2-03 | M2 | P0 | New tool (AI-powered) |
| Compare candidates | M2-04 | M2 | P1 | New tool (AI-powered) |
| Generate interview questions | M2-05 | M2 | P2 | New tool (AI-powered) |
| Analyze Zoom/recording | M3-01 | M3 | P0 | New tool (AI-powered) |
| Aggregated interview summary | M3-02 | M3 | P1 | New tool |
| Zoom OAuth integration | M3-03 | M3 | P2 | Infrastructure |
| Offer recommendation | M3-04 | M3 | P0 | New tool (AI-powered) |
| Hire + Waleed handoff | M3-05 | M3 | P0 | New tool (cross-agent) |
| Bulk candidate import | -- | Future | -- | Gap |
| Saudization ratio per posting | -- | Future | -- | Gap |
| Reference check automation | -- | Future | -- | Gap |
| Offer letter PDF generation | -- | Future | -- | Gap |
| Candidate communication/emails | -- | Future | -- | Gap |
| Employer branding strategy | -- | Future | -- | Gap (CoE agent territory) |

---

# Sprint Velocity Estimates

## Phase M1

| Story | Effort | Notes |
|-------|--------|-------|
| M1-01 | M | Real DB queries + validation, straightforward |
| M1-02 | S | Single query with joins and candidate aggregation |
| M1-03 | M | Write path, department lookup, validation |
| M1-04 | L | Inner Claude call, prompt engineering for Saudi context, bilingual output |
| M1-05 | M | Inner Claude call, structured extraction |
| M1-06 | M | Web search integration, platform-specific query construction |
| M1-07 | M | Candidate query with filters, stage validation |
| M1-08 | L | Inner Claude call for AI analysis, score storage, stage update |
| M1-09 | M | Stage transition validation logic |
| M1-10 | M | Date/time validation, weekend detection, stage update |
| M1-11 | M | Aggregation queries, avg calculation |
| M1-12 | S | Pattern copy from Waleed |
| M1-13 | S | Review all paths, copy pattern from Waleed |
| M1-14 | S | System prompt text, handoff awareness |

**M1 Total:** ~8-10 implementation sessions

## Phase M2

| Story | Effort | Notes |
|-------|--------|-------|
| M2-01 | XL | Stateful interview flow, multi-turn conversation design |
| M2-02 | L | Complex prompt engineering for assessment generation |
| M2-03 | L | Structured scorecard generation, score storage |
| M2-04 | L | Multi-candidate comparison, ranking logic |
| M2-05 | M | Question generation with follow-ups |

**M2 Total:** ~5-6 implementation sessions

## Phase M3

| Story | Effort | Notes |
|-------|--------|-------|
| M3-01 | XL | Transcript analysis, longest/most complex AI analysis |
| M3-02 | M | Aggregation across multiple data sources |
| M3-03 | XL | OAuth flow, webhooks, third-party integration |
| M3-04 | L | Market-aware recommendation, Saudi labor law integration |
| M3-05 | L | Cross-model writes (Candidate + Employee), cross-agent handoff |

**M3 Total:** ~5-7 implementation sessions

---

**Grand Total: ~18-23 implementation sessions across all three phases.**

**When M3 is done, Mohammad is a complete AI recruitment department.** A hiring manager says "نبي مهندس" and Mohammad writes the JD, posts the role, sources candidates online, screens resumes with AI, interviews finalists, analyzes their Zoom recordings, recommends an offer, hires them, and hands them to Waleed. That is the product.
