# OmniDrop AI — Architecture Specification
**Version:** 2.0.0
**Updated:** 2026-03-28
**Status:** Scaffold complete. Phase 2 (business logic) pending.

---

## 1. System Overview

OmniDrop AI is a high-volume AI document ingestion and analytics platform for roofing
accounting teams. It ingests AccuLynx webhook events, classifies and processes both
structured documents (Invoices, Sales Proposals) and unstructured knowledge
(Field Manuals, MSDS sheets, Warranty documents) using a two-stage AI pipeline
(Unstructured.io → Claude), and surfaces analytics to C-Suite users via a Next.js
dashboard.

### Environment Pipeline
```
localhost → omnidrop.dev → sandbox.omnidrop.dev → omnidrop.ai
```

Each environment has its own:
- Supabase project (separate PostgreSQL + pgvector)
- Render.com deployment (separate Web Service + Worker + Redis)
- WorkOS environment
- Hookdeck workspace
- Sentry project

---

## 2. Full System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  INBOUND LAYER                                                              │
│                                                                             │
│  AccuLynx                                                                   │
│     │  POST webhook event                                                   │
│     ▼                                                                       │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │  Hookdeck  (Webhook Gateway)                                         │  │
│  │  • Receives event, ACKs AccuLynx IMMEDIATELY (< 200ms)              │  │
│  │  • Completely bypasses AccuLynx's 10-second webhook timeout         │  │
│  │  • Queues the event internally with automatic retry logic           │  │
│  │  • Re-signs event with HOOKDECK_SIGNING_SECRET                      │  │
│  │  • Delivers to FastAPI at its own generous timeout                  │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│     │  POST /api/v1/webhooks/acculynx  (Hookdeck-signed)                   │
│     ▼                                                                       │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│  API LAYER  (Render.com Web Service — omnidrop-api)                        │
│                                                                             │
│  FastAPI  /api/v1/webhooks/acculynx                                        │
│  1. Verify Hookdeck HMAC-SHA256 signature  → 401 if invalid               │
│  2. Validate payload shape (Pydantic)       → 422 if malformed            │
│  3. process_document.delay(job_payload)     → dispatch to Celery           │
│  4. Return 200 OK immediately               → Hookdeck ACKed              │
│                                                                             │
│  ⚡ This endpoint NEVER touches Unstructured.io, Claude, or Supabase.      │
└─────────────────────────────────────────────────────────────────────────────┘
     │  Redis queue (Render Key Value — omnidrop-redis)
     ▼

┌─────────────────────────────────────────────────────────────────────────────┐
│  WORKER LAYER  (Render.com Background Worker — omnidrop-worker)            │
│                                                                             │
│  Celery Task 1: process_document                                           │
│  ├── Fetches document bytes from AccuLynx API                             │
│  │   (respects 10 req/sec per key rate limit — Celery rate_limit option)  │
│  └── Calls UnstructuredService.partition_document()                       │
│      ┌────────────────────────────────────────────────────────────────┐   │
│      │  Unstructured.io  (Omni-Parser)                                │   │
│      │  • strategy="hi_res"  → Invoices, MSDS (image-heavy PDFs)     │   │
│      │  • strategy="fast"    → Digital text PDFs, Proposals           │   │
│      │  • strategy="auto"    → Unknown document types (default)       │   │
│      │  Output: list of typed elements                                │   │
│      │  [{type: "Title"|"Table"|"NarrativeText", text, metadata}]    │   │
│      └────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  Celery Task 2: triage_document  (Triage Agent)                            │
│  └── Claude receives plain text from Unstructured elements                │
│      └── Classifies document type:                                        │
│          ├── "structured"   → Invoice, Sales Proposal, Purchase Order     │
│          └── "unstructured" → Field Manual, MSDS, Warranty, Spec Sheet    │
│                                                                             │
│  ┌──────────────────────────┐    ┌──────────────────────────────────────┐  │
│  │  Path A: STRUCTURED      │    │  Path B: UNSTRUCTURED                │  │
│  │                          │    │                                      │  │
│  │  Task 3a: extract_struct │    │  Task 3b: chunk_and_embed            │  │
│  │  Claude extracts strict  │    │  Claude chunks text semantically     │  │
│  │  JSON schema:            │    │  → Generates vector embeddings       │  │
│  │  {vendor, invoice_num,   │    │  → Saves to pgvector for RAG        │  │
│  │   total, line_items...}  │    │  → Enables semantic search over     │  │
│  │  → Saves to Supabase     │    │    knowledge base                   │  │
│  │    relational tables     │    └──────────────────────────────────────┘  │
│  └──────────────────────────┘                                              │
└─────────────────────────────────────────────────────────────────────────────┘
     │  Supabase writes
     ▼

┌─────────────────────────────────────────────────────────────────────────────┐
│  DATA LAYER  (Supabase)                                                    │
│                                                                             │
│  PostgreSQL tables (structured data):                                      │
│    jobs, intake_events, documents, line_items, invoices                    │
│                                                                             │
│  pgvector table (unstructured knowledge — RAG):                            │
│    document_embeddings  →  enables semantic search over manuals/MSDS       │
└─────────────────────────────────────────────────────────────────────────────┘
     │  Next.js data fetching
     ▼

┌─────────────────────────────────────────────────────────────────────────────┐
│  PRESENTATION LAYER  (Next.js 15 — Vercel / Render Static)                │
│                                                                             │
│  WorkOS AuthKit protects all routes (SSO / Magic Links)                   │
│                                                                             │
│  /dashboard   → Celery task status, recent intake events (Tremor charts)  │
│  /analytics   → C-Suite KPIs: volume, accuracy, processing time           │
│  /search      → Semantic search over unstructured knowledge (RAG)         │
│  /settings    → WorkOS user management, AccuLynx connection config        │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Why Hookdeck Solves the AccuLynx 10-Second Timeout

AccuLynx retries webhooks if it doesn't receive a 200–299 within **10 seconds**.

**Without Hookdeck (risky):**
```
AccuLynx → FastAPI → must process OR dispatch AND respond in < 10s
           └─ risk: slow Celery broker connection causes AccuLynx to retry → duplicate jobs
```

**With Hookdeck (safe):**
```
AccuLynx → Hookdeck (ACKs in < 200ms ✓) → queue → FastAPI → 200 to Hookdeck
```

Hookdeck owns the AccuLynx relationship entirely. FastAPI only needs to satisfy
Hookdeck's delivery timeout (configurable, far more generous). AccuLynx never
waits on our infrastructure.

---

## 4. Document Processing Pipeline Details

### Unstructured.io Strategy Selection
| Document Type | Strategy | Reason |
|---------------|----------|--------|
| Roofing Invoice (scanned PDF) | `hi_res` | Requires OCR + layout analysis |
| Sales Proposal (digital PDF) | `fast` | Clean text, no OCR needed |
| MSDS Sheet | `hi_res` | Complex layout, tables, safety symbols |
| Field Manual | `fast` or `auto` | Usually digital text |
| Unknown type | `auto` | Unstructured picks the best strategy |

### Claude Triage Prompt Design (Phase 2)
The Triage Agent (Task 2) receives plain text and must classify into exactly:
- `"structured"` — contains line items, totals, dates, vendor info
- `"unstructured"` — reference/safety/instructional content
- `"unknown"` — insufficient content to classify (log and skip)

### Structured Extraction Schema (Target — Phase 2)
```json
{
  "vendor_name": "string",
  "invoice_number": "string",
  "invoice_date": "ISO 8601 date",
  "due_date": "ISO 8601 date | null",
  "subtotal": "float",
  "tax": "float",
  "total": "float",
  "line_items": [
    {"description": "string", "quantity": "float", "unit_price": "float", "amount": "float"}
  ],
  "notes": "string | null"
}
```

---

## 5. Complete Tech Stack

| Layer | Technology | Package / Version |
|-------|-----------|-------------------|
| Frontend | Next.js 15 (App Router) | `next@^15` |
| Frontend UI | Shadcn/UI + Tremor charts | `@tremor/react@^3` (Tailwind v3) |
| Auth | WorkOS AuthKit | `@workos-inc/authkit-nextjs` |
| Error Tracking (FE) | Sentry | `@sentry/nextjs@^8` |
| Backend API | FastAPI + Pydantic v2 | `fastapi@^0.115` |
| Webhook Gateway | Hookdeck | Infrastructure (dashboard config) |
| Task Queue | Celery + Redis | `celery[redis]@^5.4` |
| Document Parsing | Unstructured.io | `unstructured-client@^0.25` |
| AI Reasoning | Anthropic Claude | `anthropic@^0.30` (model: claude-opus-4-6) |
| Error Tracking (BE) | Sentry | `sentry-sdk[fastapi]@^2` |
| Database | Supabase (PostgreSQL) | `supabase@^2` |
| Vector Search | pgvector (Supabase extension) | enabled via migration |
| Hosting (API + Worker) | Render.com | `render.yaml` Blueprint |
| Local Dev | Docker Compose | Redis + FastAPI + Celery worker |
| CI/CD | GitHub Actions | `.github/workflows/` |

---

## 6. Render.com Deployment Architecture

```
Render.com Environment
├── omnidrop-api      (Web Service — FastAPI)
│   ├── build: pip install -r backend/requirements.txt
│   └── start: uvicorn backend.api.main:app --host 0.0.0.0 --port $PORT
│
├── omnidrop-worker   (Background Worker — Celery)
│   ├── build: pip install -r backend/requirements.txt
│   └── start: celery -A backend.workers.celery_app worker --loglevel=info --concurrency=4
│
├── omnidrop-redis    (Key Value — Redis)
│   └── maxmemoryPolicy: noeviction  (tasks NEVER silently dropped)
│
└── omnidrop-flower   (Web Service — Celery Monitoring UI, optional)
    └── start: celery -A backend.workers.celery_app flower
```

All secrets are managed via a **Render Environment Group** (`omnidrop-secrets`).
The Redis connection string is automatically injected via `fromService` reference —
no manual copy-paste of Redis URLs.

---

## 7. AccuLynx API Constraints (Non-Negotiable)

| Constraint | Value | Handled By |
|------------|-------|------------|
| Webhook response timeout | 10 seconds | Hookdeck (ACKs in < 200ms) |
| Rate limit per IP | 30 req/sec | Celery `rate_limit` task option |
| Rate limit per API key | 10 req/sec | Celery `rate_limit="10/s"` on fetch tasks |
| Webhook signature | HMAC-SHA256 | `backend/core/security.py` (Hookdeck secret) |
| 429 monitoring | — | Sentry (`failed_request_status_codes={429}`) |

---

## 8. Auth Layer (WorkOS)

```
Browser request
   │
   ▼
Next.js Middleware  (authkitMiddleware)
   │  Checks session cookie on every protected route
   │  Redirects to WorkOS hosted sign-in if unauthenticated
   ▼
WorkOS AuthKit  (hosted UI)
   │  SSO, Magic Links, MFA
   ▼
/callback  (handleAuth())
   │  Exchanges authorization code for encrypted session cookie
   ▼
Protected page  (withAuth() server / useAuth() client)
```

Public routes (no auth required):
- `/api/v1/webhooks/*` — authenticated by Hookdeck signature instead
- `/callback` — WorkOS callback

---

## 9. Security Model

| Concern | Implementation |
|---------|---------------|
| User authentication | WorkOS AuthKit (SSO, Magic Links, MFA) |
| Webhook verification | `HOOKDECK_SIGNING_SECRET` (HMAC-SHA256 in `backend/core/security.py`) |
| AccuLynx API key | Env var only — Render Environment Group |
| Supabase service role key | Server-side only — never in frontend |
| Celery task data | Passes only job IDs + event metadata — no raw secrets |
| CORS | Environment-specific allow-list in `backend/core/config.py` |
| API docs | `/docs` disabled when `APP_ENV=production` |
| Supabase RLS | TODO: Phase 2 |

---

## 10. Folder Structure

```
omnidrop-ai/
├── frontend/                      # Next.js 15 Application
│   ├── app/                       # App Router pages
│   │   ├── dashboard/page.tsx     # Task status + recent events (Tremor)
│   │   ├── analytics/page.tsx     # C-Suite KPIs
│   │   ├── settings/page.tsx      # Config + WorkOS user management
│   │   ├── callback/route.ts      # WorkOS auth callback
│   │   └── layout.tsx
│   ├── components/ui/             # Shadcn + Tremor chart components
│   ├── lib/
│   │   ├── supabase.ts            # Supabase browser client
│   │   └── api-client.ts          # Typed fetch wrapper for FastAPI
│   ├── middleware.ts               # WorkOS authkitMiddleware
│   └── package.json
│
├── backend/                       # FastAPI + Celery (single codebase, two Render services)
│   ├── api/
│   │   ├── main.py                # FastAPI entrypoint (Sentry init, CORS, routes)
│   │   └── v1/
│   │       └── webhooks.py        # POST /api/v1/webhooks/acculynx
│   ├── core/
│   │   ├── config.py              # Pydantic BaseSettings (all env vars)
│   │   ├── security.py            # Hookdeck signature verification
│   │   ├── sentry.py              # Sentry init (429 + 5xx capture)
│   │   └── logging.py             # Structured JSON logging
│   ├── workers/                   # Celery tasks (run by omnidrop-worker on Render)
│   │   ├── celery_app.py          # Celery app configuration
│   │   └── intake_tasks.py        # process_document, triage, extract, chunk_and_embed
│   ├── services/                  # Business logic (called from Celery tasks)
│   │   ├── unstructured_service.py  # Unstructured.io Omni-Parser wrapper
│   │   ├── claude_service.py        # Anthropic Claude triage + extraction
│   │   ├── supabase_client.py       # Supabase async client
│   │   └── temporal_client.py       # SUPERSEDED — kept for reference, not used
│   └── requirements.txt
│
├── shared/                        # Shared Python package (Pydantic models)
│   ├── models/
│   │   ├── acculynx.py            # AccuLynx webhook payload models
│   │   └── jobs.py                # Job input/output models
│   └── constants.py               # Rate limits, task queue names
│
├── supabase/
│   ├── migrations/
│   │   └── 00001_init.sql         # pgvector extension, placeholder tables
│   └── seed.sql
│
├── docker-compose.yml             # Local dev: Redis + FastAPI + Celery worker
├── render.yaml                    # Render.com Infrastructure as Code
├── Makefile                       # lint, test, dev, migrate targets
├── .env.example                   # All env var placeholders
├── .gitignore
└── ARCHITECTURE_SPEC.md           # This document
```

---

## 11. Local Development Quickstart

```bash
# 1. Clone and copy env
cp .env.example .env
# Fill in .env with real credentials

# 2. Install Python dependencies
pip install -e ./shared
pip install -r backend/requirements.txt

# 3. Install frontend dependencies
cd frontend && npm install && cd ..

# 4. Start Redis (required for Celery)
docker compose up -d redis

# 5. Start FastAPI backend
cd backend && uvicorn backend.api.main:app --reload --port 8000

# 6. Start Celery worker (separate terminal)
cd backend && celery -A backend.workers.celery_app worker --loglevel=info --concurrency=2

# 7. Start frontend (separate terminal)
cd frontend && npm run dev

# 8. Apply Supabase migrations
supabase db push

# Optional: RedisInsight task queue monitor
docker compose --profile debug up redisinsight
# → http://localhost:8001
```

**Service URLs:**
- Backend API docs: http://localhost:8000/docs
- Frontend: http://localhost:3000
- RedisInsight: http://localhost:8001 (debug profile only)

---

## 12. What Is NOT Yet Implemented (Phase 2)

- [ ] AccuLynx API client (fetch document bytes in `process_document` task)
- [ ] Hookdeck HMAC signature verification (`backend/core/security.py`)
- [ ] `UnstructuredService.partition_document()` implementation
- [ ] `ClaudeService.classify_document()` — Triage Agent prompt
- [ ] `ClaudeService.extract_invoice_schema()` — Structured extraction
- [ ] `ClaudeService.chunk_for_rag()` — Unstructured chunking + embeddings
- [ ] Supabase table migrations (jobs, documents, line_items, document_embeddings)
- [ ] Supabase RLS policies
- [ ] WorkOS middleware + callback route (uncomment stubs in `frontend/`)
- [ ] Sentry wizard (`npx @sentry/wizard@latest -i nextjs`)
- [ ] Tremor dashboard components (`frontend/app/dashboard/`)
- [ ] Render Environment Group `omnidrop-secrets` (create in Render dashboard before first deploy)
- [ ] Deploy targets in `.github/workflows/deploy-dev.yml`

---

## 13. Superseded Components (Kept for Reference)

The following were part of an earlier architecture iteration and have been superseded.
They remain in the repo for reference but are not used by the current pipeline:

| Component | Location | Superseded By |
|-----------|----------|---------------|
| Temporal.io workers | `workers/` (top-level) | Celery in `backend/workers/` |
| Azure Document Intelligence | `workers/activities/ocr_activities.py` | Unstructured.io |
| Merge.dev accounting push | `workers/activities/accounting_activities.py` | Out of current scope |
| `backend/services/temporal_client.py` | — | Celery `process_document.delay()` |
