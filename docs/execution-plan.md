# Coding Team Execution Plan
# Omni-Intake AI Agent — Phase 2

**Version:** 1.1
**Status:** Approved — Ready to Execute
**Last Updated:** 2026-03-28

**Agent team spawn prompt:** `docs/agent-team-spawn-prompt.md`
**Architecture rules:** `CLAUDE.md`
**Full tech spec:** `docs/technical-spec.md`

---

## Team Structure

Phase 2 is executed by a 4-agent Claude Code team with strict file ownership
boundaries to prevent race conditions. The team maps directly to the three
implementation squads below plus the Lead Orchestrator.

| Agent Team Role | Squad Equivalent | File Ownership |
|---|---|---|
| Lead Orchestrator | — | Coordination only, no file edits |
| Teammate 1 — Frontend Engineer | Squad C | `/frontend/**` |
| Teammate 2 — Backend Plumber | Squad A + B (infra/plumbing) | `/backend/api/**`, `/backend/workers/**`, `/backend/core/**`, `/shared/**`, `docker-compose.yml`, `render.yaml` |
| Teammate 3 — AI & QA Engineer | Squad B (AI logic) + QA | `/backend/services/**`, `/tests/**` |

---

## Squad A — Infrastructure & Backend Plumbing

**Agent:** Teammate 2 — Backend Plumber
**Objective:** Data moves securely from Hookdeck → FastAPI → Celery → services. No blocking I/O anywhere in the request path.

| Task | Description | Deliverable | Status |
|---|---|---|---|
| Repo scaffold | Monorepo with Next.js, FastAPI, Celery | Foundation | ✅ Complete |
| `render.yaml` | Render.com Infrastructure as Code | 4 services defined | ✅ Complete |
| Docker Compose | Local Redis + API + Worker | `docker-compose.yml` | ✅ Complete |
| Supabase provisioning | Dev / sandbox / prod projects | 3 projects active | ✅ Complete |
| Database migrations | `jobs`, `documents`, `invoices`, `line_items`, `document_embeddings`, `locations` tables | `supabase/migrations/` | 🔲 Phase 2 |
| Hookdeck HMAC verification | `backend/core/security.py` — verify_hookdeck_signature() using HMAC-SHA256 | 401 on invalid sig | 🔲 Phase 2 |
| Webhook endpoint | `POST /api/v1/webhooks/acculynx` — 4 steps only, 200 OK | Core intake route | 🔲 Phase 2 |
| Celery task signatures | 4 tasks in `intake_tasks.py` with `rate_limit="10/s"` | Task scaffolding | 🔲 Phase 2 |
| Shared Pydantic models | `shared/models/acculynx.py`, `shared/models/jobs.py`, `shared/constants.py` | Type-safe payloads | 🔲 Phase 2 |
| Supabase async client | `backend/services/supabase_client.py` wired with service role key | DB connection | 🔲 Phase 2 |
| REST API endpoints | FastAPI routes per `docs/api-contracts.md` | Frontend-ready API | 🔲 Phase 2 |
| Sentry backend init | `sentry-sdk[fastapi]` with `SENTRY_PYTHON_DSN`, 429 capture | Error tracking | 🔲 Phase 2 |
| Render env group | Create `omnidrop-secrets` in Render dashboard | Production secrets | 🔲 Phase 2 |
| CI/CD pipeline | `.github/workflows/deploy-dev.yml` | Auto-deploy to dev | 🔲 Phase 2 |

**Non-negotiable constraints:**
- Webhook endpoint does ONLY the 4 allowed steps — see CLAUDE.md
- AccuLynx API key is per-location — fetch from Supabase `locations` table at task runtime
- Redis `maxmemoryPolicy: noeviction` — tasks must never be silently dropped

---

## Squad B — AI Engineering

**Agent:** Teammate 3 — AI & QA Engineer (services portion)
**Objective:** Implement the full Unstructured.io → Claude pipeline and own all test coverage.

| Task | Description | Deliverable | Status |
|---|---|---|---|
| UnstructuredService | `partition_document()` with strategy selection (hi_res/fast/auto) | Typed element output | 🔲 Phase 2 |
| Claude Triage Agent | `classify_document()` — prompt for "structured" \| "unstructured" \| "unknown" | Document routing | 🔲 Phase 2 |
| Structured extraction | `extract_invoice_schema()` — Claude extracts JSON, Pydantic validation | Invoice JSON to Supabase | 🔲 Phase 2 |
| RAG chunking + embedding | `chunk_for_rag()` — semantic chunks → pgvector upsert | Semantic search enabled | 🔲 Phase 2 |
| Text-to-SQL agent | `analytics_agent()` — CMD+K text → safe parameterized Postgres query | Analytics CMD+K | 🔲 Phase 3 |
| HITL confidence scoring | Add confidence scores to extraction output → surface low-confidence fields | Accountant review queue | 🔲 Phase 3 |
| Integration tests | `tests/test_webhook.py` — HMAC, Pydantic, Celery dispatch, 200 response | Webhook test coverage | 🔲 Phase 2 |
| Unit tests | `tests/test_services.py` — all ClaudeService methods with fixture docs | Service test coverage | 🔲 Phase 2 |

**AI model:** `claude-opus-4-6` for all Claude calls.

**Unstructured.io strategy selection:**

| Document Type | Strategy | Reason |
|---|---|---|
| Scanned invoice (image PDF) | `hi_res` | Requires OCR + layout analysis |
| Digital proposal / text PDF | `fast` | Clean text, no OCR needed |
| MSDS sheet | `hi_res` | Complex layout, safety tables |
| Field manual (digital) | `fast` | Usually clean text |
| Unknown type | `auto` | Unstructured picks best strategy |

**QA mandate:** Teammate 3 is the active feedback loop for the full team. Protocol on violation detection:
1. Write a failing test demonstrating the issue
2. Message the offending teammate directly with test path + CLAUDE.md rule violated
3. If unresolved within 2 tasks, escalate to Lead

---

## Squad C — Frontend & UX

**Agent:** Teammate 1 — Frontend Engineer
**Objective:** Zero-cognitive-load UI. Every screen loads fast, guides the user to one action, and requires no training.

| Task | UI Screen | Route | Description | Status |
|---|---|---|---|---|
| WorkOS auth integration | Screen 5 | `/callback`, `middleware.ts` | authkitMiddleware, handleAuth(), session cookie | 🔲 Phase 2 |
| Sentry frontend init | — | — | `npx @sentry/wizard -i nextjs`, `NEXT_PUBLIC_SENTRY_DSN` | 🔲 Phase 2 |
| API client | — | `lib/api-client.ts` | Typed fetch wrapper for all FastAPI calls | 🔲 Phase 2 |
| Omni-Drop dashboard | Screens 2 & 15 | `/dashboard` | Drag-and-drop upload zone + Celery task status feed + Tremor charts | 🔲 Phase 2 |
| Analytics CMD+K | Screens 3 & 9 | `/analytics` | C-Suite KPIs — Tremor Metric/BarList/AreaChart, natural language query bar | 🔲 Phase 2 |
| Semantic search | — | `/search` | RAG query input → ranked document results with source excerpts | 🔲 Phase 2 |
| HITL triage screen | Screens 4 & 7 | `/triage` | Split-screen PDF viewer + extracted fields with confidence scores | 🔲 Phase 2 |
| Settings — locations | — | `/settings` | AccuLynx location key registration UI, connection status per location | 🔲 Phase 2 |
| System health dashboard | Screens 10 & 14 | `/dashboard` (admin) | Webhook status, Celery queue depth, rate limit monitoring | 🔲 Phase 2 |

**UI rules (non-negotiable):**
- Tremor (`@tremor/react@^3`) for all charts and metrics — no Chart.js, no raw Recharts
- Shadcn/UI for all primitive components (buttons, inputs, dialogs, tables)
- Tailwind CSS v3 for layout and spacing
- `SUPABASE_KEY` (anon) only in frontend — service role key never crosses to browser

**Dependency:** Frontend data-fetching components depend on `docs/api-contracts.md` — Lead generates this in Phase 0 before frontend implements API calls.

---

## Phase 0 — Lead Orchestrator Pre-Work

Before spawning any teammate, the Lead completes:

| Task | Output | Why |
|---|---|---|
| Read and internalize `CLAUDE.md` | — | Establishes approval criteria |
| Define all FastAPI endpoints | `docs/api-contracts.md` | Unblocks frontend data fetching |
| Define TypeScript response interfaces | `docs/api-contracts.md` | Type safety across the boundary |
| Define Supabase table schemas | `docs/api-contracts.md` | Unblocks both backend migrations and frontend reads |
| Create initial task list (19 tasks) | Shared task list | Enables teammate self-claiming |

---

## Execution Sequence

```
Phase 0 (Lead):    API contracts defined → docs/api-contracts.md
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
Squad A (Backend):  Squad B (AI/QA):  Squad C (Frontend):
  HMAC verify         UnstructuredSvc   WorkOS auth
  Webhook endpoint    Claude triage     Sentry init
  Celery tasks        Extraction        API client
  Shared models       RAG chunking      Dashboard UI
  DB migrations       Integration tests Analytics UI
  REST endpoints      Unit tests        Search + HITL
         │               │               │
         └───────────────┼───────────────┘
                         ▼
                  Lead: Final synthesis
                  Lead: Clean up team
```

---

## Definition of Done

A Phase 2 task is complete when:
- [ ] Implementation is within the assigned file ownership boundary
- [ ] At least one test exists covering the implemented logic
- [ ] No CLAUDE.md rules are violated (QA engineer validates)
- [ ] No synchronous AccuLynx calls outside a Celery task
- [ ] No secrets hardcoded in any file
- [ ] Lead has approved the plan before implementation began
