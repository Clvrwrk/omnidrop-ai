# OmniDrop AI — Agent Operating Rules

All teammates read this file automatically. These rules are non-negotiable.
Full architecture detail is in `ARCHITECTURE_SPEC.md`.

---

## What We're Building

High-volume AI document ingestion platform for roofing accounting teams.
AccuLynx sends webhook events → Hookdeck → FastAPI → Celery → Unstructured.io → Claude → Supabase.
Frontend: Next.js 15 dashboard for C-Suite analytics and semantic document search.

**Environment pipeline:** `localhost → omnidrop.dev → sandbox.omnidrop.dev → omnidrop.ai`

---

## Non-Negotiable Rules

### Webhook Endpoint (backend/api/v1/webhooks.py)
The `POST /api/v1/webhooks/acculynx` endpoint MUST do exactly four things in this order:
1. Verify Hookdeck HMAC-SHA256 signature → return `401` if invalid
2. Validate payload shape with Pydantic → return `422` if malformed
3. Call `process_document.delay(job_payload)` → dispatch to Celery
4. Return `200 OK` immediately

**This endpoint NEVER calls Unstructured.io, Claude, or Supabase. No exceptions.**

### AccuLynx API — Multi-Tenant Architecture
AccuLynx API keys are **per-location, per-user**. There is no global key.
- Each client has multiple roofing locations
- Each location has its own AccuLynx API key
- Clients enter their location keys via the `/settings` UI
- Keys are stored in Supabase, fetched at task runtime by `location_id`
- **Never reference a single `ACCULYNX_API_KEY` env var for production logic**

### AccuLynx Rate Limits
| Limit | Value | Enforcement |
|---|---|---|
| Per IP | 30 req/sec | Celery `rate_limit` |
| Per API key | 10 req/sec | `rate_limit="10/s"` on fetch tasks |
| 429 monitoring | — | Sentry `failed_request_status_codes={429}` |

**Never write synchronous AccuLynx API calls outside a Celery task.**

### Celery Rate Limit Pattern
```python
@celery_app.task(rate_limit="10/s")
def fetch_acculynx_document(location_id: str, document_id: str):
    # Fetch API key from Supabase using location_id
    ...
```

### Supabase Service Role Key
- `SUPABASE_SERVICE_ROLE_KEY` is server-side only — never expose to frontend
- Frontend uses `SUPABASE_KEY` (anon key) only
- All worker/service writes use the service role key

### Sentry DSN Variable Name
Backend and Celery workers: `SENTRY_PYTHON_DSN` (NOT `SENTRY_DSN`)

---

## Tech Stack (Quick Reference)

| Layer | Technology |
|---|---|
| Frontend | Next.js 15 App Router, TypeScript strict, Tailwind CSS v3 |
| UI Components | Shadcn/UI + Tremor (`@tremor/react@^3`) |
| Auth | WorkOS AuthKit (`@workos-inc/authkit-nextjs`) |
| Backend | FastAPI + Pydantic v2 |
| Webhook Gateway | Hookdeck (infrastructure, not a library) |
| Task Queue | Celery + Redis (`celery[redis]@^5.4`) |
| Document Parsing | Unstructured.io (`unstructured-client@^0.25`) |
| AI | Anthropic Claude `claude-opus-4-6` (`anthropic@^0.30`) |
| Database | Supabase PostgreSQL + pgvector |
| Hosting | Render.com (`render.yaml`) |
| Error Tracking | Sentry — `@sentry/nextjs` (FE), `sentry-sdk[fastapi]` (BE) |

---

## File Ownership (Agent Teams)

| Agent | Owns |
|---|---|
| Frontend Engineer | `/frontend/**` |
| Backend Plumber | `/backend/api/**`, `/backend/workers/**`, `/backend/core/**`, `/shared/**`, `docker-compose.yml`, `render.yaml` |
| AI & QA Engineer | `/backend/services/**`, `/tests/**` |

**Agents ONLY edit files within their assigned directories.**
Cross-boundary changes must go through the Lead.

---

## Folder Structure (Key Files)

```
frontend/
  app/dashboard/       ← Celery task status + Tremor charts
  app/analytics/       ← C-Suite KPIs
  app/search/          ← RAG semantic search
  app/settings/        ← AccuLynx location key config + WorkOS user mgmt
  app/callback/        ← WorkOS auth callback
  middleware.ts         ← WorkOS authkitMiddleware (all routes except /api/v1/webhooks/* and /callback)
  lib/api-client.ts    ← Typed fetch wrapper — all FastAPI calls go through here

backend/
  api/v1/webhooks.py   ← THE critical endpoint (see rules above)
  core/security.py     ← Hookdeck HMAC verification (stub exists, needs implementation)
  core/config.py       ← Pydantic BaseSettings
  workers/intake_tasks.py  ← process_document, triage_document, extract_struct, chunk_and_embed
  services/unstructured_service.py  ← Unstructured.io wrapper
  services/claude_service.py        ← Triage + extraction + RAG chunking
  services/supabase_client.py       ← Async Supabase client
  services/temporal_client.py       ← SUPERSEDED — do not use or extend

shared/
  models/acculynx.py   ← AccuLynx webhook payload Pydantic models
  models/jobs.py       ← Job input/output models
  constants.py         ← Rate limits, queue names
```

---

## Document Processing Pipeline

```
Celery Task 1: process_document
  → fetch document bytes from AccuLynx API (rate_limit="10/s", uses location API key)
  → call UnstructuredService.partition_document()

Celery Task 2: triage_document  [Claude]
  → classify: "structured" | "unstructured" | "unknown"

Path A — structured (Invoice, Proposal, PO):
  Celery Task 3a: extract_struct  [Claude]
  → extract JSON schema → save to Supabase relational tables

Path B — unstructured (MSDS, Manual, Warranty):
  Celery Task 3b: chunk_and_embed  [Claude]
  → semantic chunks → pgvector embeddings → Supabase document_embeddings table
```

### Unstructured.io Strategy Selection
| Document Type | Strategy |
|---|---|
| Scanned invoice, MSDS | `hi_res` |
| Digital text PDF, Proposal | `fast` |
| Unknown | `auto` |

### Structured Extraction Schema (Claude output)
```json
{
  "vendor_name": "string",
  "invoice_number": "string",
  "invoice_date": "ISO 8601",
  "due_date": "ISO 8601 | null",
  "subtotal": "float",
  "tax": "float",
  "total": "float",
  "line_items": [{"description": "string", "quantity": "float", "unit_price": "float", "amount": "float"}],
  "notes": "string | null"
}
```

---

## Auth Rules (WorkOS)

- `middleware.ts` runs `authkitMiddleware` on ALL routes
- Public routes (no auth): `/api/v1/webhooks/*`, `/callback`
- Protected routes use `withAuth()` (server) or `useAuth()` (client)
- `/settings` page handles AccuLynx location key management

---

## What Is NOT Yet Implemented (Phase 2 — Your Job)

- [ ] AccuLynx API client (`fetch_acculynx_document` task)
- [ ] Hookdeck HMAC verification (`backend/core/security.py` stub)
- [ ] `UnstructuredService.partition_document()` implementation
- [ ] `ClaudeService.classify_document()` — Triage Agent
- [ ] `ClaudeService.extract_invoice_schema()` — Structured extraction
- [ ] `ClaudeService.chunk_for_rag()` — RAG chunking + embeddings
- [ ] Supabase migrations: `jobs`, `documents`, `line_items`, `invoices`, `document_embeddings` tables
- [ ] WorkOS middleware + `/callback` route
- [ ] Sentry initialization (frontend + backend)
- [ ] Tremor dashboard + analytics + search pages
- [ ] `/settings` page — AccuLynx location key entry UI
- [ ] API contracts between frontend and backend (defined in `docs/api-contracts.md`)

---

## Superseded — Do Not Use or Extend

| Component | Location | Replaced By |
|---|---|---|
| Temporal.io workers | `workers/` (top-level) | `backend/workers/` (Celery) |
| Azure Document Intelligence | `workers/activities/ocr_activities.py` | Unstructured.io |
| `temporal_client.py` | `backend/services/` | `process_document.delay()` |
