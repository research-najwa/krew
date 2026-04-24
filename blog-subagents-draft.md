# I Built a 16-Agent AI Dev Team Inside My Terminal — Here's What Actually Happened

*A solo founder's experiment with Claude Code subagents as a full simulated engineering org.*

---

## The Premise

I'm building a SaaS platform solo. No co-founder, no engineering team, no budget for one yet. What I do have is Claude Code and a question that wouldn't leave me alone:

**What if I didn't just use AI as a coding assistant — but structured it as an entire development team?**

Not "hey Claude, write me a function." Instead: an architect who designs before anyone codes. A developer who follows the architect's spec. A code reviewer who can read but *cannot edit* — by design. A QA engineer who validates against acceptance criteria. A DBA, a DevOps engineer, an SRE, a red team specialist.

Sixteen agents. One terminal. Zero humans besides me.

Here's what I learned.

---

## The Setup (It's Simpler Than You Think)

Claude Code has a feature most people overlook: the `.claude/agents/` directory. You drop a markdown file in there, and it becomes a callable subagent.

Each file has three parts:

```markdown
---
name: architect
description: Designs data models, API contracts, and technical blueprints
tools: Read, Glob, Grep, Bash
model: opus
---

You are the System Architect. You receive user stories and produce
technical designs that the dev team implements...
```

That's it. The **frontmatter** controls identity, permissions, and model selection. The **body** is the system prompt — what the agent believes about itself, its responsibilities, its output format.

The key insight: **tool scoping is your org chart.** My reviewer agent gets `Read, Glob, Grep, Bash` — it can examine everything but modify nothing. My dev agent gets `Read, Edit, Write, Bash` — it can change code. This isn't just role-playing. It's enforced at the infrastructure level.

---

## The Team

| Name | Role | Tools | Model | Why This Scope |
|------|------|-------|-------|----------------|
| Faisal | Architect | Read-only + can spawn agents | Opus | Designs, doesn't implement |
| Rania | Developer | Full read/write | Opus | Needs to change code |
| Khaled | Reviewer | Read-only | Opus | Reviews, cannot "fix it myself" |
| Reviewer 2 | 2nd Reviewer | Read-only | Opus | Blind independent review |
| Layla | QA Engineer | Read/write + spawn agents | Opus | Writes and runs tests |
| Tariq | Product Owner | Read-only + web | Sonnet | Validates stories, not code |
| DBA | DBA | Full read/write | Opus | Manages migrations and schema |
| DevOps | DevOps | Full read/write | Opus | CI/CD, Docker, infra |
| SRE | SRE | Full read/write | Opus | Monitoring, runbooks |
| Red Team | Red Team | Full read/write | Opus | Adversarial security testing |
| Doc Writer | Doc Writer | Read + write | Sonnet | Generates docs, no code changes |
| UX Researcher | UX Researcher | Read-only + web | Sonnet | Validates flows, not builds them |
| UI Designer | UI Designer | Read/write | Sonnet | Interface design |
| Analytics | Analytics | Read/write | Sonnet | Tracks agent performance metrics |
| Conv Tester | Conversation Tester | Read/write | Opus | Tests multi-turn AI conversations |
| Prompt Tester | Prompt Tester | Read/write | Opus | Tests system prompts, hallucination |

---

## What I Embedded in Each Agent

A minimal agent prompt is 5 lines. Mine average 100+. Here's what goes into them:

### 1. Domain Knowledge
My platform targets a specific regulated market. Every relevant agent has compliance rules, locale-specific business logic, and edge cases baked into its system prompt. The architect knows the data model constraints. The QA engineer knows the edge cases to always test. The reviewer has a checklist that includes regulatory compliance items.

This means I don't have to remind them every time. The knowledge persists across conversations.

### 2. Output Format Templates
Each agent has a structured output format. The architect produces tables of API endpoints and code blocks of model definitions. The reviewer produces a verdict (APPROVE / REQUEST CHANGES), a table of critical issues with file:line references, and a design compliance checklist.

This makes outputs **comparable across runs**. I can diff two architecture reviews or track whether issues from review round 1 were addressed in round 2.

### 3. Cross-Agent References
The dev agent's prompt says "follow the architect's design." The reviewer's prompt says "check against the architect's technical design." The QA agent's prompt references specific seed data and known test state.

They don't literally talk to each other — but they share a mental model of the pipeline.

---

## The Pipeline in Practice

Here's how a typical feature flows:

```
Me: "Design the notification system"
  → Architect agent produces technical design

Me: "Implement it" (pastes or references the design)
  → Dev agent writes code following the spec

Me: "Review this"
  → Reviewer agent examines code (cannot edit it)
  → 2nd Reviewer agent does independent blind review

Me: "Test it"
  → QA agent writes and runs test suite

Me: "Red team it"
  → Red Team agent tries prompt injection, data exfiltration,
    tenant boundary violations
```

I'm the orchestrator. I pass context between agents and make decisions at each gate. It's not fully automated — and that's intentional. The human-in-the-loop at each stage is what keeps quality high.

---

## Performance: What Actually Worked

### The Good

**Reviewer with no edit access is the best decision I made.** When the reviewer can't "just fix it," it has to articulate *what's wrong and why.* This produces better feedback. I've caught security issues, missing tenant isolation, and N+1 query patterns that I would have missed reviewing my own code.

**Domain knowledge in the prompt eliminates repeat mistakes.** Before I embedded locale-specific business logic into each agent, I was correcting the same errors every session — wrong weekend days, missing compliance checks, English-only outputs. After embedding it, these errors dropped to near zero.

**Structured output formats make agents composable.** Because the architect always outputs the same table format for API endpoints, the dev agent can parse and follow it. Because the reviewer always produces a table of issues with file:line references, I can track them systematically.

**Parallel agent execution is a real multiplier.** Running reviewer + QA + red team simultaneously on a feature cuts wall-clock time significantly. They're examining the same code from different angles, concurrently.

### The Surprising

**Two independent reviewers catch different things.** I was skeptical about having both a reviewer and a "reviewer2" (blind, independent). In practice, reviewer2 catches roughly 20-30% of issues that reviewer1 misses — and vice versa. The overlap is smaller than expected.

**The architect agent made me a better engineer.** Having to request a formal technical design before writing code forced me to think through data models and API contracts upfront. The agent doesn't just produce the design — the *process* of asking for one changes how I approach problems.

### The Honest

**Token costs are real.** Sixteen Opus-level agents with 100+ line system prompts is expensive. Each agent invocation loads that full prompt. For a solo founder, this matters. I could cut costs by moving some agents to Sonnet or Haiku — the doc writer and UX researcher don't need Opus-level reasoning.

**Some agents sit idle for weeks.** The SRE agent is ready for production incidents I don't have yet. The analytics agent tracks metrics for a user base that doesn't exist. They're insurance policies, not daily drivers. Whether that insurance is worth the setup cost is debatable.

**Context passing is manual and lossy.** I'm the glue between agents. When I summarize the architect's design for the dev agent, I might miss nuances. When I describe a bug for QA to reproduce, I might omit context. A tighter integration — where agents could reference each other's outputs directly — would help.

---

## Lessons for Builders

**1. Start with 4-5 agents, not 16.** Architect, dev, reviewer, QA, and one ops agent covers 90% of solo development. Add specialists when you feel the pain, not before.

**2. Tool scoping > role description.** Telling an agent "you are a reviewer" is weak. Giving it `Read, Grep` and *removing* `Edit, Write` is strong. Constraints create behavior.

**3. Embed domain knowledge aggressively.** The ROI on spending an hour writing compliance rules, edge cases, and business logic into an agent prompt is massive. You write it once; it applies to every future session.

**4. Structured output is non-negotiable.** If your agents return free-form text, you can't compose them into a pipeline. Define tables, checklists, and verdict formats from day one.

**5. The human stays in the loop.** These agents are not an autonomous pipeline. I make every gate decision — whether to proceed from design to implementation, whether to accept a review, whether a test suite is sufficient. The AI handles the work; I handle the judgment.

---

## What's Next

I'm exploring a few directions:

- **Agent-to-agent handoff** — letting the orchestrator agent pass context between specialists automatically, reducing my manual glue work
- **Memory across sessions** — agents that remember past designs, past review feedback, past test results, building institutional knowledge over time
- **Cost optimization** — routing to Haiku for simple tasks (doc generation, basic searches) and reserving Opus for reasoning-heavy work (architecture, security review)
- **Metrics** — tracking resolution rates, review catch rates, and token spend per agent to understand which agents deliver the most value

---

## The Bottom Line

Subagents aren't just "AI assistants with different hats." When you scope their tools, embed domain knowledge, structure their outputs, and wire them into a pipeline — they become something closer to a **simulated engineering org.**

It's not a replacement for a real team. It doesn't handle ambiguity, politics, or product intuition. But for a solo builder who needs to move fast without cutting corners on architecture, review, testing, and security — it's the closest thing to having a team that I've found.

Sixteen agents. One terminal. Ship it.

---

*Built with Claude Code's `.claude/agents/` framework. All agents run locally as subprocesses with scoped tool access.*
