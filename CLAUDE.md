# OmniDrop AI — Agent Operating Rules

All teammates read this file automatically. These rules are non-negotiable.
Full architecture detail is in `ARCHITECTURE_SPEC.md`.

---

## Context Window Protocol — 50% Rule (Non-Negotiable)

Every agent checks context usage after completing each discrete unit of work (one endpoint, one page, one migration, one reference doc).

**At 50% context used — execute this immediately:**

1. Finish the current function, migration, or component. Never stop mid-block.
2. Commit all changes: `git add [specific files] && git commit -m "[message]"`
3. Write `docs/handoffs/current.md` using the template in `docs/references/session-handoff-system.md`
4. Copy to `docs/handoffs/archive/YYYY-MM-DD-HHMM.md`
5. Send this message to Lead (or user if no Lead):

```
🟡 CONTEXT 50% — [Agent Name] — Handoff generated

Handoff: docs/handoffs/current.md
Last commit: [short hash] — [message]
Next task: [exact task name]

To resume: /ProjectHandoff
```

6. **STOP. Do not start the next task.**

**The 50% alert is a hard stop — not a suggestion.**
Do not rationalize continuing because "this task is almost done." Almost done at 80% context means broken code at 100%.

**Token efficiency rules (built into every task):**
- Prefer MCP tools over raw API calls when an MCP server is available
- Read only files needed for the current task — no exploratory browsing
- Use `mcp__plugin_supabase_supabase__execute_sql` for schema inspection, not the Python SDK
- Each agent session targets ONE deliverable: one endpoint, one page, one migration

---

## What We're Building

AI-powered **revenue recovery and financial interrogation platform** for roofing accounting teams.
The system acts as a financial detective — ingesting supplier invoices and cross-referencing them
against contracted pricing to surface revenue leakage at the line-item level.

AccuLynx sends webhook events → Hookdeck → FastAPI → Celery → Unstructured.io → Claude → Supabase.
Frontend: Next.js 15 dashboard serving two distinct personas — C-Suite (revenue recovery) and
Ops (HITL document review).

**Environment pipeline:** `app.omnidrop.dev` (alpha) → `app.omnidrop.ai` (V1.0 production)
**`omnidrop.ai`** — sales/marketing site (separate repo, not this codebase)
**Primary development target: `app.omnidrop.dev` — deploy there, validate with alpha users, then promote.**
localhost docker-compose is available for engineer convenience but is NOT the primary dev loop.

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

### Context Score Rubric — Must Live in `system_config` Table
The Context Score rubric weights MUST be stored in the `system_config` table under key
`context_score_rubric`. **Never hardcode rubric weights in prompt strings or Python code.**
The `score_context` task reads the rubric at runtime and injects it into the Claude prompt.
This allows recalibration via SQL update without a code deploy.

```python
# Correct pattern:
rubric = await get_system_config("context_score_rubric")
prompt = build_scoring_prompt(raw_text, rubric)

# Wrong — never do this:
prompt = "Award 15 points if vendor name is present..."
```

### Notification Channels — Vendor-Agnostic Pattern
The bounce-back notification system is channel-agnostic. Each location stores its channels in
`locations.notification_channels JSONB`. **Never hardcode Slack logic directly into the
`bounce_back` task.** Route through the channel adapter pattern:

```python
channel_config = location["notification_channels"]
adapter = get_notification_adapter(channel_config)  # SlackAdapter | AccuLynxAdapter | etc.
adapter.send(message)
```

Alpha ships with `SlackAdapter` only. `AccuLynxAdapter` and `SignalAdapter` are future additions
to the same interface. `AccuLynxAdapter` uses the location's existing `acculynx_api_key` —
no extra credentials needed. Test `@mention` syntax in the message body to confirm the
AccuLynx notification engine fires on API-created messages.

### Analytics Agent — Scope Rules
`ClaudeService.analytics_agent()` accepts `organization_id` (C-Suite) or `location_id` (branch).
- **C-Suite queries:** pass `organization_id`, no `location_id` — spans all locations in the org
- **Location queries:** pass `location_id` — scoped to that branch only
- **Never filter by `location_id` on a C-Suite query path**
- The schema description passed to Claude must include `pricing_contracts` and `revenue_findings`

### Freemium Gate — Check Before Dispatch
Before calling `process_document.delay()`, check document quota:

```python
if org["documents_processed"] >= org["max_documents"]:
    raise HTTPException(status_code=402, detail="Document quota reached. Upgrade to continue.")
```

This check happens in the FastAPI webhook endpoint AND the manual upload endpoint.
`documents_processed` increments in `_update_job_status` when `status='complete'`.

### Pricing Reference — Leakage Detection Gate
`detect_revenue_leakage` MUST check for a pricing reference before running:
1. Query `pricing_contracts` by `organization_id` — if rows exist, use Contract Mode
2. Else check `vendor_baseline_prices` view — if ≥ 3 samples per vendor, use Baseline Mode
3. If neither: log `leakage_skipped_reason='no_pricing_reference'` to job record and skip

**Never run leakage detection against an empty reference — it produces silent false negatives.**

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
| Embeddings | Voyage AI `voyage-3` 1024-dim (`voyageai`) |
| Database | Supabase PostgreSQL + pgvector |
| Hosting | Render.com (`render.yaml`) |
| Error Tracking | Sentry — `@sentry/nextjs` (FE), `sentry-sdk[fastapi]` (BE) |
| Notifications | Slack Incoming Webhooks (alpha) |

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
  app/
    dashboard/
      c-suite/page.tsx        ← Revenue Recovery Dashboard (org-scoped, cross-branch)
      ops/page.tsx             ← "Needs Clarity" HITL queue (medium-context docs)
      ops/jobs/[id]/page.tsx   ← Job review + response surface (Slack deep link target)
    search/page.tsx            ← RAG semantic search
    settings/page.tsx          ← Location config: AccuLynx key + Slack webhook URL
    onboarding/page.tsx        ← 5-step wizard (company → location → pricing → upload → findings)
    callback/route.ts          ← WorkOS auth callback
    layout.tsx
  middleware.ts                ← WorkOS authkitMiddleware
  lib/api-client.ts            ← Typed fetch wrapper — all FastAPI calls go through here

backend/
  api/v1/
    webhooks.py                ← THE critical endpoint (see rules above)
    documents.py               ← Manual upload endpoint (freemium gate lives here too)
    organizations.py           ← Org provisioning
    settings.py                ← Location + notification channel management
    analytics.py               ← KPI + vendor spend + leakage summary endpoints
    search.py                  ← RAG semantic search endpoint
    triage.py                  ← HITL review actions
  core/
    security.py                ← Hookdeck HMAC verification
    config.py                  ← Pydantic BaseSettings
    sentry.py                  ← Sentry init
    logging.py                 ← Structured JSON logging
  workers/
    intake_tasks.py            ← process_document, score_context, triage_document,
                                  extract_struct, chunk_and_embed,
                                  detect_revenue_leakage, bounce_back
    celery_app.py              ← Celery configuration
  services/
    unstructured_service.py    ← Unstructured.io wrapper
    claude_service.py          ← Scoring + triage + extraction + RAG + analytics + leakage
    notification_service.py    ← SlackAdapter (alpha); AccuLynxAdapter, SignalAdapter (future)
    supabase_client.py         ← Async Supabase client

shared/
  models/acculynx.py           ← AccuLynx webhook payload Pydantic models
  models/jobs.py               ← Job input/output models
  constants.py                 ← Rate limits, queue names
```

---

## Document Processing Pipeline

```
Celery Task 1: process_document
  → fetch document bytes from AccuLynx API (rate_limit="10/s", uses location API key)
  → call UnstructuredService.partition_document()

Celery Task 2: score_context  [Claude + system_config rubric]
  → score 0–100 against configurable rubric loaded from system_config table
  → output: {score, routing, breakdown, document_summary, clarification_question}
  ├── LOW  (0–39):   → bounce_back task — notify via Slack, job status='bounced'
  ├── MEDIUM (40–79): → triage_document — after extraction, triage_status='needs_clarity'
  └── HIGH (80–100): → triage_document — full pipeline, leakage detection eligible

Celery Task 3: triage_document  [Claude]
  → classify: "structured" | "unstructured" | "unknown"

Path A — structured (Invoice, Proposal, PO):
  Celery Task 4a: extract_struct  [Claude]
  → extract JSON schema with per-field confidence scores
  → save to Supabase: invoices + line_items tables
  → HIGH context:   → detect_revenue_leakage
  → MEDIUM context: → mark triage_status='needs_clarity', surface in /dashboard/ops queue

Path B — unstructured (MSDS, Manual, Warranty):
  Celery Task 4b: chunk_and_embed  [Claude + Voyage AI]
  → semantic chunks → 1024-dim embeddings → document_embeddings table

Celery Task 5: detect_revenue_leakage  [high-context structured docs only]
  → Contract Mode: compare line items vs pricing_contracts (organization_id scope)
  → Baseline Mode: compare vs vendor_baseline_prices view (fallback, ≥3 samples)
  → No reference: log leakage_skipped_reason, skip
  → write findings → revenue_findings table

Side path: bounce_back  [LOW context only]
  → read location.notification_channels
  → SlackAdapter (alpha): POST to webhook URL, include deep link to /dashboard/ops/jobs/[id]
  → AccuLynxAdapter (future): POST /jobs/{acculynx_job_id}/messages with @mention attempt
  → write to bounce_back_log, job status='bounced'
```

### Context Score Routing Thresholds
| Score | Label | Next Step | UI Surface |
|---|---|---|---|
| 80–100 | High | Full pipeline + leakage | /dashboard/c-suite findings |
| 40–79 | Medium | Full pipeline, flagged | /dashboard/ops queue |
| 0–39 | Low | Bounce back only | Slack message to field contact |

### Unstructured.io Strategy Selection
| Document Type | Strategy |
|---|---|
| Scanned invoice, MSDS | `hi_res` |
| Digital text PDF, Proposal | `fast` |
| Unknown | `auto` |

### Structured Extraction Schema (Claude output — with confidence scores)
```json
{
  "vendor_name":     {"value": "string",          "confidence": 0.0},
  "invoice_number":  {"value": "string",          "confidence": 0.0},
  "invoice_date":    {"value": "ISO 8601 date",   "confidence": 0.0},
  "due_date":        {"value": "ISO 8601 | null", "confidence": 0.0},
  "subtotal":        {"value": 0.0,               "confidence": 0.0},
  "tax":             {"value": 0.0,               "confidence": 0.0},
  "total":           {"value": 0.0,               "confidence": 0.0},
  "line_items": [
    {
      "description": {"value": "string", "confidence": 0.0},
      "quantity":    {"value": 0.0,      "confidence": 0.0},
      "unit_price":  {"value": 0.0,      "confidence": 0.0},
      "amount":      {"value": 0.0,      "confidence": 0.0}
    }
  ],
  "notes": {"value": "string | null", "confidence": 0.0}
}
```

---

## Auth Rules (WorkOS)

- `middleware.ts` runs `authkitMiddleware` on ALL routes
- Public routes (no auth): `/api/v1/webhooks/*`, `/callback`
- Protected routes use `withAuth()` (server) or `useAuth()` (client)
- Role-based dashboard routing: C-Suite role → `/dashboard/c-suite`, Ops/Accountant → `/dashboard/ops`
- `/settings` handles AccuLynx location key + Slack webhook URL per location

---

## What Is NOT Yet Implemented (Your Job)

### Database
- [x] `00002_application_tables.sql` — core tables exist
- [x] `00003_organizations.sql` — organizations + org_id FK columns exist
- [x] `00004_v3_pivot.sql` — freemium cols, notification_channels, pricing_contracts,
      revenue_findings, bounce_back_log, system_config (+ rubric seed),
      context_reference_examples, vendor_baseline_prices view, extended CHECK constraints
- [ ] Supabase RLS policies (stubs enabled, policies not yet written)

### Backend Pipeline
- [ ] AccuLynx API client (`fetch_acculynx_document` task)
- [ ] Hookdeck HMAC verification (`backend/core/security.py` stub)
- [ ] `UnstructuredService.partition_document()` implementation
- [ ] `ClaudeService.score_context()` — reads rubric from system_config, returns scored result
- [ ] `ClaudeService.classify_document()` — Triage Agent
- [ ] `ClaudeService.extract_invoice_schema()` — Structured extraction with confidence scores
- [ ] `ClaudeService.chunk_for_rag()` — RAG chunking + Voyage AI embeddings
- [ ] `ClaudeService.detect_leakage()` — compare line items vs contracts/baseline
- [ ] `score_context` Celery task (routes low/medium/high)
- [ ] `bounce_back` Celery task + `notification_service.py` SlackAdapter
- [ ] `detect_revenue_leakage` Celery task
- [ ] Freemium quota check in webhook + upload endpoints

### Frontend
- [ ] WorkOS middleware + `/callback` route
- [ ] Sentry initialization (`npx @sentry/wizard@latest -i nextjs`)
- [ ] `/dashboard/c-suite` — Revenue Recovery Dashboard (org-scoped leakage findings + Tremor)
- [ ] `/dashboard/ops` — HITL "Needs Clarity" queue (medium-context docs awaiting review)
- [ ] `/dashboard/ops/jobs/[id]` — split-screen review UI (Slack deep link target)
- [ ] `/onboarding` — 5-step wizard
- [ ] `/settings` — location config with Slack webhook URL input + test button
- [ ] Freemium usage counter in layout (documents_processed / max_documents)

### Deployment
- [ ] Render Environment Group `omnidrop-secrets` for omnidrop.dev
- [ ] `.github/workflows/deploy-dev.yml` — auto-deploy to omnidrop.dev on merge to main
- [ ] Hookdeck workspace pointed at omnidrop.dev API URL

---

## Superseded — Do Not Use or Extend

| Component | Location | Replaced By |
|---|---|---|
| Temporal.io workers | `workers/` (top-level) | Celery in `backend/workers/` |
| Azure Document Intelligence | `workers/activities/ocr_activities.py` | Unstructured.io |
| `temporal_client.py` | `backend/services/` | `process_document.delay()` |
| `/app/analytics/page.tsx` | `frontend/app/analytics/` | `/dashboard/c-suite` — do not extend |
