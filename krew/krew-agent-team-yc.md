# Krew Dev Team — 16 AI Agents, 1 CTO

**Krew** is building an AI-powered HR department for Saudi companies. Instead of hiring a 16-person engineering team, we built 16 specialized Claude Code agents that run a full software development pipeline — from user stories to production monitoring.

## The Pipeline

Every feature flows through a strict sequence. No skipping steps.

## Dev Team (12 agents)

| # | Agent | Name | What They Do | Model | Special Sauce |
|---|-------|------|-------------|-------|--------------|
| 1 | **Product Owner** | Tariq | Writes user stories, acceptance criteria, gap analysis | Opus | Web search for Saudi labor law research |
| 2 | **UX Researcher** | Dana | Validates user flows, Saudi cultural UX norms, friction points | Sonnet | Web research on Saudi workplace patterns |
| 3 | **UI Designer** | Lina | Arabic-first, mobile-friendly interface design | Opus | **Google Gemini** as a second opinion via MCP |
| 4 | **System Architect** | Faisal | Data models, API contracts, tool schemas, technical blueprints | Opus | Can spawn sub-agents for deep research |
| 5 | **Senior Developer** | Rania | Writes production Python/FastAPI code from Faisal's designs | Opus | Full read/write/edit + sub-agents |
| 6 | **Code Reviewer #1** | Khaled | Quality, security, Saudi labor compliance, design adherence | Opus | Read-only (can't modify code) |
| 7 | **Code Reviewer #2** | Nasser | Independent second review — catches what Khaled missed | Sonnet | **OpenAI o3-mini** as a second brain via MCP |
| 8 | **QA Engineer** | Layla | Unit, integration, e2e tests + acceptance criteria validation | Opus | Can write tests and spawn sub-agents |
| 9 | **Prompt Tester** | Youssef | System prompt validation, tool-use testing, hallucination detection, bilingual quality | Opus | Tests the AI layer specifically |
| 10 | **Conversation Tester** | Huda | Multi-turn conversation testing with simulated personas | Opus | Custom `krew-sim` simulation library |
| 11 | **Red Team** | Zaid | Prompt injection, data exfiltration, PII leakage, tenant boundary attacks | Opus | Adversarial — tries to break everything |
| 12 | **Tech Writer** | Maha | API docs, agent capability docs, changelogs | Sonnet | — |

## Ops Team (4 agents)

| # | Agent | Name | What They Do | Model |
|---|-------|------|-------------|-------|
| 13 | **DevOps** | Sultan | CI/CD, Docker, GitHub Actions, deployment | Opus |
| 14 | **SRE** | Aws | Production monitoring, incidents, SLAs, postmortems | Opus |
| 15 | **DBA** | Majid | PostgreSQL + pgvector, migrations, indexing, backups | Sonnet |
| 16 | **Analytics** | Reema | Agent performance metrics, user behavior, CTO dashboards | Sonnet |

## How It Works

```
Tariq (PO) → Dana (UX) + Lina (UI) → Faisal (Architect) → Rania (Dev)
→ Khaled (Review) → Nasser (Review #2 w/ OpenAI) → Layla (QA)
→ Youssef (Prompt Test) → Huda (Conv Test) → Zaid (Red Team)
→ CTO approval → Ops team
```

## Why This Matters

- **Multi-model**: Claude Opus + Sonnet + OpenAI o3-mini + Google Gemini — agents cross-check each other using different AI providers via MCP
- **Adversarial by design**: Red team + 2 independent reviewers (one powered by a competing model) before anything ships
- **Domain-specific**: Every agent understands Saudi labor law, GOSI, Nitaqat, Arabic-first UX
- **1 human, 16 agents**: The CTO is the only human in the loop — approves at key gates, agents handle everything else
