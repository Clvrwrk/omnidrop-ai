# OmniDrop AI — Architecture Specification
**Version:** 3.0.0
**Updated:** 2026-03-28
**Status:** V2 pivot complete. Phase 2 (business logic) pending.

---

## 1. System Overview

OmniDrop AI is a revenue recovery and financial interrogation platform for roofing accounting
teams. The primary objective is identifying lost revenue by cross-referencing supplier invoices
against contracted pricing documents and proposals — surfacing overcharges at the line-item level
across every branch of a multi-location roofing enterprise.

The system ingests documents via AccuLynx webhooks and direct upload, scores each document for
AI-processability (Context Score), classifies and extracts structured data, then runs leakage
detection against national pricing contracts. Low-quality documents are bounced back to the
field via Slack with a targeted clarification question. Medium-quality documents route to a
Human-in-the-Loop review queue.

### Environment Pipeline
```
omnidrop.dev → sandbox.omnidrop.dev → omnidrop.ai
```
`omnidrop.dev` is the **primary development and testing environment**.
Each environment has its own Supabase project, Render deployment, WorkOS environment,
Hookdeck workspace, and Sentry project.

---

## 2. Full System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  INBOUND LAYER                                                              │
│                                                                             │
│  AccuLynx  (or direct upload via /dashboard)                               │
│     │  POST webhook event                                                   │
│     ▼                                                                       │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │  Hookdeck  (Webhook Gateway)                                         │  │
│  │  • ACKs AccuLynx immediately (< 200ms)                              │  │
│  │  • Bypasses AccuLynx 10-second webhook timeout                      │  │
│  │  • Re-signs event with HOOKDECK_SIGNING_SECRET                      │  │
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
│  3. Check freemium quota                    → 402 if exceeded             │
│  4. process_document.delay(job_payload)     → dispatch to Celery           │
│  5. Return 200 OK immediately                                              │
│                                                                             │
│  ⚡ This endpoint NEVER touches Unstructured.io, Claude, or Supabase.      │
└─────────────────────────────────────────────────────────────────────────────┘
     │  Redis queue (Render Key Value — omnidrop-redis)
     ▼

┌─────────────────────────────────────────────────────────────────────────────┐
│  WORKER LAYER  (Render.com Background Worker — omnidrop-worker)            │
│                                                                             │
│  Task 1: process_document                                                  │
│  ├── Fetches document bytes from AccuLynx API (rate_limit="10/s")         │
│  └── Calls UnstructuredService.partition_document()                       │
│      └── Unstructured.io: strategy hi_res / fast / auto                  │
│                                                                             │
│  Task 2: score_context  ← NEW                                              │
│  └── Claude evaluates against configurable rubric (from system_config)    │
│      ├── LOW  (0–39):   ──────────────────────────────────────────────┐   │
│      ├── MEDIUM (40–79): ──────────────────────────────┐             │   │
│      └── HIGH (80–100): ─────────────────┐            │             │   │
│                                          ▼            ▼             ▼   │
│  Task 3: triage_document             triage        triage       bounce   │
│  └── Claude classifies:              (flagged)                   _back   │
│      ├── "structured"  → Task 4a                                       │
│      └── "unstructured"→ Task 4b                                       │
│                                                                           │
│  Task 4a: extract_struct  (structured path)                              │
│  └── Claude extracts JSON with per-field confidence scores              │
│      ├── HIGH context  → Task 5: detect_revenue_leakage                │
│      └── MEDIUM context→ mark triage_status='needs_clarity'            │
│                           surface in /dashboard/ops queue              │
│                                                                           │
│  Task 4b: chunk_and_embed  (unstructured path)                          │
│  └── Claude chunks → Voyage AI embeddings → pgvector                   │
│                                                                           │
│  Task 5: detect_revenue_leakage  ← NEW                                  │
│  ├── Contract Mode: compare line items vs pricing_contracts             │
│  └── Baseline Mode: compare vs vendor_baseline_prices view (fallback)  │
│      └── Write findings → revenue_findings table                       │
│                                                                           │
│  Side path: bounce_back  ← NEW  (LOW context only)                      │
│  └── NotificationService → SlackAdapter → POST to webhook URL           │
│      └── Message includes deep link to /dashboard/ops/jobs/[id]        │
└─────────────────────────────────────────────────────────────────────────────┘
     │  Supabase writes
     ▼

┌─────────────────────────────────────────────────────────────────────────────┐
│  DATA LAYER  (Supabase)                                                    │
│                                                                             │
│  Tenant hierarchy:  organizations → locations → jobs → documents          │
│                                  ↘ pricing_contracts (org-level)          │
│                                  ↘ revenue_findings  (org + location)     │
│                                                                             │
│  Structured:  jobs, documents, invoices, line_items                        │
│  Leakage:     pricing_contracts, revenue_findings                          │
│  Vector RAG:  document_embeddings (pgvector 1024-dim)                      │
│  AI Config:   system_config (rubric weights), context_reference_examples   │
│  Audit:       bounce_back_log                                              │
└─────────────────────────────────────────────────────────────────────────────┘
     │  Next.js data fetching
     ▼

┌─────────────────────────────────────────────────────────────────────────────┐
│  PRESENTATION LAYER  (Next.js 15)                                          │
│                                                                             │
│  WorkOS AuthKit — SSO / Magic Links / SCIM                                │
│                                                                             │
│  /dashboard/c-suite  → Revenue Recovery Dashboard (org-scoped, C-Suite)   │
│  /dashboard/ops      → "Needs Clarity" HITL queue (Accountant/Ops)        │
│  /dashboard/ops/jobs/[id] → Document review + Slack deep link target      │
│  /search             → RAG semantic search (knowledge base)               │
│  /settings           → Location config: AccuLynx key + Slack webhook URL  │
│  /onboarding         → 5-step wizard (new customer activation flow)       │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Context Score Engine

### Purpose
Evaluated immediately after Unstructured.io parses a document. Determines whether the AI
has enough context to process the document autonomously, route it for human review, or
bounce it back to the field for clarification.

### Phase 1 — Rubric-Based Scoring (alpha launch)
The rubric is stored in `system_config` table under key `context_score_rubric`. The
`score_context` task reads it at runtime and injects it into the Claude prompt.
This allows recalibration via a single SQL update — no code deploy required.

**Default rubric (seed into system_config at migration time):**
```json
{
  "identifiability": {
    "vendor_name_present": 15,
    "job_or_po_number_present": 10,
    "date_present": 5
  },
  "content_quality": {
    "legible_machine_readable_text": 20,
    "financial_data_present": 15,
    "document_type_unambiguous": 5
  },
  "metadata_and_context": {
    "file_metadata_present": 10,
    "linkable_to_known_vendor_or_job": 10,
    "specific_enough_to_act_on": 10
  }
}
```
Maximum score: 100. Thresholds: HIGH ≥ 80, MEDIUM 40–79, LOW ≤ 39.

The Claude prompt returns:
```json
{
  "score": 65,
  "routing": "medium",
  "breakdown": {"identifiability": 20, "content_quality": 30, "metadata_and_context": 15},
  "document_summary": "Appears to be an ABC Supply invoice — vendor name present but no job number",
  "clarification_question": "Which AccuLynx job number does this invoice belong to?"
}
```

`clarification_question` is only populated when `routing = "low"` — used directly in the
Slack bounce-back message. Single Claude API call; no separate prompt for the question.

### Phase 1.5 — Rubric Recalibration (post-alpha)
After accumulating data from multiple alpha customers, recalibrate rubric weights using
anonymized cross-customer patterns. Documents that scored medium but humans consistently
upgraded across all orgs indicate a miscalibrated threshold. Recalibration = SQL update to
`system_config`. Score distributions before/after are logged for audit.

### Phase 2 — Vector Enhancement (post-alpha, per-org)
Layer in vector similarity as a secondary ±15 point adjustment once an org has 500+
labeled examples in `context_reference_examples`. The rubric score remains the foundation.
`context_reference_examples` is populated automatically by HITL corrections in the
Ops dashboard — no manual seeding required.

```
final_score = clamp(rubric_score + vector_adjustment, 0, 100)
```

---

## 4. Revenue Leakage Detection

### Purpose
The core "Aha moment" feature. Compares extracted invoice line items against reference pricing
at the `organization_id` scope (not location-scoped), enabling a national roofing company to
detect when one branch is paying above the contracted national rate.

### Two Pricing Reference Modes

**Contract Mode** — customer has uploaded a formal pricing document:
- Claude extracts vendor/SKU/price rows from the uploaded document into `pricing_contracts`
- `detect_revenue_leakage` queries by `organization_id` + vendor_name
- Finding: invoiced unit price > contracted unit price by any amount

**Baseline Mode** — no formal contract, use invoice history as reference:
- `vendor_baseline_prices` view computes 90-day rolling average unit price per org/vendor/SKU
- Requires ≥ 3 invoice samples for a reliable baseline
- Finding: invoiced unit price > baseline × (1 + threshold), default threshold = 10%
- Findings labeled distinctly: "Paid 20% above your 90-day average" vs "Paid above contracted rate"

**No Reference** — neither mode available:
- `leakage_skipped_reason = 'no_pricing_reference'` logged to job record
- Ops dashboard prompts the customer to upload a pricing contract

### Finding Output (written to `revenue_findings`)
```
leakage_amount = (invoiced_unit_price - reference_unit_price) × quantity
```
Aggregated at C-Suite level: "Idaho Branch paid $42/bundle vs. national contract $35/bundle.
Total overcharge on this batch: $2,800."

---

## 5. Notification System (Bounce-Back)

### Purpose
When a document scores LOW context (0–39), do not route to the Ops queue. Immediately notify
the responsible party at the point of ingestion with a targeted clarification question.

### Channel-Agnostic Architecture
Each location stores its notification configuration in `locations.notification_channels JSONB`:

```json
{
  "slack": {
    "webhook_url": "https://hooks.slack.com/services/...",
    "channel": "#field-ops"
  }
}
```

Future adapters (same interface, no task changes required):
```json
{
  "acculynx": { "enabled": true },
  "signal": { "phone": "+15551234567" }
}
```

`AccuLynxAdapter` uses the location's existing `acculynx_api_key` to call
`POST /jobs/{acculynx_job_id}/messages`. Include `@mention` syntax in the message body
as best-effort notification — behavior must be tested to confirm the AccuLynx notification
engine fires on API-created messages.

### Alpha: Slack Incoming Webhook (one-way, no bot required)
Slack message format:
```
*OmniDrop — Document Needs Clarification*

📍 Location: [location name]
📄 Job: [acculynx_job_id]  |  File: [filename]
🔍 What we detected: [document_summary from score_context]

*Question:*
[clarification_question from score_context]

➡️  View document: https://omnidrop.dev/dashboard/ops/jobs/[job_id]
```

The deep link to `/dashboard/ops/jobs/[job_id]` is the response surface — the field
salesperson clicks through and either re-uploads or answers via the Ops HITL interface.
No Slack bot, no reply-capture infrastructure required for alpha.

### `bounce_back_log` Table
Every bounce-back is logged for: bounce rate analytics, identifying locations with no channel
configured, and audit trail.

---

## 6. Freemium Tier

| Limit | Free Tier | Pro | Enterprise |
|---|---|---|---|
| Documents | 500 | Unlimited | Unlimited |
| Users | 5 | Unlimited | Unlimited |
| Pricing contracts | 1 | Unlimited | Unlimited |
| Locations | 1 | Unlimited | Unlimited |

`organizations.plan_tier` values: `'free'` | `'pro'` | `'enterprise'`
`organizations.max_documents` default: `500`
`organizations.documents_processed` increments on each `status='complete'` job update.

Freemium gate enforced at both webhook endpoint and manual upload endpoint (return 402).

### Onboarding Wizard (`/onboarding`)
Five-step flow designed to deliver the Aha moment (found revenue) within the first batch:

1. **Company Setup** — name, timezone, invite up to 5 teammates
2. **Connect Location** — location name + AccuLynx API key + Slack webhook URL
3. **Unlock Revenue Detection** — upload pricing contract (PDF/spreadsheet) OR skip to Baseline Mode
   - Copy: "Customers who complete this step find an average of $8,400 in overcharges within their first 50 invoices."
   - Skip option: "Use my invoice history as the baseline instead"
4. **Process First Batch** — drag-and-drop upload zone; invoices prioritized over unstructured docs
5. **Your First Findings** — dashboard surfaces leakage findings prominently

Step 3 activates Contract Mode or Baseline Mode. Either path produces leakage findings.
Alpha delivery is sales-assisted — the wizard does not need to be fully self-serve for launch.

---

## 7. Database Schema

### Tenant Hierarchy
```
organizations (company root — national roofing enterprise)
  └── locations (individual branches — AccuLynx API key bound here)
        └── jobs (one per document processed)
              └── documents
                    ├── invoices + line_items  (structured path)
                    └── document_embeddings    (unstructured path)

organizations → pricing_contracts  (national contracts, org-scoped NOT location-scoped)
organizations + locations → revenue_findings  (leakage findings, queryable both ways)
```

### Key Tables

```sql
-- Tenant root
organizations (
  organization_id   UUID PK,
  workos_org_id     TEXT UNIQUE,
  name              TEXT NOT NULL,
  plan_tier         TEXT DEFAULT 'free',        -- 'free' | 'pro' | 'enterprise'
  max_documents     INTEGER DEFAULT 500,
  documents_processed INTEGER DEFAULT 0,
  max_users         INTEGER DEFAULT 5,
  created_at        TIMESTAMPTZ DEFAULT NOW()
)

-- Branches (AccuLynx API key bound here)
locations (
  location_id           UUID PK,
  organization_id       UUID FK → organizations,
  user_id               TEXT,
  name                  TEXT NOT NULL,
  acculynx_api_key      TEXT,
  connection_status     TEXT DEFAULT 'pending',
  notification_channels JSONB DEFAULT '{}',     -- {"slack": {"webhook_url": "..."}}
  created_at            TIMESTAMPTZ DEFAULT NOW(),
  updated_at            TIMESTAMPTZ DEFAULT NOW()
)

-- National pricing contracts (org-scoped — enables cross-branch leakage detection)
pricing_contracts (
  contract_id           UUID PK,
  organization_id       UUID FK → organizations,
  vendor_name           TEXT NOT NULL,
  sku                   TEXT,
  description           TEXT,
  contracted_unit_price NUMERIC(12,2) NOT NULL,
  effective_date        DATE,
  expiry_date           DATE,
  source_document_id    UUID,                    -- FK to documents if extracted from a file
  created_at            TIMESTAMPTZ DEFAULT NOW()
)

-- Revenue leakage findings
revenue_findings (
  finding_id            UUID PK,
  organization_id       UUID FK → organizations,
  location_id           UUID FK → locations,
  invoice_id            UUID FK → invoices,
  line_item_id          UUID FK → line_items,
  contract_id           UUID FK → pricing_contracts,  -- null if Baseline Mode
  reference_mode        TEXT NOT NULL,           -- 'contract' | 'baseline'
  vendor_name           TEXT,
  sku                   TEXT,
  invoiced_unit_price   NUMERIC(12,2),
  reference_unit_price  NUMERIC(12,2),
  quantity              NUMERIC(12,4),
  leakage_amount        NUMERIC(12,2),           -- (invoiced - reference) × quantity
  created_at            TIMESTAMPTZ DEFAULT NOW()
)

-- Bounce-back audit log
bounce_back_log (
  log_id          UUID PK,
  job_id          UUID FK → jobs,
  location_id     UUID FK → locations,
  organization_id UUID FK → organizations,
  context_score   INTEGER NOT NULL,
  channel_used    TEXT NOT NULL,                 -- 'slack' | 'acculynx' | 'signal' | 'none'
  message_sent    TEXT NOT NULL,
  delivery_status TEXT NOT NULL,                 -- 'sent' | 'failed' | 'no_channel'
  sent_at         TIMESTAMPTZ DEFAULT NOW()
)

-- AI configuration (rubric weights live here)
system_config (
  key        TEXT PRIMARY KEY,
  value      JSONB NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT NOW()
)
-- Seed: INSERT INTO system_config (key, value) VALUES ('context_score_rubric', '{...}')

-- Labeled examples for Phase 2 vector enhancement (populated by HITL corrections)
context_reference_examples (
  example_id      UUID PK,
  organization_id UUID FK → organizations,
  document_id     UUID FK → documents,
  label           TEXT NOT NULL,                 -- 'high' | 'medium' | 'low'
  label_source    TEXT NOT NULL,                 -- 'hitl_correction' | 'manual_seed'
  rubric_score    INTEGER NOT NULL,
  embedding       vector(1024),
  created_at      TIMESTAMPTZ DEFAULT NOW()
)
```

### Baseline Prices View
```sql
CREATE VIEW vendor_baseline_prices AS
SELECT
  organization_id,
  vendor_name,
  description,
  AVG(unit_price)    AS baseline_unit_price,
  STDDEV(unit_price) AS price_stddev,
  COUNT(*)           AS sample_count
FROM line_items li
JOIN invoices i USING (invoice_id)
WHERE i.created_at > NOW() - INTERVAL '90 days'
GROUP BY organization_id, vendor_name, description
HAVING COUNT(*) >= 3;
```

---

## 8. Complete Tech Stack

| Layer | Technology | Package / Version |
|---|---|---|
| Frontend | Next.js 15 (App Router) | `next@^15` |
| Frontend UI | Shadcn/UI + Tremor | `@tremor/react@^3` (Tailwind v3) |
| Auth | WorkOS AuthKit | `@workos-inc/authkit-nextjs` |
| Error Tracking (FE) | Sentry | `@sentry/nextjs@^8` |
| Backend API | FastAPI + Pydantic v2 | `fastapi@^0.115` |
| Webhook Gateway | Hookdeck | Infrastructure (dashboard config) |
| Task Queue | Celery + Redis | `celery[redis]@^5.4` |
| Document Parsing | Unstructured.io | `unstructured-client@^0.25` |
| AI Reasoning | Anthropic Claude | `anthropic@^0.30` (model: claude-opus-4-6) |
| Embeddings | Voyage AI | `voyageai` (voyage-3, 1024-dim) |
| Error Tracking (BE) | Sentry | `sentry-sdk[fastapi]@^2` |
| Database | Supabase (PostgreSQL) | `supabase@^2` |
| Vector Search | pgvector | enabled via migration |
| Notifications | Slack Incoming Webhooks | alpha; no additional package |
| Hosting | Render.com | `render.yaml` Blueprint |
| Local Dev | Docker Compose | Redis + FastAPI + Celery (convenience only) |
| CI/CD | GitHub Actions | `.github/workflows/deploy-dev.yml` |

---

## 9. Render.com Deployment Architecture

```
Render.com Environment (omnidrop.dev)
├── omnidrop-api      (Web Service — FastAPI)
│   └── start: uvicorn backend.api.main:app --host 0.0.0.0 --port $PORT
│
├── omnidrop-worker   (Background Worker — Celery)
│   └── start: celery -A backend.workers.celery_app worker --loglevel=info --concurrency=4
│
├── omnidrop-redis    (Key Value — Redis)
│   └── maxmemoryPolicy: noeviction
│
└── omnidrop-flower   (optional — Celery monitoring UI)
```

Secrets managed via Render Environment Group `omnidrop-secrets`.

---

## 10. AccuLynx API Constraints

| Constraint | Value | Handled By |
|---|---|---|
| Webhook response timeout | 10 seconds | Hookdeck (ACKs in < 200ms) |
| Rate limit per IP | 30 req/sec | Celery `rate_limit` |
| Rate limit per API key | 10 req/sec | Celery `rate_limit="10/s"` on fetch tasks |
| Webhook signature | HMAC-SHA256 | `backend/core/security.py` |
| 429 monitoring | — | Sentry `failed_request_status_codes={429}` |
| Job message API | POST /jobs/{id}/messages | Used by AccuLynxAdapter in bounce_back |

---

## 11. Auth Layer (WorkOS)

```
Browser request
   ▼
Next.js Middleware (authkitMiddleware) — all routes except /api/v1/webhooks/* and /callback
   ▼
WorkOS AuthKit (SSO, Magic Links, MFA, SCIM)
   ▼
/callback (handleAuth()) — exchanges code for encrypted session cookie
   ▼
Role-based routing:
  C-Suite role    → /dashboard/c-suite
  Ops/Accountant  → /dashboard/ops
  Admin           → /settings
```

---

## 12. Security Model

| Concern | Implementation |
|---|---|
| User auth | WorkOS AuthKit (SSO, Magic Links, MFA) |
| Webhook verification | `HOOKDECK_SIGNING_SECRET` HMAC-SHA256 |
| AccuLynx API key | Per-location, stored in Supabase, fetched at task runtime |
| Supabase service role key | Server-side only — never in frontend |
| Celery task data | Passes only job IDs + event metadata — no raw secrets |
| CORS | Environment-specific allow-list in `backend/core/config.py` |
| API docs | `/docs` disabled when `APP_ENV=production` |
| Supabase RLS | Scoped by `organization_id` — Phase 2 |
| Freemium quota | Enforced at API layer before Celery dispatch |

---

## 13. Folder Structure

```
omnidrop-ai/
├── frontend/
│   ├── app/
│   │   ├── dashboard/
│   │   │   ├── c-suite/page.tsx     # Revenue Recovery Dashboard
│   │   │   ├── ops/page.tsx         # HITL "Needs Clarity" queue
│   │   │   └── ops/jobs/[id]/page.tsx  # Document review + Slack deep link target
│   │   ├── search/page.tsx          # RAG semantic search
│   │   ├── settings/page.tsx        # Location config + Slack webhook URL
│   │   ├── onboarding/page.tsx      # 5-step activation wizard
│   │   ├── callback/route.ts        # WorkOS auth callback
│   │   └── layout.tsx
│   ├── components/ui/               # Shadcn + Tremor components
│   ├── lib/
│   │   ├── supabase.ts
│   │   └── api-client.ts
│   └── middleware.ts
│
├── backend/
│   ├── api/
│   │   ├── main.py
│   │   └── v1/
│   │       ├── webhooks.py          # Critical endpoint
│   │       ├── documents.py         # Manual upload
│   │       ├── organizations.py
│   │       ├── settings.py          # Location + notification channel management
│   │       ├── analytics.py         # KPIs + leakage summary
│   │       ├── search.py
│   │       └── triage.py
│   ├── core/
│   │   ├── config.py
│   │   ├── security.py
│   │   ├── sentry.py
│   │   └── logging.py
│   ├── workers/
│   │   ├── celery_app.py
│   │   └── intake_tasks.py          # All 7 tasks
│   ├── services/
│   │   ├── unstructured_service.py
│   │   ├── claude_service.py
│   │   ├── notification_service.py  # SlackAdapter + future adapters
│   │   └── supabase_client.py
│   └── requirements.txt
│
├── shared/
│   ├── models/
│   │   ├── acculynx.py
│   │   └── jobs.py
│   └── constants.py
│
├── supabase/
│   ├── migrations/
│   │   ├── 00001_init.sql                  # pgvector + uuid extensions
│   │   ├── 00002_application_tables.sql    # locations, jobs, documents, invoices, line_items, document_embeddings
│   │   ├── 00003_organizations.sql         # organizations table + org_id columns on all tables
│   │   └── 00004_v3_pivot.sql              # V3 additions: freemium cols, notification_channels,
│   │                                       # pricing_contracts, revenue_findings, bounce_back_log,
│   │                                       # system_config (+ rubric seed), context_reference_examples,
│   │                                       # vendor_baseline_prices view, extended CHECK constraints
│
├── docker-compose.yml
├── render.yaml
├── Makefile
├── .env.example
└── ARCHITECTURE_SPEC.md
```

---

## 14. What Is NOT Yet Implemented

### Database (start here — blocks everything else)
- [x] `00002_application_tables.sql` — core tables exist
- [x] `00003_organizations.sql` — organizations + org_id FK columns exist
- [x] `00004_v3_pivot.sql` — V3 additions: freemium cols, notification_channels, new tables, rubric seed, view
- [ ] Supabase RLS policies (scoped by `organization_id`) — stubs enabled, policies not yet written

### Backend Pipeline
- [ ] AccuLynx API client (`fetch_acculynx_document` task)
- [ ] Hookdeck HMAC verification (`backend/core/security.py`)
- [ ] `UnstructuredService.partition_document()` implementation
- [ ] `ClaudeService.score_context()` — rubric from `system_config`, single API call
- [ ] `ClaudeService.classify_document()` — Triage Agent
- [ ] `ClaudeService.extract_invoice_schema()` — confidence-scored extraction
- [ ] `ClaudeService.chunk_for_rag()` — chunking + Voyage AI embeddings
- [ ] `ClaudeService.detect_leakage()` — Contract Mode + Baseline Mode
- [ ] `score_context` Celery task (routing gate)
- [ ] `bounce_back` Celery task
- [ ] `detect_revenue_leakage` Celery task
- [ ] `notification_service.py` — `SlackAdapter`
- [ ] Freemium quota check in webhook + upload endpoints

### Frontend
- [ ] WorkOS middleware + `/callback` route
- [ ] Sentry initialization
- [ ] `/dashboard/c-suite` — revenue recovery + cross-branch leakage Tremor charts
- [ ] `/dashboard/ops` — HITL "Needs Clarity" queue
- [ ] `/dashboard/ops/jobs/[id]` — split-screen document review
- [ ] `/onboarding` — 5-step activation wizard
- [ ] `/settings` — location config with Slack webhook URL + test button
- [ ] Freemium usage counter in layout

### Deployment
- [ ] Render Environment Group `omnidrop-secrets` (omnidrop.dev)
- [ ] `.github/workflows/deploy-dev.yml`
- [ ] Hookdeck workspace → omnidrop.dev URL

---

## 15. Superseded Components

| Component | Location | Superseded By |
|---|---|---|
| Temporal.io workers | `workers/` (top-level) | Celery in `backend/workers/` |
| Azure Document Intelligence | `workers/activities/ocr_activities.py` | Unstructured.io |
| Merge.dev accounting push | `workers/activities/accounting_activities.py` | Out of scope |
| `backend/services/temporal_client.py` | — | Celery `process_document.delay()` |
| `/app/analytics/page.tsx` | `frontend/app/analytics/` | `/dashboard/c-suite` |
