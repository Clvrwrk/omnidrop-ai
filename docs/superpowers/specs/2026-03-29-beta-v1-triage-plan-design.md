# OmniDrop AI — Beta V1.0 Triage & Completion Plan
# Design Specification

**Date:** 2026-03-29
**Status:** Approved — Ready for Implementation Planning
**Author:** Lead Orchestrator (brainstorming session)
**Next step:** `docs/superpowers/specs/` → invoke writing-plans skill

---

## 1. Situation

The OmniDrop AI MVP is partially built. User registration and WorkOS auth work. Render, WorkOS, and Supabase are all stable in production. The backend pipeline (Celery tasks, Claude services, Unstructured.io, notification service) is ~80% implemented with real code. The backend API layer is ~30% implemented — 12 endpoints are stubs. No UI/UX design has been done on any page. The goal of this plan is to reach Beta V1.0.

---

## 2. Codebase Audit Summary

### Production-Ready (keep as-is)
- All 6 Celery tasks: `process_document`, `score_context`, `triage_document`, `extract_struct`, `chunk_and_embed`, `bounce_back`, `detect_revenue_leakage`
- All Claude service methods: classify, extract, chunk_for_rag, score_context, detect_leakage, analytics_agent
- Unstructured.io service (`partition_document`, strategy selection)
- Notification service (SlackAdapter + extensible adapter pattern)
- Hookdeck HMAC verification (`backend/core/security.py`)
- Health check endpoint (`GET /api/v1/health`)
- Webhook endpoint (`POST /api/v1/webhooks/acculynx`) — all 4 steps correct
- Database migrations (00001–00004, including V3 pivot with pricing_contracts, revenue_findings, system_config, vendor_baseline_prices view)
- Celery app config (Redis broker, JSON serializer, 24hr result expiry)
- WorkOS middleware (`middleware.ts`, `/callback` route)
- API client (`lib/api-client.ts` — all 25 typed methods)
- TypeScript types (`lib/types.ts`)
- CI/CD pipeline (`.github/workflows/deploy-dev.yml`)
- `render.yaml`, `docker-compose.yml`

### Needs Completion (stub → real)
**Backend API endpoints (18):**
1. `POST /api/v1/documents/upload` — store bytes to Supabase Storage, create jobs row, dispatch Celery, freemium gate
2. `GET /api/v1/jobs` — query jobs by location/org, paginate
3. `GET /api/v1/jobs/{job_id}` — single job detail
4. `GET /api/v1/events` — list intake_events
5. `GET /api/v1/organizations/me` — lazy-provision org from WorkOS session
6. `GET /api/v1/organizations/me/users` — list org users
7. `GET /api/v1/settings/locations` — list locations (api_key_last4 only)
8. `POST /api/v1/settings/locations` — create location + store API key
9. `PATCH /api/v1/settings/locations/{id}` — update location name or rotate API key
10. `PATCH /api/v1/settings/locations/{id}/notifications` — save Slack webhook URL
11. `POST /api/v1/settings/locations/{id}/notifications/test` — send test Slack message
12. `POST /api/v1/settings/pricing-contracts` — parse uploaded contract file, insert rows
13. `GET /api/v1/triage` — list documents where triage_status='pending'
14. `GET /api/v1/triage/{document_id}` — full extraction with confidence scores + signed Storage URL
15. `PATCH /api/v1/triage/{document_id}` — save HITL corrections, write to context_reference_examples
16. `GET /api/v1/analytics/kpis` — SQL aggregation for volume, accuracy, processing time, invoice value
17. `GET /api/v1/analytics/vendor-spend` — grouped spend by vendor/job/month
18. `GET /api/v1/analytics/leakage` — revenue findings summary for C-Suite dashboard

**Frontend pages (all need UI/UX design + implementation):**
1. `/onboarding` — 5-step wizard (logic exists, no design)
2. `/dashboard` — drag-and-drop upload zone + job status feed
3. `/dashboard/c-suite` — revenue recovery dashboard (leakage findings, Tremor charts)
4. `/settings` — location config + Slack webhook + pricing contract upload
5. `/dashboard/ops` — HITL "Needs Clarity" queue
6. `/dashboard/ops/jobs/[id]` — split-screen PDF viewer + extraction fields
7. `/search` — CMD+K semantic search
8. `/triage` — extraction confirmation (redirect to /dashboard/ops)

### Missing Entirely (must build)
- RLS policies on all 7 Supabase tables
- Supabase Storage bucket + raw file write pattern
- Celery task retry strategy (max_retries, retry_backoff, on_failure)
- `/docs/references/` — 12 third-party service reference docs
- Human SOP for every manual step
- Notification channels (Slack webhook URL) in `/settings` UI + test button
- Pricing contract upload in `/settings`

### Known Schema Issues (fix before spawning agents)
- `document_embeddings.embedding` — currently `VECTOR(1536)`, must be `VECTOR(1024)` (Voyage AI voyage-3)
- Verify `00004_v3_pivot.sql` has: `bounced` job status, `notification_channels` on locations, `context_score`/`context_score_routing`/`clarification_question` on documents
- `api-contracts.md` — add `system_config` table schema, update embedding dimension comment

---

## 3. Beta V1.0 Agent Team

### Team Structure

| Agent | Track | File Ownership |
|---|---|---|
| Lead Orchestrator | Pre-work + coordination | No file edits — coordination only |
| Teammate 1 — Frontend Engineer | Track 3: UI/UX | `/frontend/**` |
| Teammate 2 — Backend Plumber | Track 2: API completion | `/backend/api/**`, `/backend/core/**`, `/shared/**` |
| Teammate 3 — AI & QA Engineer | Track 1: References + RLS + tests | `/backend/services/**`, `/tests/**`, `/docs/references/**` |

### Lead Pre-Work (before spawning any teammate)

| Task | Output |
|---|---|
| Fix `VECTOR(1536)` → `VECTOR(1024)` in `api-contracts.md` | Correct embedding schema |
| Verify all `00004_v3_pivot.sql` columns exist | No runtime surprises |
| Add `system_config` schema to `api-contracts.md` | Complete migration reference |
| Create `/docs/references/` directory with template | Teammates populate their service |
| Create initial task list (all tracks) | Teammates self-assign |

### Execution Sequence

```
Lead Pre-Work: schema fixes + reference template + task list
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
Track 1 (T3):  Track 2 (T2):    Track 3 (T1):
RLS policies     Upload endpoint    Onboarding UI
Supabase Stor    Jobs endpoints     Dashboard UI
Voyage ref doc   Settings CRUD      C-Suite UI
Unstructured     Notifications API  Settings UI
Hookdeck ref     Pricing contracts  Ops queue UI
Supabase ref     Triage endpoints   Split-screen UI
AccuLynx ref     Analytics SQL      Search UI
Other ref docs   Search endpoint
                 Organizations
                 Events endpoint
        │           │           │
        └───────────┼───────────┘
                    ▼
           Lead: Integration test
           Full pipeline: upload → process → score →
           extract → leakage → C-Suite dashboard
                    ▼
               Beta V1.0 ✅
```

---

## 4. Reference Docs Structure

### Directory Layout
```
docs/references/
  README.md              ← Index + how to use these docs
  voyage-ai.md
  unstructured.md
  hookdeck.md
  sentry.md
  workos.md
  render.md
  supabase.md
  cronjob.md
  acculynx.md            ← Integration partner (in scope)
  servicetitan.md        ← Integration partner (future)
  jobnimbus.md           ← Integration partner (future)
  jobtread.md            ← Integration partner (future)
```

### Standard File Format (every reference doc)

```markdown
# [Service] — OmniDrop Reference

## 1. What It Does Here
Why OmniDrop uses it. Which files/tasks touch it.

## 2. Credentials & Environment Variables
| Variable | Where to Find It | Used By |

## 3. CLI
Install, auth, key commands (copy-paste ready), debug commands.

## 4. MCP (Claude Code)
Available MCP tools. Preferred tool per operation. Example calls.

## 5. Direct API
Base URL. Auth header. Key endpoints with curl examples.

## 6. OmniDrop-Specific Patterns
Exact file paths + function names. Rate limits. Known gotchas.

## 7. ⛔ Human SOP
Step-by-step instructions for everything Claude cannot do.
```

### Human SOP Format (inside every reference doc)

```markdown
### SOP-[SERVICE]-[N]: [Task Name]
**When:** [Trigger — what causes this step to be needed]
**Time:** ~[X] minutes
**Prerequisite:** [What must be true first]

Step 1. Go to [exact URL]
Step 2. Click [exact button label] in [exact location]
Step 3. In the field "[exact field name]", enter: [exact value or format]
Step 4. Copy the value labeled "[exact label]" — it looks like: [example]
Step 5. Paste into [exact file path] as [VARIABLE_NAME]
Step 6. Tell Claude: "[exact resume message]"

✅ Done when: [Observable outcome]
⚠️ If you see "[error message]": [exact recovery step]
```

---

## 5. Agent Operating Constraints

### Context Window Protocol (added to CLAUDE.md)

Every agent follows the 50% rule without exception.

**When to check:** After completing each discrete unit of work (one endpoint, one page, one migration, one reference doc).

**At 50% context used — send this to Lead:**
```
🟡 CONTEXT 50% — [Agent Name] handoff

COMPLETED THIS SESSION:
- [file path]: [what was implemented]

COMMITTED: yes/no — branch: [branch name]

NEXT TASK:
- [exact next task]
- [context the next instance needs]

BLOCKERS: [any blockers or "none"]

TO RESUME: Spawn [Agent Name] with: "[exact task prompt]"
```

**Lead response:** Spawns fresh agent instance with next task + pointer to handoff message.

**Rule:** Never stop mid-function or mid-migration. Always stop at a commit boundary.

### Token Efficiency (built into the plan, invisible to agents)

**Tool preference order:**
1. MCP tools (structured, minimal tokens)
2. CLI (one command, one result)
3. Direct API (only when MCP/CLI unavailable)

**Agent-side rules (in CLAUDE.md):**
- Prefer MCP tools over raw API calls when an MCP server is available
- Read only files needed for current task
- Use `mcp__plugin_supabase_supabase__execute_sql` for schema inspection, not Python SDK
- Stub responses use minimum JSON — no padding

**Plan-side efficiency (Lead's job):**
- Each agent session targets one discrete deliverable
- Tasks scoped to complete in under 40% context window
- 50% alert is a hard stop

### Agent Task Scope Rules
- Each task targets ONE deliverable: one endpoint, one page, one doc
- No exploratory browsing — read only the files the task requires
- If a task requires reading more than 5 files to understand context, the task is too large — split it

---

## 6. Definition of Done — Beta V1.0

### Backend
- [ ] All 18 API endpoints return real Supabase data
- [ ] `POST /documents/upload` stores file to Supabase Storage + dispatches Celery
- [ ] All 6 Celery tasks have `max_retries=3`, `retry_backoff=True`, `on_failure` handler
- [ ] RLS policies written and tested on all 7 tables
- [ ] Freemium quota gate active on upload + webhook endpoints

### Frontend
- [ ] All 8 pages have full UI/UX design using `frontend-design` skill
- [ ] All pages use Tremor for charts/metrics, Shadcn/UI for primitives, Tailwind v3
- [ ] No raw `fetch()` outside `lib/api-client.ts`
- [ ] Freemium counter visible in layout (documents_processed / max_documents)

### Integration
- [ ] Full pipeline tested end-to-end: upload → process → score → extract → leakage finding on C-Suite dashboard
- [ ] Bounce-back tested: low-context doc → Slack message delivered
- [ ] HITL tested: medium-context doc → appears in Ops queue → accountant confirms → written to context_reference_examples

### Reference Docs
- [ ] 12 reference docs exist in `/docs/references/`
- [ ] Every doc has CLI, MCP, Direct API sections
- [ ] Every doc has at least one Human SOP entry
- [ ] `docs/references/README.md` indexes all docs

### Deployment
- [ ] App runs end-to-end on `app.omnidrop.dev`
- [ ] `deploy-dev.yml` runs migrations before service restart
- [ ] Sentry capturing errors in both backend and frontend

---

## 7. What Is Out of Scope for Beta V1.0

- Stripe billing (freemium limits enforced, upgrade is manual)
- Self-serve sign-up (sales-assisted for alpha/beta)
- ServiceTitan, JobNimbus, JobTread integrations (reference docs only — no implementation)
- Signal notification adapter
- AccuLynx notification adapter
- Mobile app
- SCIM directory sync
- Custom AI model fine-tuning
- Text-to-SQL analytics agent (Phase 3)
- Vector-based Context Score enhancement (requires 500+ labeled examples)
