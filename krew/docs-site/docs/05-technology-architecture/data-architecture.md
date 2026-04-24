# Data Infrastructure

## Data Architecture Overview

### Data Categories
| Category | Examples | Sensitivity | Storage |
|----------|----------|-------------|---------|
| **Company Config** | Policies, org chart, settings | Medium | PostgreSQL |
| **Employee PII** | Names, SSN, salary, bank info | Critical | Encrypted PostgreSQL |
| **Conversations** | Agent-employee chat history | High | PostgreSQL + Vector DB |
| **Documents** | Contracts, handbooks, resumes | High | Object storage (S3) |
| **Regulatory Data** | Labor laws, compliance rules | Low | Vector DB + PostgreSQL |
| **Analytics** | Metrics, reports, aggregations | Medium | Analytics DB / Data warehouse |
| **Audit Logs** | All agent actions and decisions | High | Append-only log store |

### Tech Stack (Recommended)

| Layer | Technology | Why |
|-------|-----------|-----|
| **Primary Database** | PostgreSQL (with pgvector) | Reliable, supports vector search |
| **Vector Database** | Pinecone or pgvector | RAG retrieval for agent context |
| **Object Storage** | AWS S3 / GCS | Documents, resumes, attachments |
| **Cache** | Redis | Session state, rate limiting |
| **Search** | Elasticsearch / OpenSearch | Full-text search across docs |
| **Queue** | Redis Streams or SQS | Async task processing |
| **Data Warehouse** | BigQuery or Snowflake | Analytics and reporting (Phase 2) |

### Multi-Tenancy
- **Approach:** Shared database with tenant isolation (row-level security)
- Every table has `company_id` column
- PostgreSQL Row-Level Security (RLS) enforced at DB level
- Consider dedicated schemas per customer for Enterprise tier

### Data Residency
- Default: US region (AWS us-east-1 or us-west-2)
- GCC customers: May need Middle East region (AWS me-south-1)
- EU customers: EU region required (GDPR)
- [ ] Define data residency requirements by market

## Data Pipeline

```
External Sources → Ingestion → Processing → Storage → Serving
                                                         ↓
Labor law feeds ──→ Parse ──→ Chunk + Embed ──→ Vector DB → Agents
Company docs ────→ Parse ──→ Chunk + Embed ──→ Vector DB → Agents
Employee data ───→ Validate → Encrypt ──────→ PostgreSQL → Agents
```

## Backup & Recovery
- Database: Continuous replication + daily snapshots
- Documents: Versioned object storage
- RPO (Recovery Point Objective): <1 hour
- RTO (Recovery Time Objective): <4 hours
