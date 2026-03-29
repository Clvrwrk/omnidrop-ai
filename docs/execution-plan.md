# OmniDrop AI — Beta V1.0 Execution Plan

**Version:** 2.0
**Status:** Approved — Ready to Execute
**Date:** 2026-03-29
**Supersedes:** Phase 2 plan (v1.1 — archived)

**Design spec:** `docs/superpowers/specs/2026-03-29-beta-v1-triage-plan-design.md`
**Architecture rules:** `CLAUDE.md`
**API contracts:** `docs/api-contracts.md`
**Agent spawn prompt:** `docs/agent-team-spawn-prompt.md`

---

## Current State

| Layer | Status |
|---|---|
| Celery pipeline (6 tasks) | ✅ Production-ready — do not touch |
| Claude service methods | ✅ Production-ready — do not touch |
| Unstructured.io service | ✅ Production-ready — do not touch |
| Hookdeck HMAC + webhook endpoint | ✅ Production-ready — do not touch |
| Database migrations (00001–00004) | ✅ Applied — do not touch |
| WorkOS middleware + /callback | ✅ Production-ready — do not touch |
| API client (lib/api-client.ts) | ✅ 25 typed methods — do not touch |
| Backend API endpoints (18) | ⚠️ Stub → must implement |
| Frontend pages (8) | ⚠️ Routing exists, zero UI design |
| RLS policies | ❌ Missing entirely |
| Supabase Storage bucket | ❌ Missing entirely |
| Celery retry strategy | ❌ Missing on all 6 tasks |
| Reference docs (12 services) | ❌ Missing entirely |

---

## Team Structure

| Agent | Track | File Ownership |
|---|---|---|
| Lead Orchestrator | Pre-work + coordination + integration | No file edits — coordination only |
| Teammate 1 — Frontend Engineer | Track 3: UI/UX | `/frontend/**` |
| Teammate 2 — Backend Plumber | Track 2: API completion | `/backend/api/**`, `/backend/core/**`, `/shared/**` |
| Teammate 3 — AI & QA Engineer | Track 1: References + RLS + retries + tests | `/backend/services/**`, `/tests/**`, `/docs/references/**`, `/backend/workers/**` |

---

## Lead Pre-Work

Complete all items below **before spawning any teammate**. These unblock all three tracks.

| # | Task | File | Done |
|---|---|---|---|
| L1 | Fix `VECTOR(1536)` → `VECTOR(1024)` in embedding schema | `docs/api-contracts.md` | ☐ |
| L2 | Verify `00004_v3_pivot.sql` has: `bounced` job status, `notification_channels` on locations, `context_score`/`context_score_routing`/`clarification_question` on documents | Supabase SQL check | ☐ |
| L3 | Add `system_config` table schema to api-contracts.md | `docs/api-contracts.md` | ☐ |
| L4 | Create `docs/references/README.md` with index + standard template | `docs/references/README.md` | ☐ |
| L5 | Spawn all three teammates with their track assignments | Agent spawn | ☐ |

**Spawn prompt for each teammate:** See `docs/agent-team-spawn-prompt.md`

---

## Track 1 — AI & QA Engineer (Teammate 3)

**Start after:** Lead Pre-Work complete
**One task per agent session. Stop at 50% context.**

| # | Task | Deliverable | File(s) | Done |
|---|---|---|---|---|
| T1-01 | Write migration `00005` — two parts: (1) `ALTER TABLE jobs ADD COLUMN clarification_question TEXT` (missing from 00004); (2) RLS policies for all 7 tables + V3 tables | `supabase/migrations/00005_rls_and_fixes.sql` | ☐ |
| T1-02 | Add Celery retry strategy to all 6 tasks: `max_retries=3`, `retry_backoff=True`, `on_failure` handler | `backend/workers/intake_tasks.py` | ☐ |
| T1-03 | Write `docs/references/supabase.md` — CLI, MCP tools, direct API, RLS patterns, Storage SOPs | `docs/references/supabase.md` | ☐ |
| T1-04 | Write `docs/references/voyage-ai.md` — SDK setup, embedding call pattern, 1024-dim config | `docs/references/voyage-ai.md` | ☐ |
| T1-05 | Write `docs/references/unstructured.md` — SDK, strategy selection, hi_res vs fast, API key SOP | `docs/references/unstructured.md` | ☐ |
| T1-06 | Write `docs/references/hookdeck.md` — CLI, dashboard, HMAC setup, webhook SOP | `docs/references/hookdeck.md` | ☐ |
| T1-07 | Write `docs/references/sentry.md` — init wizard, DSN variables, error capture patterns | `docs/references/sentry.md` | ☐ |
| T1-08 | Write `docs/references/workos.md` — AuthKit setup, redirect URIs, role assignment SOP | `docs/references/workos.md` | ☐ |
| T1-09 | Write `docs/references/render.md` — CLI, env group, deploy hooks, migration-before-restart pattern | `docs/references/render.md` | ☐ |
| T1-10 | Write `docs/references/acculynx.md` — API auth, rate limits, per-location key pattern, webhook SOP | `docs/references/acculynx.md` | ☐ |
| T1-11 | Write `docs/references/cronjob.md` — scheduling patterns for future maintenance tasks | `docs/references/cronjob.md` | ☐ |
| T1-12 | Write `docs/references/servicetitan.md`, `jobnimbus.md`, `jobtread.md` — future integrations overview only | 3 files in `docs/references/` | ☐ |
| T1-13 | Write integration tests: full pipeline webhook → process → score → extract | `tests/test_pipeline_integration.py` | ☐ |
| T1-14 | Write unit tests: all ClaudeService methods, UnstructuredService, NotificationService | `tests/test_services.py` | ☐ |

---

## Track 2 — Backend Plumber (Teammate 2)

**Start after:** Lead Pre-Work complete (especially L1-L3 — api-contracts.md must be correct)
**One endpoint group per agent session. Stop at 50% context.**

All endpoints must: use `mcp__plugin_supabase_supabase__execute_sql` for schema inspection, return real Supabase data, include WorkOS auth extraction from session, and apply `organization_id` / `location_id` scoping.

| # | Task | Endpoints | File | Done |
|---|---|---|---|---|
| T2-01 | Document upload — store bytes to Supabase Storage, create jobs row, dispatch `process_document.delay()`, freemium quota gate | `POST /api/v1/documents/upload` | `backend/api/v1/documents.py` | ☐ |
| T2-02 | Jobs list + detail — query jobs by location/org with pagination | `GET /api/v1/jobs`, `GET /api/v1/jobs/{job_id}` | `backend/api/v1/jobs.py` | ☐ |
| T2-03 | Events — list intake_events with pagination | `GET /api/v1/events` | `backend/api/v1/events.py` | ☐ |
| T2-04 | Organizations — lazy-provision org from WorkOS session + list users | `GET /api/v1/organizations/me`, `GET /api/v1/organizations/me/users` | `backend/api/v1/organizations.py` | ☐ |
| T2-05 | Location CRUD — list locations (api_key_last4 only), create location + store encrypted API key, update location | `GET /api/v1/settings/locations`, `POST /api/v1/settings/locations`, `PATCH /api/v1/settings/locations/{id}` | `backend/api/v1/settings.py` | ☐ |
| T2-06 | Notification channels — save Slack webhook URL, send test message via SlackAdapter | `PATCH /api/v1/settings/locations/{id}/notifications`, `POST /api/v1/settings/locations/{id}/notifications/test` | `backend/api/v1/settings.py` | ☐ |
| T2-07 | Pricing contracts — parse uploaded contract file (CSV/PDF), insert rows into `pricing_contracts` | `POST /api/v1/settings/pricing-contracts` | `backend/api/v1/settings.py` | ☐ |
| T2-08 | Triage list + detail — list `triage_status='pending'` docs, return full extraction with confidence scores + signed Supabase Storage URL | `GET /api/v1/triage`, `GET /api/v1/triage/{document_id}` | `backend/api/v1/triage.py` | ☐ |
| T2-09 | Triage corrections — save HITL edits, write corrected fields to `context_reference_examples` | `PATCH /api/v1/triage/{document_id}` | `backend/api/v1/triage.py` | ☐ |
| T2-10 | Analytics KPIs — SQL aggregation: volume, accuracy rate, avg processing time, total invoice value | `GET /api/v1/analytics/kpis` | `backend/api/v1/analytics.py` | ☐ |
| T2-11 | Analytics detail — vendor-spend grouped by vendor/job/month, leakage findings summary for C-Suite | `GET /api/v1/analytics/vendor-spend`, `GET /api/v1/analytics/leakage` | `backend/api/v1/analytics.py` | ☐ |
| T2-12 | Search — pgvector semantic search via `chunk_and_embed` output | `GET /api/v1/search` | `backend/api/v1/search.py` | ☐ |

---

## Track 3 — Frontend Engineer (Teammate 1)

**Start after:** Track 2 T2-01 through T2-04 complete (upload + jobs + orgs endpoints must be live for dashboard)
**One page per agent session. Use `frontend-design` skill for every page. Stop at 50% context.**

All pages must: use `lib/api-client.ts` exclusively (no raw `fetch()`), use Tremor for charts/metrics, Shadcn/UI for primitives, Tailwind v3 for layout.

| # | Task | Route | Description | Done |
|---|---|---|---|---|
| T3-01 | Onboarding wizard — 5 steps: company → location → AccuLynx key → pricing contract upload → first findings | `/onboarding` | Multi-step form with progress indicator. Each step calls the relevant settings endpoint. | ☐ |
| T3-02 | Main dashboard — drag-and-drop upload zone + real-time Celery job status feed | `/dashboard` | Dropzone component, job status cards with processing stages, freemium counter in layout | ☐ |
| T3-03 | C-Suite revenue recovery — org-scoped leakage findings, vendor overcharge breakdown, Tremor charts | `/dashboard/c-suite` | Tremor BarList (vendor spend), AreaChart (leakage trend), KPI metrics row | ☐ |
| T3-04 | Settings — location config, AccuLynx key input, Slack webhook URL + test button, pricing contract upload | `/settings` | Tabbed layout: Locations tab, Notifications tab, Pricing tab | ☐ |
| T3-05 | Ops queue — HITL "Needs Clarity" document queue, medium-context docs awaiting accountant review | `/dashboard/ops` | Table with confidence score column, filter by location, sort by date | ☐ |
| T3-06 | Job review — split-screen: PDF viewer (signed URL) + extracted fields with confidence indicators + correction form | `/dashboard/ops/jobs/[id]` | Two-panel layout. Slack deep link target. Per-field confidence badges. | ☐ |
| T3-07 | Semantic search — CMD+K bar → ranked document results with source excerpts | `/search` | Command palette style. Results show document name, excerpt, confidence score. | ☐ |
| T3-08 | Sentry frontend init + freemium counter in layout + final polish pass | `layout.tsx`, `middleware.ts` | `npx @sentry/wizard@latest -i nextjs`, usage counter component in nav | ☐ |

---

## Execution Sequence

```
Lead Pre-Work (L1–L4): schema fixes + api-contracts update + references template
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
Track 1 (T3):         Track 2 (T2):      Track 3 (T1):
T1-01 RLS policies    T2-01 Upload       Waits for T2-01–T2-04
T1-02 Celery retries  T2-02 Jobs         ──────────────────────
T1-03 Supabase ref    T2-03 Events       T3-01 Onboarding
T1-04 Voyage ref      T2-04 Orgs         T3-02 Dashboard
T1-05 Unstructured    T2-05 Locations    T3-03 C-Suite
T1-06 Hookdeck        T2-06 Notifs       T3-04 Settings
T1-07 Sentry          T2-07 Pricing      T3-05 Ops queue
T1-08 WorkOS          T2-08 Triage list  T3-06 Job review
T1-09 Render          T2-09 Triage patch T3-07 Search
T1-10 AccuLynx        T2-10 Analytics    T3-08 Sentry + polish
T1-11 Cronjob         T2-11 Leakage
T1-12 Future refs     T2-12 Search
T1-13 Integration tests
T1-14 Unit tests
              │               │               │
              └───────────────┼───────────────┘
                              ▼
                 Lead: Integration test
                 Full pipeline: upload → process → score →
                 extract → leakage → C-Suite dashboard ✅
                 Bounce-back test: low-context → Slack ✅
                 HITL test: medium-context → Ops queue → correction ✅
                              ▼
                         Beta V1.0 ✅
```

---

## Definition of Done — Beta V1.0

### Backend
- [ ] All 18 API endpoints return real Supabase data
- [ ] `POST /documents/upload` stores file to Supabase Storage + dispatches Celery
- [ ] All 6 Celery tasks have `max_retries=3`, `retry_backoff=True`, `on_failure` handler
- [ ] RLS policies written and applied on all 7 tables
- [ ] Freemium quota gate active on upload + webhook endpoints

### Frontend
- [ ] All 8 pages designed and implemented using `frontend-design` skill
- [ ] All pages use Tremor for charts, Shadcn/UI for primitives, Tailwind v3
- [ ] No raw `fetch()` outside `lib/api-client.ts`
- [ ] Freemium counter visible in layout (`documents_processed / max_documents`)

### Reference Docs
- [ ] 12 reference docs exist in `docs/references/`
- [ ] Every doc has CLI, MCP, Direct API, and OmniDrop-Specific Patterns sections
- [ ] Every doc has at least one Human SOP with the exact resume message format
- [ ] `docs/references/README.md` indexes all docs

### Integration
- [ ] Full pipeline tested end-to-end on `app.omnidrop.dev`
- [ ] Bounce-back: low-context doc → Slack message delivered
- [ ] HITL: medium-context doc → Ops queue → accountant confirms → written to `context_reference_examples`

### Deployment
- [ ] App runs end-to-end on `app.omnidrop.dev`
- [ ] `deploy-dev.yml` runs migrations before service restart
- [ ] Sentry capturing errors in both backend and frontend

---

## Out of Scope for Beta V1.0

- Stripe billing (freemium enforced, upgrade is manual)
- Self-serve sign-up (sales-assisted)
- ServiceTitan, JobNimbus, JobTread implementation (reference docs only)
- Signal + AccuLynx notification adapters
- Mobile app, SCIM, fine-tuning
- Text-to-SQL analytics agent (Phase 3)
- Vector-based Context Score enhancement (needs 500+ labeled examples)

---

## Agent Operating Rules (Summary)

Every agent:
1. Reads `CLAUDE.md` before starting any task
2. Works on ONE deliverable per session
3. Checks context at 50% — if hit, commits + writes handoff + stops
4. Edits only files within their assigned ownership boundary
5. Uses MCP tools over CLI over direct API (token efficiency)
6. Never reads files outside what the current task requires
