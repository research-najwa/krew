# AI Model & LLM Strategy

## Model Selection Criteria
1. **Reasoning quality** — HR decisions require nuanced judgment
2. **Instruction following** — Agents must follow company policies precisely
3. **Safety & alignment** — Cannot give harmful advice on employment matters
4. **Cost efficiency** — Must keep COGS low for healthy margins
5. **Speed** — Employee-facing agents need fast response times
6. **Privacy** — Employee data must not be used for model training
7. **Multi-language** — English first, Arabic and others later

## Recommended Model Architecture

### Multi-Model Strategy (Route by Task Complexity)

| Task Type | Model | Rationale |
|-----------|-------|-----------|
| Simple Q&A (policies, PTO balance) | Small/fast model (Claude Haiku, GPT-4o-mini) | High volume, low cost |
| Complex reasoning (compliance analysis, conflict resolution) | Large model (Claude Opus, GPT-4) | Accuracy critical |
| Document generation (handbooks, offer letters) | Mid model (Claude Sonnet, GPT-4o) | Balance of quality and cost |
| Classification/routing | Fine-tuned small model or embeddings | Speed and cost |
| Data extraction (resume parsing, document processing) | Specialized model or mid-tier | Structured output |

### Why Multi-Model?
- 80% of queries can be handled by cheaper, faster models
- Only 20% need expensive large models
- Reduces average cost per query by 60–70%
- Improves response time for simple queries

## Model Providers to Evaluate
| Provider | Models | Pros | Cons |
|----------|--------|------|------|
| **Anthropic (Claude)** | Opus, Sonnet, Haiku | Best safety/alignment, strong reasoning | API dependency |
| **OpenAI** | GPT-4, GPT-4o, GPT-4o-mini | Broad capabilities, fast | Data privacy concerns |
| **Open Source** | Llama 3, Mistral, Qwen | Self-hosted = full control | Infra cost, maintenance |
| **Google** | Gemini models | Good multi-language | Less proven in enterprise |
| **Cohere** | Command R+ | Good for enterprise search/RAG | Smaller ecosystem |

## RAG (Retrieval-Augmented Generation) Architecture
Each agent needs access to company-specific knowledge:

```
Employee Question → Query Understanding → Retrieve Relevant Context → Generate Answer

Context Sources:
├── Company policies & handbook
├── Employee data (profile, PTO, comp)
├── Labor laws (by jurisdiction)
├── Previous interactions & decisions
├── Industry best practices
└── Company-specific configurations
```

### Vector Database Options
- Pinecone (managed, easy)
- Weaviate (open source, flexible)
- Qdrant (open source, performant)
- pgvector (if already using PostgreSQL)

## Fine-Tuning Strategy
- **Phase 1:** Use prompt engineering + RAG (no fine-tuning)
- **Phase 2:** Fine-tune small models on HR-specific tasks where quality matters
- **Phase 3:** Train specialized models for high-volume tasks (resume parsing, classification)

## Cost Estimation (Per 100-Employee Customer)

| Component | Monthly Queries | Cost/Query | Monthly Cost |
|-----------|----------------|------------|-------------|
| Employee Q&A | 200 | $0.02 | $4 |
| Complex queries | 50 | $0.20 | $10 |
| Document generation | 10 | $0.50 | $5 |
| Compliance checks | 20 | $0.10 | $2 |
| Background processing | 100 | $0.01 | $1 |
| **Total inference** | | | **~$22/month** |

> Leaves healthy margin on $3,000/month revenue (100 employees x $30)

## Questions to Decide
- [ ] Primary LLM provider? (Recommend starting with Anthropic Claude)
- [ ] Self-host any models? (Not recommended for MVP)
- [ ] Build vs. buy for RAG infrastructure?
- [ ] Data residency requirements? (May need regional deployments)
