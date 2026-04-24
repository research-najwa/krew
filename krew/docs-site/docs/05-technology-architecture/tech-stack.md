# Platform Tech Stack

## Recommended Stack

### Backend
| Component | Technology | Rationale |
|-----------|-----------|-----------|
| **Language** | Python (primary), TypeScript (web) | Python for AI/ML ecosystem; TS for web |
| **API Framework** | FastAPI | Async, fast, great for AI workloads |
| **Agent Runtime** | LangGraph or custom | Stateful agent orchestration |
| **Task Queue** | Celery + Redis | Background jobs (payroll, reports) |
| **WebSocket** | FastAPI WebSocket | Real-time chat with agents |

### Frontend
| Component | Technology | Rationale |
|-----------|-----------|-----------|
| **Framework** | Next.js (React) | SEO, SSR, great ecosystem |
| **UI Library** | shadcn/ui + Tailwind | Fast development, clean design |
| **State Management** | React Query + Zustand | Server state + client state |
| **Charts** | Recharts or Tremor | Workforce analytics dashboards |

### Infrastructure
| Component | Technology | Rationale |
|-----------|-----------|-----------|
| **Cloud** | AWS (primary) | Most enterprise customers expect AWS |
| **Containers** | Docker + ECS or Kubernetes | Container orchestration |
| **CI/CD** | GitHub Actions | Simple, integrated with code |
| **Monitoring** | Datadog or Grafana | Observability |
| **Error Tracking** | Sentry | Error tracking and alerting |
| **Logging** | CloudWatch + ELK | Centralized logging |

### AI/ML
| Component | Technology | Rationale |
|-----------|-----------|-----------|
| **LLM Provider** | Anthropic Claude (primary) | Best reasoning + safety |
| **LLM Fallback** | OpenAI GPT-4o | Redundancy |
| **Vector DB** | Pinecone or pgvector | RAG retrieval |
| **Embeddings** | OpenAI or Cohere | Document embeddings |
| **Document Processing** | Unstructured.io or LlamaParse | PDF/doc parsing |

### Third-Party Services
| Service | Provider | Purpose |
|---------|----------|---------|
| **Email** | SendGrid or AWS SES | Transactional emails |
| **SMS** | Twilio | Notifications |
| **Auth** | Clerk or Auth0 | Authentication |
| **Payments** | Stripe | Subscription billing |
| **Document Signing** | DocuSign API | Offer letters, contracts |
| **Calendar** | Nylas or Google/Microsoft APIs | Scheduling |

## Development Practices
- Monorepo (Turborepo or Nx)
- Trunk-based development
- Feature flags (LaunchDarkly or Flagsmith)
- Automated testing (pytest + Playwright)
- Code review required for all merges
