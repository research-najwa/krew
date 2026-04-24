# Krew Master Roadmap — Post-Investor Pitch
**Author:** Tariq (Product Owner) | **Date:** 2026-03-29 | **Version:** 1.0

---

## 1. Vision

Krew is the **workplace platform built for Saudi organizations** where AI agents and humans are equal team members. Think Slack — but every department has AI colleagues who know Saudi labor law, speak Arabic natively, and handle HR workflows alongside your human team.

**Positioning:** Not an HR chatbot. Not a Slack clone. The place where Saudi organizations **communicate AND get work done** — with AI built in, not bolted on.

**Three differentiators:**
1. **Multi-agent depth** — 5 specialized agents, 91+ tools, orchestrated handoffs
2. **Arabic-first, Saudi labor law native** — not a translation layer
3. **Humans + AI agents in the same channels** — indistinguishable in UX

---

## 2. What We've Built (Phase 1 Complete)

| Agent | Role | Tools | Status |
|-------|------|-------|--------|
| **Deema** | Employee Services | 17 | LIVE — policy RAG, bilingual, leave/salary/tickets |
| **Waleed** | Onboarding & Manager | 14 | DONE — checklists, buddy assign, manager approvals, handoff |
| **Mohammad** | Recruitment | 27 | DONE — full pipeline, AI interviews, transcript analysis, offers |
| **Yara** | AI Workforce Architect | 16 | DONE — workforce planning, Agent Factory, governance, DynamicAgent runtime |
| **Ahmad** | CHRO (Analytics + Compliance) | 7/17 | A1 DONE — headcount, saudization, turnover, budget, salary, compliance. A2+A3 pending. |

**Total shipped:** 81 tools across 5 agents. Teams UI with department members (humans + AI agents). Channel-agnostic architecture (web, WhatsApp, Slack, email ready).

**Infrastructure:**
- FastAPI backend + PostgreSQL + pgvector RAG
- Anthropic Claude (tool-use agents)
- Alembic migrations, tenant isolation
- 40 QA tests on Ahmad, 56 on Yara, full review pipeline per agent

---

## 3. Architecture Evolution

### Current State → Target State

| Layer | Today | Target |
|-------|-------|--------|
| **Transport** | Sync REST `POST /chat` | WebSocket real-time + Redis Pub/Sub |
| **Conversations** | 1 employee <-> 1 agent | Unified Channels: DMs, groups, departments (N participants, human+agent) |
| **Teams** | Read-only sidebar | Real channels with message history, @mentions |
| **Presence** | Hardcoded "online" | Real-time: online/offline/away, typing indicators, read receipts |
| **Frontend** | Monolithic `chat.html` (37K tokens) | Next.js (React) — SSR + SPA + component sharing with React Native |
| **Mobile** | Desktop-only | PWA first (Sprint 11), React Native (Sprint 14) |
| **Integrations** | None (channel field exists but unused) | WhatsApp bridge, Slack bridge, push notifications |
| **Input** | Text only | Text + voice + documents + camera + smart suggestions |
| **Output** | Plain text | Rich messages: cards, buttons, forms, charts, progress bars |

### Key Architecture Decisions

1. **WebSocket:** FastAPI native + Redis Pub/Sub for multi-instance fan-out
2. **Data Model:** New `Channel` / `ChannelMessage` / `ChannelMember` (types: dm, group, department, org-wide). Migrate existing conversations.
3. **Frontend:** Next.js (React) — enables SSR, rich SPA, React Native code sharing
4. **Mobile:** PWA first (Sprint 11), React Native (Sprint 14)
5. **Agent-in-Channel:** @mention only for V1 — agents respond when tagged, silent otherwise
6. **STT:** Whisper API (best Arabic dialect support) — decision needed before Sprint 9
7. **OCR:** Azure Document Intelligence (best Arabic layout) — decision needed before Sprint 10
8. **File Storage:** S3-compatible — decision needed before Sprint 8

---

## 4. Sprint Plan (Sprints 7-15)

### Sprint 7 (Weeks 1-2): Ahmad A2 + Effortless UX Foundation

**Agent work:**
| Tool | Description | Effort |
|------|-------------|--------|
| A2-01: `get_recruitment_analytics` | Funnel conversion, time-to-fill, cost-per-hire | 2d |
| A2-02: `get_leave_analytics` | Usage patterns, seasonal peaks, Hajj tracking | 1.5d |
| A2-03: `get_attendance_analytics` | Attendance rate, late rate, overtime trends | 1.5d |
| A2-04: `get_onboarding_analytics` | Completion rates, bottleneck steps, overdue | 1d |
| A2-05: `get_payroll_summary` | Monthly cost trends, GOSI breakdown | 2d |

**Conversational UX (no new infra needed):**
| Feature | Description | Effort |
|---------|-------------|--------|
| Context-aware suggestions | Rule-based chips: time, role, pending items, deadlines | M |
| Follow-up chips | 2-3 suggested next actions after every agent response | S |
| Quick Actions Bar | Persistent strip above keyboard, role-based defaults | S |

**Deliverable:** Ahmad at 12/17 tools. Every chat session starts with smart suggestions instead of a blank input.

---

### Sprint 8 (Weeks 3-4): Ahmad A3 + RBAC + Rich Messages

**Agent work:**
| Tool | Description | Effort |
|------|-------------|--------|
| A3-01: `predict_attrition_risk` | Rule-based dept risk scoring | 2d |
| A3-02: `forecast_budget` | 3-scenario projection | 2d |
| A3-03: `audit_gosi_compliance` | Unregistered employee detection | 1.5d |
| A3-04: `track_policy_acknowledgments` | Per-policy ack rates, gaps | 1.5d |
| A3-05: `generate_custom_report` | Multi-metric report with Hijri dates | 2d |

**Security & Agent Factory Enhancements:**
| Feature | Description | Effort |
|---------|-------------|--------|
| RBAC data model | User, Role, Permission tables | 3d |
| JWT authentication | Login, token issuance, refresh | 3d |
| Agent access control | Role checks before tool execution | 2d |
| Agent visibility controls | visibility enum (department/role_based/specific_users/org), `set_agent_visibility` tool | 2d |
| Agent data source binding | `data_sources` JSONB on deployed_agents, `configure_data_sources` tool, DynamicAgent enforcement | 2d |
| Agent knowledge base | `agent_knowledge_sources` table, `assign_knowledge` + `list_agent_knowledge` tools, scoped RAG | 2d |
| Overlap detection | Duplicate/super-agent overlap checks in `design_agent` + `create_agent` | 1d |

*Full spec: [docs/yara_factory_enhancements.md](docs/yara_factory_enhancements.md)*

**Conversational UX:**
| Feature | Description | Effort |
|---------|-------------|--------|
| File upload in chat | PDF, images, docs — extend ChatRequest | M |
| Structured message format | MessageBlock types: card, table, button_group, form, chart | L |
| Disambiguation | "Did you mean...?" when intent unclear | M |
| Role-based default suggestions | Employee/manager/exec/admin presets | S |

**Deliverable:** Ahmad complete (17/17 tools). Auth system live. Rich message foundation.

---

### Sprint 9 (Weeks 5-6): Real-Time Messaging Core + Voice

**Messaging infrastructure:**
| Feature | Description | Effort |
|---------|-------------|--------|
| Channel data model | Channel, ChannelMessage, ChannelMember + Alembic migration | 3d |
| WebSocket endpoint | `/ws/chat` with JWT auth handshake | 3d |
| Message persistence | Send/receive via WebSocket, persist to DB | 2d |
| Redis Pub/Sub | Multi-instance fan-out | 1d |
| Conversation migration | Convert existing Conversations to Channels | 1d |
| Next.js shell | Channel list + message stream (replaces chat.html) | 3d |

**Voice:**
| Feature | Description | Effort |
|---------|-------------|--------|
| Voice recording | Hold-to-record, WhatsApp-style | M |
| Speech-to-text | Whisper API, Saudi dialect support | L |

**Conversational UX:**
| Feature | Description | Effort |
|---------|-------------|--------|
| Camera capture | Snap documents directly in chat | S |
| Action buttons | Approve/Reject in messages — one tap | M |

**Deliverable:** Real-time messaging live. Voice input working. Krew becomes a platform.

---

### Sprint 10 (Weeks 7-8): Channels + DMs + Agent-in-Channel

**Messaging:**
| Feature | Description | Effort |
|---------|-------------|--------|
| Department auto-channels | Every dept gets a channel with all members | 2d |
| Human-to-human DMs | Direct messaging between employees | 2d |
| @mention routing | @deema in a group channel → Deema responds in thread | 2d |
| Typing indicators | "typing..." / "thinking..." for agents | 1d |
| Read receipts | Double checkmark, "seen by N" | 1d |
| Unread counts | Badge on channels, total on app icon | 1d |

**Conversational UX:**
| Feature | Description | Effort |
|---------|-------------|--------|
| Voice-to-action | "أبي إجازة يوم الخميس" → leave flow starts | S |
| OCR extraction | Arabic + English, reads Saudi gov docs | L |
| Inline forms | Leave request form IN the chat, Hijri date picker | L |
| Progress bars | Waleed's onboarding checklist as visual tracker | S |

**Deliverable:** Full Slack-like experience. Humans chat with humans AND agents in same channels. **First pilot-ready date.**

---

### Sprint 11 (Weeks 9-10): Mobile PWA + Admin UI + Push

**Mobile:**
| Feature | Description | Effort |
|---------|-------------|--------|
| Responsive PWA | Works on all phones, installable | 3d |
| Service worker | Offline cached messages, background sync | 2d |
| Web Push notifications | FCM for Android, APNs via PWA for iOS | 2d |
| Offline message queue | Queue outgoing while offline, send on reconnect | 1d |

**Admin UI:**
| Feature | Description | Effort |
|---------|-------------|--------|
| Admin shell + nav | Sidebar: People, Compliance, Finance, Settings | 2d |
| Employee management | List, search, view/edit employees | 2d |
| Attendance management | View/filter, manual corrections, overtime | 1.5d |
| HR Policy management | CRUD, publish/unpublish, ack rates | 1.5d |
| GOSI + Nitaqat dashboard | Visual Nitaqat bands, GOSI status, alerts | 1.5d |
| Onboarding templates | Manage checklists, view progress | 1.5d |

**Conversational UX:**
| Feature | Description | Effort |
|---------|-------------|--------|
| Smart document routing | Upload medical cert → sick leave flow auto-starts | M |
| Data visualization | Ahmad's analytics as inline charts | M |

**Deliverable:** Mobile-ready. Admin can configure the system. Analytics are visual.

---

### Sprint 12 (Weeks 11-12): WhatsApp Bridge + Data Seeding

**WhatsApp:**
| Feature | Description | Effort |
|---------|-------------|--------|
| WhatsApp Business API | Twilio/Meta Cloud connector | 3d |
| Inbound routing | WhatsApp msg → correct agent | 2d |
| Bidirectional sync | WhatsApp ↔ Krew channel history | 2d |
| Phone number linking | Employee profile ↔ WhatsApp number | 1d |

**Data seeding:**
| Feature | Description | Effort |
|---------|-------------|--------|
| Saudi Labor Law policies | 15-20 core policies (Art. 84-86, 109, 117, etc.) | 4d |
| Compliance records seed | GOSI, Nitaqat, WPS, labor contract items | 1.5d |
| Realistic demo data | 50+ employees, 5 depts, Saudi names, salaries | 2d |

**Conversational UX:**
| Feature | Description | Effort |
|---------|-------------|--------|
| TTS for agent responses | Speaker icon, Arabic voice playback | S |

**Deliverable:** WhatsApp channel live. Demo data makes every agent look real.

---

### Sprint 13 (Weeks 13-14): Slack Bridge + File Sharing + Polish

| Feature | Description | Effort |
|---------|-------------|--------|
| Slack Events API integration | Bidirectional channel mirroring | 3d |
| `/krew` slash commands | `/krew ask deema`, `/krew leave-balance` | 2d |
| File/image sharing | Upload in channels, S3 storage, thumbnails | 2d |
| Voice messages | Record + transcribe + play waveform | 2d |
| Personalized action bar | ML-based reordering from usage patterns | M |
| Remaining admin pages | Documents, Mudad, escalations, audit logs | 2d |

---

### Sprint 14 (Weeks 15-16): React Native MVP

| Feature | Description | Effort |
|---------|-------------|--------|
| iOS + Android app | React Native, shared WebSocket backend | 5d |
| Native push | FCM + APNs | 2d |
| Biometric auth | Face ID / fingerprint login | 1d |
| Offline sync | Message caching + background fetch | 2d |

---

### Sprint 15 (Weeks 17-18): Production Hardening

| Feature | Description | Effort |
|---------|-------------|--------|
| Arabic RTL perfection | All components, all screens | 2d |
| Saudi weekend presence | Fri/Sat defaults, prayer time awareness | 1d |
| Saudi PDPL compliance | Data retention, phone number storage rules | 2d |
| Load testing | 1000 concurrent WebSocket connections | 2d |
| OpenAI embeddings | Upgrade RAG semantic search for Arabic | 2d |
| Message search | Full-text search across channels, Arabic stemming | 2d |

---

## 5. Conversational UX — The "Effortless" Layer

### Design Principles
1. **Zero-typing default** — suggest the right action before the user thinks of it
2. **One-tap interactions** — chips, buttons, quick actions replace typing wherever possible
3. **Voice-first for Arabic** — Saudi users prefer voice; typing Arabic is slower
4. **Camera as input** — snap a document, system reads it and acts
5. **Rich output** — charts, progress bars, forms IN the chat, not JSON walls
6. **Mobile-first** — every feature designed for thumb on phone first

### Feature Map

| Capability | What | Sprint |
|-----------|------|--------|
| **Smart Suggestions** | Context-aware chips before typing (time, role, pending items) | 7 |
| **Follow-up Chips** | 2-3 next actions after every agent response | 7 |
| **Quick Actions Bar** | Persistent strip above keyboard, role-based | 7 |
| **Disambiguation** | "Did you mean...?" tappable options | 8 |
| **File Upload** | PDF, images, HEIC in chat | 8 |
| **Rich Messages** | Cards, tables, structured blocks | 8 |
| **Voice Recording** | Hold-to-record, WhatsApp-style | 9 |
| **Speech-to-Text** | Whisper, Saudi dialect, code-switching | 9 |
| **Camera Capture** | Snap iqama / medical cert directly | 9 |
| **Action Buttons** | Approve/Reject in-message | 9 |
| **Voice-to-Action** | "أبي إجازة يوم الخميس" → leave flow | 10 |
| **OCR** | Arabic + English doc reading | 10 |
| **Inline Forms** | Leave request form in chat, Hijri dates | 10 |
| **Progress Bars** | Onboarding checklist visual tracker | 10 |
| **Smart Doc Routing** | Upload cert → auto-detect → right agent | 11 |
| **Charts in Chat** | Ahmad's analytics as bar/pie/gauge | 11 |
| **TTS Playback** | Hear agent responses (accessibility) | 12 |
| **Voice Messages** | Record + transcribe + waveform | 13 |
| **Personalized Actions** | ML-based reordering from usage | 13 |

---

## 6. Epic Summary (10 Messaging + 5 Conversational UX)

### Messaging Platform Epics

| # | Epic | Effort | Priority | Sprint |
|---|------|--------|----------|--------|
| M1 | Real-Time Messaging Core | L | P0 | 9 |
| M2 | Channels & Groups | M | P0 | 10 |
| M3 | Presence & Status | M | P1 | 10 |
| M4 | Human-to-Human DMs | S | P0 | 10 |
| M5 | Agent-in-Channel (@mention) | M | P1 | 10 |
| M6 | Mobile PWA | L | P1 | 11 |
| M7 | WhatsApp Bridge | L | P2 | 12 |
| M8 | Slack Bridge | M | P2 | 13 |
| M9 | Push Notifications | M | P1 | 11 |
| M10 | File Sharing & Media | M | P2 | 13 |

### Conversational UX Epics

| # | Epic | Effort | Priority | Sprint |
|---|------|--------|----------|--------|
| C1 | Smart Suggestions System | M | P0 | 7 |
| C2 | Voice Input & Output | L | P0 | 9-10 |
| C3 | Document & Image Handling | L | P1 | 8-11 |
| C4 | Rich Message Types | L | P0 | 8-11 |
| C5 | Quick Actions Bar | S | P0 | 7 |

---

## 7. Key Milestones

| Week | Milestone | What's Live |
|------|-----------|-------------|
| **4** | All agents complete | 5 agents, 91 tools, RBAC, rich messages |
| **6** | Platform launch | Real-time messaging, voice, WebSocket |
| **8** | Pilot-ready | Channels, DMs, agent-in-channel, forms, OCR |
| **10** | Mobile-ready | PWA, push notifications, admin UI |
| **12** | WhatsApp live | Bridge active, Saudi labor law policies seeded |
| **14** | Native app | React Native iOS + Android |
| **18** | Production-hardened | Load tested, PDPL compliant, search, RTL perfect |

---

## 8. Competitive Positioning

### vs Slack
- AI agents are native team members, not bots. Names, avatars, presence.
- Arabic-first, RTL-native. Not a localization patch.
- Saudi labor law built into the agent layer.
- Lower cost for Saudi SME market.

### vs Microsoft Teams
- Zero IT infrastructure. No Active Directory, no Exchange, no Azure AD.
- Live in one day (Teams = weeks of IT setup).
- Purpose-built for HR, not a generic productivity suite.

### vs Jisr / MenaITech / ZenHR
- They're systems of record (forms + CRUD). Krew is where work happens.
- Real-time communication layer they completely lack.
- AI agents that execute workflows, not FAQ bots.
- Multi-agent orchestration with handoffs.

### The Moat
1. **Agent depth** — 91+ tools, Saudi labor law expertise. Months to replicate.
2. **Agent orchestration** — routing, handoffs, multi-agent channels. Non-trivial.
3. **Saudi cultural embedding** — not translation, but understanding (Hajj leave, probation, Nitaqat).
4. **Network effects** — once communication lives in Krew, switching costs are high.

---

## 9. Infrastructure Decisions Needed

| Decision | Options | Deadline | Recommendation |
|----------|---------|----------|----------------|
| STT Service | Whisper API / Google Cloud Speech / Azure Speech | Before Sprint 9 | Whisper (best Arabic dialect) |
| OCR Service | Azure Doc Intelligence / Google Vision / Tesseract | Before Sprint 10 | Azure (best Arabic layout) |
| File Storage | AWS S3 / GCS / Azure Blob | Before Sprint 8 | S3 (most ecosystem support) |
| Frontend Framework | Next.js (React) / Nuxt (Vue) | Before Sprint 8 | Next.js (React Native synergy) |
| Mobile Strategy | PWA first → React Native | Before Sprint 11 | PWA Sprint 11, RN Sprint 14 |
| Redis Provider | ElastiCache / Upstash / self-hosted | Before Sprint 9 | Upstash (serverless, low ops) |

---

## 10. Risk Register

| Risk | Impact | Mitigation |
|------|--------|------------|
| Scope creep — building generic Slack | High | Stay laser-focused on HR use case. Not competing with Slack on general messaging. |
| Arabic STT quality | Medium | Test Whisper large-v3 Saudi dialect early. Fallback: manual transcription correction UI. |
| WhatsApp Business API approval | Medium | Start Meta business verification now (2-4 week lead time). |
| Frontend migration (chat.html → Next.js) | High | Parallel run: keep chat.html working while building Next.js. No big-bang rewrite. |
| Single-developer bottleneck | High | Prioritize ruthlessly. Ship Sprint 7-8 (agents + suggestions) before infrastructure. |

---

## Appendix: Agent Tool Inventory

### Deema — Employee Services (17 tools)
Policy RAG, leave balance, leave request, salary info, payslip, profile, contract, tickets, notifications, document upload, and more.

### Waleed — Onboarding & Manager (14 tools)
Onboarding checklist, buddy assignment, document collection, 30/60/90 check-ins, team overview, leave approvals, headcount.

### Mohammad — Recruitment (27 tools)
JD generation, job posting, candidate pipeline, resume screening, AI interviews, transcript analysis, salary benchmarking, offer recommendation, hire-to-Waleed handoff.

### Yara — AI Workforce Architect (16 tools)
Department overview, workforce analysis, workforce mix recommendation, scenario simulation, ROI estimation, agent design, agent creation, agent activation, tool configuration, escalation rules, agent listing, performance monitoring, drift detection, prompt updates, deactivation, governance reports.

### Ahmad — CHRO (17 tools planned)
**A1 (7 tools, DONE):** Headcount summary, Saudization status, turnover metrics, department budget, salary distribution, workforce overview, compliance status.
**A2 (5 tools, Sprint 7):** Recruitment analytics, leave analytics, attendance analytics, onboarding analytics, payroll summary.
**A3 (5 tools, Sprint 8):** Attrition risk, budget forecast, GOSI audit, policy acknowledgments, custom reports.
