# Product Requirements Document
# Omni-Intake AI Agent — Enterprise Edition

**Version:** 1.1
**Status:** Approved — Phase 2 Implementation
**Last Updated:** 2026-03-28

---

## 1. Objective

Build a zero-cognitive-load, multi-modal document ingestion engine that automates roofing accounting and document retrieval. The system passively and actively ingests structured data (invoices, job costs) and unstructured knowledge (MSDS sheets, warranty manuals, field guides), converting them into actionable insights and a semantically searchable knowledge base — with no manual categorization required from users.

---

## 2. Core User Personas

### The Accountant
Processes hundreds of invoices per week. Primary pain point is manual data entry and vendor SKU reconciliation. Needs:
- Automatic invoice extraction with structured JSON output
- A focused Human-in-the-Loop (HITL) review screen for AI uncertainties and unrecognized SKUs
- Confidence scoring on extracted fields so low-confidence items surface for review

### The C-Suite / Ops Manager
Needs macro-level analytics on job costs, vendor spend, and margins without navigating complex reports. Needs:
- Natural language query interface ("What is total vendor spend for Q1 by job?")
- Visual KPI dashboards with trend charts
- Zero training curve — must work like a search engine

### The DevOps Admin
Manages integration health and API governance. Needs:
- Real-time webhook delivery status and retry visibility
- AccuLynx rate limit monitoring and alerting
- Celery worker queue depth and task failure dashboards

### The Roofing Location Manager *(new)*
Each roofing location has its own AccuLynx instance with its own API key. Needs:
- Self-service UI to register location name and AccuLynx API key
- Ability to manage multiple locations under one account
- Per-location document visibility

---

## 3. Product Features

### 3.1 Omni-Drop Interface
A single drag-and-drop zone that accepts any file type — PDFs, images, spreadsheets, scanned documents — and intelligently routes them through the pipeline without requiring the user to categorize them. The AI determines document type automatically.

**Routes to:** `/dashboard` (upload trigger) → Celery pipeline

### 3.2 Passive AccuLynx Sync
Webhooks automatically pull new job files, milestones, and documents from AccuLynx into the platform without user action. Hookdeck manages the webhook gateway so AccuLynx's 10-second response timeout is never at risk.

**Multi-tenant:** Each roofing location has its own AccuLynx API key. Location managers register their keys via the Settings page. The system fetches the correct key per location at processing time.

**Routes to:** `POST /api/v1/webhooks/acculynx` → Celery queue

### 3.3 CMD+K Analytics & Search (RAG)
A Spotlight-style command bar accessible from any page. Supports two query modes:
- **Semantic search:** "What is the warranty period for Timberline shingles in the GAF manual?" → searches pgvector embeddings
- **Analytical queries:** "What is total SKU spend for Q1 by vendor?" → Text-to-SQL agent queries structured tables

**Routes to:** `/search` (semantic) + `/analytics` (structured queries + Tremor charts)

### 3.4 Human-in-the-Loop (HITL) Triage
A focused split-screen interface for accountants to resolve AI uncertainties:
- Left pane: original document (PDF viewer)
- Right pane: extracted fields with confidence scores, flagged low-confidence items
- Accountants confirm, correct, or reject extractions
- Unrecognized vendor SKUs are surfaced for mapping to the master database

**Routes to:** `/triage` (dedicated review screen)

### 3.5 Location Settings & AccuLynx Key Management *(critical for multi-tenancy)*
Self-service settings page where location managers:
- Add roofing locations by name
- Enter the AccuLynx API key for each location
- View connection status per location
- Remove or rotate keys

**Routes to:** `/settings`

### 3.6 Enterprise Identity (WorkOS)
Frictionless authentication supporting:
- Magic Links (email)
- SAML SSO (enterprise)
- Microsoft / Google OAuth
- SCIM directory sync for user provisioning
- RBAC: Admin, Accountant, Manager, Viewer roles

**Routes to:** WorkOS hosted UI → `/callback` → session cookie

### 3.7 System Health Dashboard
DevOps visibility:
- Webhook delivery status, retry count, last error (Hookdeck feed)
- Celery worker status, queue depth, task failure rate
- AccuLynx API rate limit consumption (429 alerts via Sentry)
- Supabase connection health

**Routes to:** `/dashboard` (admin view)

---

## 4. Non-Functional Requirements

| Requirement | Target |
|---|---|
| Webhook acknowledgement | < 200ms (Hookdeck ACKs AccuLynx) |
| AccuLynx rate compliance | ≤ 10 req/sec per location API key |
| Invoice extraction accuracy | ≥ 95% field-level accuracy (HITL covers remainder) |
| Initial bulk load support | 5,000 documents without data loss |
| Auth session | WorkOS encrypted cookie, 30-day rolling |
| Data isolation | Supabase RLS — users see only their location's data |
| Error visibility | Sentry captures all 4xx/5xx + AI extraction failures |

---

## 5. Out of Scope (Current Phase)

- Mobile app
- Direct QuickBooks / accounting system push (Merge.dev removed from scope)
- Multi-language document support
- Custom AI model fine-tuning
- Stripe billing integration
