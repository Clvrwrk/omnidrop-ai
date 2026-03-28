# Product Requirements Document
# OmniDrop AI — Revenue Recovery Platform

**Version:** 2.0
**Status:** Approved — Phase 2 Implementation
**Last Updated:** 2026-03-28

---

## 1. Objective

Build a zero-cognitive-load revenue recovery platform for roofing accounting teams. The primary
goal is not document storage — it is **identifying lost revenue** by cross-referencing supplier
invoices against contracted pricing, surfacing overcharges at the line-item level across all
branches of a multi-location roofing enterprise.

The system passively ingests documents from AccuLynx webhooks and actively accepts direct
uploads. Every document is scored for AI-processability, then routed: high-confidence documents
are extracted and interrogated for leakage automatically; medium-confidence documents go to a
human review queue; low-confidence documents are bounced back to the field with a targeted
clarification question.

---

## 2. Core User Personas

### The Strategist (C-Suite / Owner)
Runs a multi-location roofing company. Primary concern: are my branches paying above our national
supplier contracts, and by how much? Needs:
- Single-screen revenue recovery view aggregated across all branches
- No training curve — must read like a financial dashboard, not a data tool
- "Idaho Branch paid $42/bundle vs. our $35 national contract — $14K overcharge this quarter"

**Primary surface:** `/dashboard/c-suite`

### The Detective (Accounting / Ops Manager)
Processes hundreds of invoices per week. Primary pain point: documents the AI couldn't fully
process are piling up and blocking reconciliation. Needs:
- A focused, low-friction queue of documents that need clarification
- Split-screen review: document on the left, extracted data with flagged fields on the right
- Plain-English questions — not raw JSON fields
- Every correction they make improves future AI accuracy (flywheel)

**Primary surface:** `/dashboard/ops`

### The Location Manager
Each roofing branch has its own AccuLynx instance and its own supplier relationships. Needs:
- Self-service UI to register their branch name and AccuLynx API key
- Notification channel setup (Slack webhook for field alerts)
- Per-location document visibility and processing status

**Primary surface:** `/settings`

### The Field Salesperson
Takes photos and uploads job documents on-site. Not an OmniDrop user — interacts with the
system only when a document they submitted couldn't be processed. Needs:
- A clear, non-technical message explaining what went wrong
- A single specific question to answer, not a support ticket
- Response path that doesn't require logging into another app

**Primary surface:** Slack message with deep link to `/dashboard/ops/jobs/[id]`

### The DevOps Admin
Manages integration health. Needs:
- Webhook delivery status and retry visibility
- Celery worker queue depth and task failure dashboards
- AccuLynx rate limit monitoring (429 alerts via Sentry)

**Primary surface:** `/dashboard/c-suite` system health section (admin role)

---

## 3. Product Features

### 3.1 Omni-Drop Interface
Drag-and-drop zone on the dashboard that accepts any file type. The AI determines document
type, quality, and routing automatically — zero manual categorization required.

**Routes to:** `/dashboard` upload → Celery pipeline

### 3.2 Context Score Engine
Every document receives a 0–100 Context Score immediately after Unstructured.io parsing.
The score is evaluated by Claude against a configurable rubric stored in `system_config`.

| Score | Label | Action |
|---|---|---|
| 80–100 | High | Auto-process → extraction → leakage detection |
| 40–79 | Medium | Auto-process → extraction → Ops review queue |
| 0–39 | Low | Bounce back → Slack alert to field contact |

The rubric covers: vendor identifiability, document legibility, financial data presence,
and metadata completeness. Rubric weights are recalibrated from anonymized cross-customer
data after alpha — no code deploy required.

**Routes to:** Celery `score_context` task (runs after `process_document`)

### 3.3 Revenue Recovery Dashboard
The flagship C-Suite feature. Displays revenue leakage findings aggregated at the
organization level — cross-branch, not siloed by location.

Key views:
- **Total overcharge this period** — currency amount across all branches
- **By branch** — which locations are paying above contract most often
- **By vendor** — which suppliers are charging above contracted rates
- **By SKU** — which line items account for the most leakage

Powered by: `revenue_findings` table + `pricing_contracts` (Contract Mode) or
`vendor_baseline_prices` view (Baseline Mode).

**Routes to:** `/dashboard/c-suite`

### 3.4 Ops "Needs Clarity" Queue
HITL review interface for medium-context documents. Split-screen UI:
- Left pane: original document (PDF viewer or image)
- Right pane: extracted fields with confidence scores, flagged low-confidence items
- Accountants confirm, correct, or reject extractions with plain-English prompts
- Every correction writes to `context_reference_examples` — feeds Phase 2 vector scoring

**Routes to:** `/dashboard/ops` + `/dashboard/ops/jobs/[id]`

### 3.5 Bounce-Back Notifications
Low-context documents (score 0–39) are not routed to the Ops queue — they are immediately
bounced back to the field via Slack. The message includes:
- A one-sentence summary of what the AI detected
- A single targeted clarification question (Claude-generated)
- A deep link to the document in the Ops dashboard

The notification system is channel-agnostic. Alpha ships Slack only. AccuLynx job message
write-back and Signal are future adapters behind the same interface.

Each location manager configures their Slack webhook URL in `/settings`.

**Routes to:** Celery `bounce_back` task → `notification_service.SlackAdapter`

### 3.6 Passive AccuLynx Sync
Webhooks automatically pull new job files from AccuLynx without user action. Hookdeck
manages the gateway; AccuLynx's 10-second timeout is never at risk.

Multi-tenant: each location has its own API key registered in `/settings`.

**Routes to:** `POST /api/v1/webhooks/acculynx` → Celery

### 3.7 CMD+K Semantic Search (RAG)
Spotlight-style search over unstructured knowledge base:
- **Semantic:** "What is the warranty period for Timberline shingles?" → pgvector
- **Analytical:** "Total SKU spend for Q1 by vendor?" → Text-to-SQL agent

**Routes to:** `/search`

### 3.8 Onboarding Wizard
Five-step flow designed to deliver the Aha moment (found revenue) within the first batch.
Critical path: Step 3 (pricing reference) must be completed or skipped to Baseline Mode
before the first batch is processed — without a pricing reference, leakage detection
produces no findings.

| Step | Action | Purpose |
|---|---|---|
| 1 | Company Setup | Name, timezone, invite team (up to 5 for free tier) |
| 2 | Connect Location | AccuLynx API key + Slack webhook URL |
| 3 | Unlock Revenue Detection | Upload pricing contract OR skip to Baseline Mode |
| 4 | Process First Batch | Upload or sync from AccuLynx |
| 5 | Your First Findings | Dashboard highlights first leakage finding |

Step 3 copy: *"Customers who complete this step find an average of $8,400 in overcharges
within their first 50 invoices."*

Alpha delivery is sales-assisted — the wizard does not need to be self-serve for launch.

**Routes to:** `/onboarding`

### 3.9 Location Settings & AccuLynx Key Management
Self-service settings page:
- Add/edit roofing locations
- Enter AccuLynx API key per location
- Enter Slack webhook URL + optional channel name per location
- "Test" button sends a sample Slack message
- View connection status per location

**Routes to:** `/settings`

### 3.10 Enterprise Identity (WorkOS)
- Magic Links (email), SAML SSO, Microsoft/Google OAuth
- SCIM directory sync for user provisioning
- RBAC roles: Admin, Accountant/Ops, C-Suite, Location Manager, Viewer
- Role determines default dashboard landing: C-Suite → `/dashboard/c-suite`, Ops → `/dashboard/ops`

**Routes to:** WorkOS hosted UI → `/callback` → session cookie

---

## 4. Freemium Tier

| Feature | Free | Pro | Enterprise |
|---|---|---|---|
| Documents | 500 | Unlimited | Unlimited |
| Users | 5 | Unlimited | Unlimited |
| Locations | 1 | Unlimited | Unlimited |
| Pricing contracts | 1 | Unlimited | Unlimited |
| Leakage detection | Yes (Baseline Mode) | Yes (Contract + Baseline) | Yes |
| Slack notifications | Yes | Yes | Yes |

Freemium counter shown in the app layout: *"247 / 500 documents used. [Upgrade]"*
Counter turns amber at 80%, red at 95%. At 100%: pipeline pauses, existing data remains
accessible, upgrade CTA shown. API returns 402 for new submissions.

---

## 5. Non-Functional Requirements

| Requirement | Target |
|---|---|
| Webhook acknowledgement | < 200ms (Hookdeck ACKs AccuLynx) |
| AccuLynx rate compliance | ≤ 10 req/sec per location API key |
| Context Score response | Single Claude API call, no second round-trip |
| Invoice extraction accuracy | ≥ 95% field-level (HITL covers remainder) |
| Bounce-back delivery | < 60 seconds from document receipt |
| Initial bulk load | 5,000 documents without data loss |
| Auth session | WorkOS encrypted cookie, 30-day rolling |
| Data isolation | Supabase RLS — users see only their organization's data |
| Error visibility | Sentry captures all 4xx/5xx + AI extraction failures |

---

## 6. Out of Scope (Current Phase)

- Mobile app
- Direct QuickBooks / accounting system push (Merge.dev removed from scope)
- Multi-language document support
- Custom AI model fine-tuning
- Stripe billing integration (freemium limits enforced, upgrade flow is manual for alpha)
- Self-serve sign-up (alpha is sales-assisted)
- Vector-based Context Score enhancement (Phase 2 — requires 500+ labeled examples per org)
- Signal notification adapter (Phase 2 — same interface as Slack, add after alpha)
- AccuLynx notification adapter (Phase 2 — requires @mention behavior testing)
