# Technical Specification
# Omni-Intake AI Agent — Enterprise Edition

**Version:** 1.1
**Status:** Approved — Phase 2 Implementation
**Last Updated:** 2026-03-28
**Authoritative rules:** See `CLAUDE.md` for all non-negotiable implementation constraints.

---

## 1. Architecture Philosophy

The entire system is built on an **asynchronous, event-driven model**. No user-facing request ever waits on AI processing, document parsing, or external API calls. All heavy work is offloaded to the Celery queue immediately. This is enforced at the code level — see CLAUDE.md webhook rules.

---

## 2. Infrastructure & Hosting

### 2.1 Render.com Services (`render.yaml`)

| Service | Type | Purpose |
|---|---|---|
| `omnidrop-api` | Web Service (Python) | FastAPI — receives Hookdeck webhooks, serves REST API |
| `omnidrop-worker` | Background Worker (Python) | Celery — runs the full AI pipeline |
| `omnidrop-redis` | Key Value (Redis) | Celery broker + result backend |
| `omnidrop-flower` | Web Service (Python) | Celery monitoring UI (optional, remove for prod) |

**Frontend (Next.js 15) is hosted separately** — Vercel (recommended) or a Render Static Site. It is NOT colocated with the FastAPI service. They communicate via HTTP through `NEXT_PUBLIC_API_BASE_URL`.

**Secrets** are managed via a Render Environment Group named `omnidrop-secrets`. The Redis connection string is injected automatically via `fromService` reference — no manual copy-paste.

### 2.2 Scaling Strategy

Celery worker concurrency starts at 4 (`--concurrency=4`). For the initial 5,000-document bulk load, upgrade the worker to a Render Standard plan and increase concurrency. Render's auto-scaling (CPU/RAM triggers) requires at least a Standard plan — the Starter plan does not auto-scale.

### 2.3 Supabase Projects

| Environment | Project | Region |
|---|---|---|
| local / dev | `omnidrop-dev` (`njlbjdlicbmqvvegrics`) | us-west-1 |
| sandbox | `omnidrop-sandbox` (`rnhmvcpsvtqjlffpsayu`) | us-west-1 |
| production | `omnidrop-prod` (`zxxyscxoyqqvmlarpwdh`) | us-west-1 |

Each environment has fully isolated PostgreSQL + pgvector. Supabase RLS (Row Level Security) is a Phase 2 deliverable.

---

## 3. Data & AI Pipeline (Full Flow)

```
AccuLynx
  │  POST webhook event (10-second hard timeout)
  ▼
Hookdeck  ←── ACKs AccuLynx in < 200ms
  │  Queues event internally, re-signs with HOOKDECK_SIGNING_SECRET
  │  Delivers to FastAPI at its own generous timeout
  ▼
FastAPI  POST /api/v1/webhooks/acculynx
  1. Verify Hookdeck HMAC-SHA256 → 401 if invalid
  2. Validate payload (Pydantic) → 422 if malformed
  3. process_document.delay(payload) → push to Celery
  4. Return 200 OK  ← Hookdeck satisfied
  [This endpoint does NOTHING else]
  ▼
Redis (Celery Broker)
  ▼
Celery Worker: process_document
  │  Fetches document bytes from AccuLynx API
  │  Uses location_id to fetch the correct API key from Supabase
  │  rate_limit="10/s" per location key
  ▼
Celery Worker: triage_document  [Unstructured.io + Claude]
  │
  ├── Unstructured.io (Omni-Parser)
  │     Input:  raw PDF bytes / image
  │     Output: typed element list [{type, text, metadata}]
  │             NOT Markdown — typed structured elements
  │     Strategies: hi_res (scanned/OCR), fast (digital text), auto (unknown)
  │
  └── Claude claude-opus-4-6 (Triage Agent)
        Input:  plain text from Unstructured elements
        Output: "structured" | "unstructured" | "unknown"
  ▼
  ├── PATH A — STRUCTURED (Invoice, Proposal, PO)
  │     Celery: extract_struct
  │     Claude extracts JSON schema → validates with Pydantic
  │     Writes to Supabase: jobs, documents, invoices, line_items tables
  │
  └── PATH B — UNSTRUCTURED (Manual, MSDS, Warranty)
        Celery: chunk_and_embed
        Claude semantic chunking → vector embeddings
        Writes to Supabase: document_embeddings (pgvector)
        Enables RAG semantic search
```

---

## 4. AccuLynx Integration — Multi-Tenant Model

AccuLynx issues **one API key per roofing location**. There is no global API key.

```
User (Location Manager)
  → registers location + API key via /settings UI
  → key stored in Supabase locations table

Celery task (at runtime)
  → receives webhook payload with location_id
  → fetches API key from Supabase by location_id
  → uses that key for AccuLynx document fetch
  → rate_limit="10/s" applied per key
```

**Never use a single `ACCULYNX_API_KEY` env var for document fetching in production.** The env var in `omnidrop-secrets` is reserved for admin/testing purposes only.

### Rate Limits

| Constraint | Value | Enforcement |
|---|---|---|
| Webhook response timeout | 10 seconds | Hookdeck (ACKs in < 200ms) |
| Rate limit per IP | 30 req/sec | Celery worker concurrency cap |
| Rate limit per API key | 10 req/sec | `rate_limit="10/s"` on fetch tasks |
| 429 responses | — | Sentry `failed_request_status_codes={429}` |

---

## 5. Tech Stack

| Layer | Technology | Package |
|---|---|---|
| Frontend | Next.js 15 App Router, TypeScript strict | `next@^15` |
| UI | Shadcn/UI + Tremor charts | `@tremor/react@^3`, Tailwind CSS v3 |
| Auth | WorkOS AuthKit | `@workos-inc/authkit-nextjs` |
| Frontend error tracking | Sentry | `@sentry/nextjs@^8` |
| Backend API | FastAPI + Pydantic v2 | `fastapi@^0.115` |
| Webhook gateway | Hookdeck | Infrastructure (dashboard config) |
| Task queue | Celery + Redis | `celery[redis]@^5.4` |
| Document parsing | Unstructured.io Omni-Parser | `unstructured-client@^0.25` |
| AI reasoning | Anthropic Claude | `anthropic@^0.30` — model: `claude-opus-4-6` |
| Backend error tracking | Sentry | `sentry-sdk[fastapi]@^2` |
| Database | Supabase PostgreSQL | `supabase@^2` |
| Vector search | pgvector (Supabase extension) | enabled via migration |
| Hosting (API + Worker) | Render.com | `render.yaml` |
| CI/CD | GitHub Actions | `.github/workflows/` |

---

## 6. Database Schema (Supabase)

### Relational Tables (Structured Path)
```sql
jobs               — AccuLynx job record (job_id, location_id, status, created_at)
intake_events      — Raw webhook events log (event_id, job_id, payload, received_at)
documents          — Parsed document records (document_id, job_id, type, raw_path)
invoices           — Extracted invoice header (vendor_name, invoice_number, total, dates)
line_items         — Invoice line items (invoice_id, description, qty, unit_price, amount)
locations          — Roofing locations (location_id, user_id, name, acculynx_api_key)
```

### Vector Table (Unstructured Path)
```sql
document_embeddings — (id, document_id, chunk_text, embedding vector(1536), metadata jsonb)
```

### pgvector Setup
```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE INDEX ON document_embeddings USING ivfflat (embedding vector_cosine_ops);
```

### RLS (Phase 2)
All tables scoped by `location_id`. Users can only read/write rows matching their authenticated location.

---

## 7. Structured Extraction Schema (Claude Output)

```json
{
  "vendor_name": "string",
  "invoice_number": "string",
  "invoice_date": "ISO 8601",
  "due_date": "ISO 8601 | null",
  "subtotal": "float",
  "tax": "float",
  "total": "float",
  "line_items": [
    {
      "description": "string",
      "quantity": "float",
      "unit_price": "float",
      "amount": "float"
    }
  ],
  "notes": "string | null"
}
```

---

## 8. Auth Layer (WorkOS)

```
Browser request
  ▼
Next.js middleware.ts  (authkitMiddleware)
  Checks encrypted session cookie on every request
  Redirects unauthenticated users to WorkOS hosted sign-in
  ▼
WorkOS AuthKit  (hosted UI)
  SSO / Magic Links / MFA
  ▼
/callback  (handleAuth())
  Exchanges code for encrypted session cookie
  ▼
Protected page  (withAuth() server / useAuth() client)
```

**Public routes (no auth):**
- `/api/v1/webhooks/*` — authenticated by Hookdeck HMAC signature instead
- `/callback` — WorkOS OAuth callback

---

## 9. Security Model

| Concern | Implementation |
|---|---|
| User auth | WorkOS AuthKit (SSO, Magic Links, SAML, SCIM) |
| RBAC | WorkOS roles: Admin, Accountant, Manager, Viewer |
| Webhook verification | Hookdeck HMAC-SHA256 (`backend/core/security.py`) |
| Location API keys | Stored in Supabase `locations` table, fetched at task runtime |
| Supabase service role | Server-side + Celery workers only — never in frontend |
| Celery task payloads | Pass only `job_id` + `location_id` + metadata — no raw secrets |
| CORS | Environment-specific allow-list in `backend/core/config.py` |
| API docs | `/docs` disabled when `APP_ENV=production` |
| RLS | Supabase Row Level Security — Phase 2 |
| Error key name | `SENTRY_PYTHON_DSN` (not `SENTRY_DSN`) for backend/worker |

---

## 10. Observability

| Signal | Tool | What It Catches |
|---|---|---|
| Frontend exceptions | `@sentry/nextjs` | JS errors, failed API calls, Core Web Vitals |
| Backend exceptions | `sentry-sdk[fastapi]` | 4xx/5xx, unhandled exceptions |
| AccuLynx 429s | Sentry `failed_request_status_codes={429}` | Rate limit breaches |
| Task queue | Celery Flower (`omnidrop-flower`) | Queue depth, worker status, failure rate |
| Webhook delivery | Hookdeck dashboard | Retry count, delivery latency, error payloads |

---

## 11. Environment Variables Reference

| Variable | Used By | Notes |
|---|---|---|
| `SUPABASE_URL` | Backend, Worker | Project URL |
| `SUPABASE_KEY` | Frontend only | Anon key — safe for browser |
| `SUPABASE_SERVICE_ROLE_KEY` | Backend, Worker | Never in frontend |
| `ANTHROPIC_API_KEY` | Worker | Claude API |
| `HOOKDECK_SIGNING_SECRET` | Backend | HMAC verification |
| `CELERY_BROKER_URL` | Backend, Worker | Injected by Render from Redis service |
| `CELERY_RESULT_BACKEND` | Backend, Worker | Injected by Render from Redis service |
| `WORKOS_API_KEY` | Backend | Server-side only |
| `WORKOS_CLIENT_ID` | Frontend + Backend | OAuth client |
| `WORKOS_COOKIE_PASSWORD` | Backend | 32+ char session encryption key |
| `UNSTRUCTURED_API_KEY` | Worker | Omni-Parser |
| `SENTRY_PYTHON_DSN` | Backend, Worker | Note: NOT `SENTRY_DSN` |
| `NEXT_PUBLIC_SENTRY_DSN` | Frontend | Public DSN for browser |
| `NEXT_PUBLIC_SUPABASE_URL` | Frontend | Mirrors `SUPABASE_URL` |
| `NEXT_PUBLIC_SUPABASE_KEY` | Frontend | Mirrors `SUPABASE_KEY` |
| `NEXT_PUBLIC_API_BASE_URL` | Frontend | FastAPI service URL |
| `NEXT_PUBLIC_WORKOS_REDIRECT_URI` | Frontend | WorkOS callback URL |

---

## 12. Phase Status

### Phase 1 — Complete ✓
- Monorepo scaffold
- `render.yaml` IaC
- Docker Compose local dev
- Supabase projects provisioned (dev, sandbox, prod)
- All environment files populated
- `CLAUDE.md` agent rules established

### Phase 2 — In Progress (Agent Team)
See `docs/execution-plan.md` for task breakdown and team assignments.
See `docs/api-contracts.md` (generated by Lead agent) for endpoint definitions.
