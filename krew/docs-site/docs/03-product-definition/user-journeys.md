# User Journeys

## Journey 1: Company Onboarding (Admin sets up the platform)

```
Day 0: Admin signs up → selects company size, industry, locations
  ↓
Day 0: Upload existing policies, handbook, org chart (or let AI generate from scratch)
  ↓
Day 0: Connect integrations (Google Workspace / M365, Slack, payroll system)
  ↓
Day 0: Import employee directory (CSV or HRIS sync)
  ↓
Day 1: Compliance Agent audits uploaded policies → flags gaps → suggests fixes
  ↓
Day 1: Admin reviews and approves AI-generated policies
  ↓
Day 2: Employee Relations Agent goes live — employees get Slack/email intro
  ↓
Week 1: First analytics report generated for admin
```

## Journey 2: Employee Asks a Question

```
Employee sends message via Slack: "How many vacation days do I have left?"
  ↓
Employee Relations Agent checks employee profile → PTO balance
  ↓
Agent responds: "Hi Sarah, you have 12 vacation days remaining this year.
  You've used 8 days so far. Would you like to request time off?"
  ↓
Employee: "Yes, I'd like to take Dec 20-24 off"
  ↓
Agent checks: team calendar, blackout dates, manager approval rules
  ↓
Agent: "I've submitted your request for Dec 20-24 (3 business days).
  Your manager Ahmed will be notified. I'll let you know once approved."
  ↓
Agent sends approval request to manager Ahmed via Slack
  ↓
Ahmed approves → Agent confirms to Sarah → Calendar updated
```

## Journey 3: Hiring a New Employee (End-to-End)

```
Manager submits hiring request: "I need a Senior Product Designer"
  ↓
Recruitment Agent generates job description based on role level + company context
  ↓
Manager reviews and approves JD (with edits)
  ↓
Agent posts to LinkedIn, Indeed, company careers page
  ↓
Applications come in → Agent screens and ranks top 10 candidates
  ↓
Agent presents shortlist to manager with match scores and key highlights
  ↓
Manager selects 5 for interviews → Agent schedules with interview panel
  ↓
Agent sends interview guides and scorecards to interviewers
  ↓
Post-interview: Agent collects feedback, generates summary, recommends top pick
  ↓
Manager decides → Agent generates offer letter using compensation bands
  ↓
Offer accepted → HANDOFF to Onboarding Agent
  ↓
Onboarding Agent activates: welcome email, document collection, IT setup,
  orientation schedule, buddy assignment, 30/60/90 plan
```

## Journey 4: Compliance Alert

```
Labor law changes in [jurisdiction] → Compliance Agent detects update
  ↓
Agent analyzes impact on company's current policies
  ↓
Agent generates: "Alert: New overtime regulations in California effective March 1.
  Your current overtime policy needs 2 updates. Here's what changed and
  my recommended policy language."
  ↓
Admin reviews → approves changes → policies auto-updated
  ↓
Agent notifies affected employees and managers of policy change
  ↓
Agent schedules mandatory training if required
```

## Journey 5: Employee Offboarding

```
Manager initiates: "Alex is leaving. Last day is Feb 28."
  ↓
Offboarding Agent activates → generates customized checklist
  ↓
Agent schedules exit interview with Alex (AI-conducted)
  ↓
Agent coordinates: IT access revocation, equipment return, final pay calc
  ↓
Agent generates separation documents for Alex to sign
  ↓
Agent processes: PTO payout, benefits continuation info (COBRA)
  ↓
Exit interview completed → insights added to attrition analytics
  ↓
Agent sends alumni welcome and references Alex's manager for future requests
```

---

## Questions to Refine
- [ ] What communication channels do we support at launch? (Slack, Teams, email, web portal)
- [ ] How much can agents do autonomously vs. requiring manager approval?
- [ ] What's the escalation UX when agents can't handle something?
- [ ] Multi-language support timeline? (English → Arabic → others?)
