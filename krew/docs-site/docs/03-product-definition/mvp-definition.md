# MVP Scope Definition

## MVP Philosophy
Launch with **HR Shared Services first** — it's the highest-volume, most transactional, and most automatable division of HR. This is where companies feel the most pain and where AI delivers the most obvious ROI. Then expand division by division until the full AI HR department is live.

## Why Start with HR Shared Services?
- **Highest volume** — 80% of employee HR interactions are transactional (leave requests, policy questions, onboarding paperwork)
- **Highest cost** — Companies staff 3–10 coordinators just for daily operations
- **Easiest to automate** — Rule-based, repetitive, data-driven tasks
- **Fastest time-to-value** — Customers see impact from day 1
- **Low risk** — Transactional work has clear right/wrong answers; less judgment needed

## MVP by Division

### HR Shared Services — FULL BUILD (MVP Core)

#### Employee Services Agent
- Answer employee questions about policies, PTO, benefits 24/7
- Process leave requests end-to-end
- Handle personal information updates
- Route complex issues to the right human
- **Success metric:** 85%+ query resolution without human escalation

#### Onboarding Operations Agent
- Generate personalized onboarding checklists
- Collect and verify new hire documents
- Schedule orientation and buddy assignments
- Conduct 30/60/90-day check-ins
- **Success metric:** 50% reduction in time-to-productivity

#### Recruitment Operations Agent (Lite)
- Job description generation
- Resume screening and ranking
- Interview scheduling
- Candidate communication
- **Success metric:** 40% reduction in time-to-hire

#### Employee Records Agent
- Maintain employee master data
- Track compliance training completion
- Process employment verifications
- **Success metric:** 99%+ data accuracy

---

### HR CoE — LITE BUILD (MVP Supporting)

#### Compliance & Policy CoE Agent (Lite)
- Audit existing policies against local labor law
- Generate/update employee handbook
- Alert on regulation changes
- **Success metric:** Zero compliance gaps in post-deployment audit

---

### HR Analytics & Finance — LITE BUILD (MVP Supporting)

#### Workforce Budget Agent (Lite)
- Headcount cost tracking (actual vs. budget)
- Cost comparison: virtual employee vs. human equivalent
- Basic monthly HR cost reports
- New hire cost modeling (before approval)
- **Success metric:** CFO can see real-time HR spend and savings dashboard

---

### Agent Factory — LITE BUILD (MVP Supporting)

#### Agent Factory Engine (Lite)
- Analyze HR job descriptions submitted by the customer
- Score AI readiness for each role
- Recommend: human or agent for each JD
- Deploy recommended virtual employees from the catalog
- **Success metric:** 80%+ accuracy in human-vs-agent recommendations for HR roles

---

### NOT in MVP (Phase 2+)

| Division | What Comes Later |
|----------|-----------------|
| **HR CoE** (full) | TA CoE, C&B CoE, L&D CoE, Performance CoE, Culture CoE |
| **HRBP** | Full HRBP agent (hybrid) — needs more data and trust |
| **HR Analytics & Finance** (full) | People Analytics, Predictive Intelligence, ROI analysis, predictive financial modeling, payroll analytics |
| **HR Shared Services** (expanded) | Payroll Operations, Offboarding Operations |
| **Agent Factory** (full) | Non-HR JD analysis (secretary, financial analyst, market researcher, etc.) |

## How It Feels to the Customer

> **Day 0:** Sign up → upload policies, org chart, and employee list (or let AI generate from scratch)
>
> **Day 1:** HR Shared Services agents go live — employees can ask questions in Slack, request leave, get instant answers
>
> **Week 1:** First new hire goes through AI-powered onboarding — zero manual coordination
>
> **Week 2:** Compliance agent delivers audit report — flags 3 policy gaps the company didn't know about
>
> **Month 1:** CFO sees dashboard: "We handled 450 employee queries, onboarded 3 new hires, and saved $4,200 vs. hiring an HR Coordinator."
>
> **Month 2:** Company submits 5 open JDs to the Agent Factory — discovers 2 roles can be virtual employees

## MVP Platform Requirements
| Component | MVP Scope |
|-----------|-----------|
| **User Interface** | Web dashboard for admins + Slack/Teams/email for employees |
| **Company Setup** | Guided wizard to input policies, org chart, compensation |
| **Employee Directory** | Profiles for both human AND virtual employees |
| **Virtual Employee Profiles** | Name, avatar, role, division, team, KPIs |
| **Knowledge Base** | Upload company handbook, policies, benefits docs |
| **Integrations** | Google Workspace or Microsoft 365 (calendar, email), Slack |
| **Agent Factory** | JD submission → human vs. agent analysis → deployment recommendation |
| **Shared Services Dashboard** | Tickets, resolution rates, satisfaction, onboarding status |
| **Analytics & Finance Dashboard** | Headcount costs, budget tracking, virtual vs. human savings |
| **Security** | SOC 2 Type I compliance, encryption at rest and in transit |

## MVP Timeline

| Month | Milestone | Division |
|-------|-----------|----------|
| 1 | Architecture design, LLM selection, regulatory data pipeline | Platform |
| 2 | Employee Services Agent + company setup wizard | HR Shared Services |
| 3 | Onboarding Ops Agent + Records Agent + admin dashboard | HR Shared Services |
| 4 | Recruitment Ops Agent (lite) + Compliance CoE Agent (lite) | Shared Services + CoE |
| 5 | Analytics & Finance dashboard (lite) + Agent Factory (lite) + beta testing with 3–5 companies | Analytics + Factory |
| 6 | Bug fixes, hardening, launch-ready | All |

## MVP Success Criteria
- [ ] 5 paying beta customers
- [ ] Each customer has live HR Shared Services (3–4 agents running)
- [ ] Agent Factory has analyzed at least 20 JDs across beta customers
- [ ] 90%+ uptime
- [ ] <30 second average response time
- [ ] 85%+ query resolution without human escalation
- [ ] Customers can quantify cost savings (vs. hiring an HR Coordinator)
- [ ] Positive NPS from beta customers
- [ ] Zero data breaches or compliance failures
