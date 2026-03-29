# Project Handoff
**Project:** OmniDrop AI — Beta V1.0
**Date:** 2026-03-29 16:00
**Agent:** Lead Orchestrator
**Reason:** User-requested mid-session handoff (teammates still running)

---

## Accomplished This Session

- `supabase/migrations/00005_rls_and_fixes.sql`: Migration 00005 applied to omnidrop-dev — `clarification_question TEXT` on jobs, `public.current_org_id()` helper function, 22 RLS policies across all 13 tables. Note: `auth` schema is off-limits on Supabase managed instances — function moved to `public` schema.
- `supabase/migrations/00006_nullable_location_id_on_embeddings.sql`: Migration 00006 applied — made `document_embeddings.location_id` nullable so org-level uploads can route through chunk_and_embed.
- `backend/workers/intake_tasks.py`: T1-02 — `retry_backoff=True`, standardised `max_retries=3`, shared `_on_task_failure` handler on all 7 tasks.
- `backend/api/v1/documents.py`: T2-01 — upload endpoint with freemium gate, Storage upload, process_document.delay(), 202 response.
- `backend/api/v1/jobs.py`: T2-02 — GET /jobs + GET /jobs/{job_id} with org-scoping.
- `backend/api/v1/events.py`: T2-03 — GET /events with org-scoping + location filter.
- `backend/api/v1/organizations.py`: T2-04 — GET /organizations/me + /me/users with WorkOS lazy-provision.
- `backend/api/v1/settings.py`: T2-05 through T2-07 — GET+POST locations (key masking via `_mask_key()`), PATCH+DELETE locations, notifications PATCH+test, POST pricing-contracts (CSV+PDF parse).
- `backend/api/v1/triage.py`: T2-08+T2-09 — GET triage list + single doc (signed URL + confidence scores), PATCH confirm/reject/correct with context_reference_example write.
- `docs/references/supabase.md`: T1-03 — full 7-section reference, 3 SOPs.
- `docs/references/voyage-ai.md`: T1-04 — full 7-section reference, 2 SOPs.
- `docs/references/unstructured.md`: T1-05 — full 7-section reference, 2 SOPs.
- `docs/references/hookdeck.md`: T1-06 — full 7-section reference, 3 SOPs. Fixed: env var is `HOOKDECK_SIGNING_SECRET` not `HOOKDECK_WEBHOOK_SECRET`.
- `frontend/app/onboarding/page.tsx`: T3-01 — 5-step wizard, Precision Instrument design.
- `frontend/app/dashboard/page.tsx`: T3-02 — Mission Control design, drag-drop upload zone, 5s-polling job feed with pipeline bar.
- `frontend/app/dashboard/c-suite/page.tsx`: T3-03 — War Room design, countUp hero, Tremor AreaChart + BarList, location/vendor leakage tables.

## Git State
- Branch: `main`
- Last commit: `4ad7528` — "feat(T2-08+T2-09): implement GET /triage endpoints + PATCH HITL corrections"
- Ahead of origin/main by 18 commits (not pushed)
- Uncommitted changes: `docs/handoffs/current.md` (this file), `docs/handoffs/archive/2026-03-29-1428.md`, `supabase/migrations/00005_rls_and_fixes.sql` (untracked — migration was applied via MCP, file was written separately)

## Active Teammates (DO NOT STOP)

Three agents are currently running in the background. A new Lead session must use SendMessage to resume them — do NOT re-spawn.

| Agent name | Current task | Last commit |
|---|---|---|
| `teammate-1-frontend` | T3-04 /settings page | `d5d771d` |
| `teammate-2-backend` | T2-10 GET /analytics/kpis | `4ad7528` |
| `teammate-3-ai-qa` | T1-07 docs/references/sentry.md | `e79648a` |

**To resume an agent:** Use `SendMessage` with `to: "teammate-1-frontend"` (or teammate-2/3) — they resume from their full transcript. Do NOT spawn new agents with the same names.

## Remaining Tasks

### Track 1 — AI & QA (Teammate 3)
- [ ] T1-07: docs/references/sentry.md ← IN PROGRESS
- [ ] T1-08: docs/references/workos.md
- [ ] T1-09: docs/references/render.md
- [ ] T1-10: docs/references/acculynx.md
- [ ] T1-11: docs/references/cronjob.md
- [ ] T1-12: docs/references/servicetitan.md + jobnimbus.md + jobtread.md
- [ ] T1-13: tests/test_pipeline_integration.py
- [ ] T1-14: tests/test_services.py

### Track 2 — Backend (Teammate 2)
- [ ] T2-10: GET /analytics/kpis ← IN PROGRESS
- [ ] T2-11: GET /analytics/vendor-spend + GET /analytics/leakage
- [ ] T2-12: GET /search (pgvector cosine similarity)

### Track 3 — Frontend (Teammate 1)
- [ ] T3-04: /settings ← IN PROGRESS
- [ ] T3-05: /dashboard/ops — HITL Needs Clarity queue
- [ ] T3-06: /dashboard/ops/jobs/[id] — split-screen review UI
- [ ] T3-07: /search — CMD+K semantic search
- [ ] T3-08: Sentry init + freemium counter + final polish

## Next Task — Start Here (if resuming Lead)

**Task:** Monitor and commit teammate output
**Context:** All three teammates are active. The Lead's job is to:
1. Receive task completion notifications
2. Commit the files (teammates cannot run `git commit`)
3. Send the teammate to their next task via `SendMessage`
4. Review reference docs before committing (check for invented credentials)
5. Handle any schema changes via `mcp__plugin_supabase_supabase__apply_migration`

**Prompt to use:** "Read docs/handoffs/current.md. Three teammates are running — use SendMessage to check their status and continue committing their output as it arrives."

## Decisions Made This Session

- **`auth` schema blocked on Supabase managed instances** — all custom functions must go in `public` schema. Use `public.current_org_id()` not `auth.organization_id()`.
- **`document_embeddings.location_id` is now nullable** (migration 00006) — org-level uploads with no location_id can still produce embeddings.
- **Pricing contracts are NOT pipeline documents** — POST /settings/pricing-contracts does a direct SQL insert with no Celery dispatch. No chunk_and_embed for contract files.
- **Teammate 2 rolled T2-08 + T2-09 into one session** — both are committed at `4ad7528`. This is fine.
- **Reference doc review protocol** — Lead must check all reference docs for invented credentials before committing. Only `[ASK USER]` placeholders are acceptable, not fabricated values.
- **All git commits are done by Lead** — teammates cannot run Bash for git. Lead runs the commit command from each teammate's output.

## Blockers Requiring Human Action

None currently.

**Anticipated future blockers:**
- Render `omnidrop-secrets` Environment Group needs populating before first deploy to omnidrop-dev (T2 deployment task — not yet started)
- `.github/workflows/deploy-dev.yml` CI/CD pipeline not yet set up

## Verification Commands

1. `cd "/Users/chussey/Documents/Claude Projects/OmniDropAI" && git log --oneline -5` — should show `4ad7528` as most recent
2. `ls docs/references/` — should show supabase.md, voyage-ai.md, unstructured.md, hookdeck.md (+ README.md, session-handoff-system.md)
3. `ls frontend/app/dashboard/` — should show page.tsx, c-suite/page.tsx

## Full Context

### Completed migrations on omnidrop-dev
- 00001 through 00004: applied in prior sessions
- 00005_rls_and_fixes: applied this session (22 RLS policies + clarification_question)
- 00006_nullable_location_id_on_embeddings: applied this session

### Lead orchestration pattern established this session
Background agents hit permission walls for `git commit` and `apply_migration`. Protocol:
- Teammate sends full file content or full SQL to Lead
- Lead writes file with `Write` tool, applies migration with `apply_migration` MCP tool
- Lead runs `git commit` via Bash
- Lead sends teammate confirmation via `SendMessage` to proceed to next task

### Design system established (frontend)
All three pages use a shared vocabulary:
- Font stack: Syne (headings) + DM Mono (numbers/data) + DM Sans (body)
- Palette: `#0D0F0E` background, `#E8A020` amber accent, crimson for leakage/errors
- Page names: "Precision Instrument" (onboarding), "Mission Control" (dashboard), "War Room" (c-suite)
- Tremor used for charts; Shadcn/UI for primitives; custom `od-*` CSS classes for layout

### Key invariants to enforce in remaining tasks
- `acculynx_api_key` never in any API response — `api_key_last4` only
- `organization_id` always from WorkOS session headers, never from request body
- Freemium gate on all upload paths
- No raw `fetch()` in frontend — all through `lib/api-client.ts`
- Reference docs: `[ASK USER]` for all credential values, never invented
