-- =============================================================================
-- OmniDrop AI — V3 Pivot: Revenue Recovery Architecture
-- Additive migration — extends existing tables, adds new ones.
-- Does NOT recreate locations, jobs, documents, invoices, organizations.
-- =============================================================================

-- ─── organizations: freemium tier columns ────────────────────────────────────
ALTER TABLE organizations
  ADD COLUMN IF NOT EXISTS plan_tier           TEXT NOT NULL DEFAULT 'free'
    CHECK (plan_tier IN ('free', 'pro', 'enterprise')),
  ADD COLUMN IF NOT EXISTS max_documents       INTEGER NOT NULL DEFAULT 500,
  ADD COLUMN IF NOT EXISTS documents_processed INTEGER NOT NULL DEFAULT 0;

-- ─── locations: notification channels ────────────────────────────────────────
-- Stores per-location delivery config. Alpha: {"slack": {"webhook_url": "..."}}
ALTER TABLE locations
  ADD COLUMN IF NOT EXISTS notification_channels JSONB NOT NULL DEFAULT '{}';

-- ─── jobs: context scoring + bounce-back state ───────────────────────────────
ALTER TABLE jobs
  ADD COLUMN IF NOT EXISTS context_score    INTEGER,          -- 0–100 from score_context task
  ADD COLUMN IF NOT EXISTS context_routing  TEXT              -- 'high' | 'medium' | 'low'
    CHECK (context_routing IN ('high', 'medium', 'low')),
  ADD COLUMN IF NOT EXISTS leakage_skipped_reason TEXT;       -- 'no_pricing_reference' | null

-- Extend jobs.status to include 'bounced' (low-context path)
-- Drop existing unnamed CHECK and replace with a named one.
ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_status_check;
ALTER TABLE jobs
  ADD CONSTRAINT jobs_status_check
    CHECK (status IN ('queued', 'processing', 'complete', 'failed', 'bounced'));

-- ─── documents: needs_clarity triage status ──────────────────────────────────
-- Medium-context documents are flagged for Ops review queue.
ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_triage_status_check;
ALTER TABLE documents
  ADD CONSTRAINT documents_triage_status_check
    CHECK (triage_status IN ('pending', 'confirmed', 'rejected', 'needs_clarity'));

-- ─── pricing_contracts ───────────────────────────────────────────────────────
-- National supplier pricing. Scoped to organization (NOT location) so C-Suite
-- can compare any branch invoice against the national contract.
CREATE TABLE IF NOT EXISTS pricing_contracts (
  contract_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id       UUID NOT NULL REFERENCES organizations(organization_id) ON DELETE CASCADE,
  vendor_name           TEXT NOT NULL,
  sku                   TEXT,
  description           TEXT,
  contracted_unit_price NUMERIC(12, 2) NOT NULL,
  effective_date        DATE,
  expiry_date           DATE,
  source_document_id    UUID REFERENCES documents(document_id) ON DELETE SET NULL,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS pricing_contracts_org_idx     ON pricing_contracts (organization_id);
CREATE INDEX IF NOT EXISTS pricing_contracts_vendor_idx  ON pricing_contracts (organization_id, vendor_name);

ALTER TABLE pricing_contracts ENABLE ROW LEVEL SECURITY;

-- ─── revenue_findings ────────────────────────────────────────────────────────
-- Leakage findings written by detect_revenue_leakage task.
-- leakage_amount = (invoiced_unit_price - reference_unit_price) × quantity
CREATE TABLE IF NOT EXISTS revenue_findings (
  finding_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id       UUID NOT NULL REFERENCES organizations(organization_id) ON DELETE CASCADE,
  location_id           UUID REFERENCES locations(location_id) ON DELETE SET NULL,
  invoice_id            UUID NOT NULL REFERENCES invoices(invoice_id) ON DELETE CASCADE,
  line_item_id          UUID NOT NULL REFERENCES line_items(line_item_id) ON DELETE CASCADE,
  contract_id           UUID REFERENCES pricing_contracts(contract_id) ON DELETE SET NULL,
  reference_mode        TEXT NOT NULL CHECK (reference_mode IN ('contract', 'baseline')),
  vendor_name           TEXT,
  sku                   TEXT,
  invoiced_unit_price   NUMERIC(12, 2) NOT NULL,
  reference_unit_price  NUMERIC(12, 2) NOT NULL,
  quantity              NUMERIC(12, 4) NOT NULL,
  leakage_amount        NUMERIC(12, 2) NOT NULL,  -- (invoiced - reference) × quantity
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS revenue_findings_org_idx      ON revenue_findings (organization_id);
CREATE INDEX IF NOT EXISTS revenue_findings_location_idx ON revenue_findings (location_id);
CREATE INDEX IF NOT EXISTS revenue_findings_invoice_idx  ON revenue_findings (invoice_id);
CREATE INDEX IF NOT EXISTS revenue_findings_created_idx  ON revenue_findings (created_at DESC);

ALTER TABLE revenue_findings ENABLE ROW LEVEL SECURITY;

-- ─── bounce_back_log ─────────────────────────────────────────────────────────
-- Audit trail for all low-context document notifications.
CREATE TABLE IF NOT EXISTS bounce_back_log (
  log_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id          UUID NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
  location_id     UUID REFERENCES locations(location_id) ON DELETE SET NULL,
  organization_id UUID REFERENCES organizations(organization_id) ON DELETE SET NULL,
  context_score   INTEGER NOT NULL,
  channel_used    TEXT NOT NULL CHECK (channel_used IN ('slack', 'acculynx', 'signal', 'none')),
  message_sent    TEXT NOT NULL,
  delivery_status TEXT NOT NULL CHECK (delivery_status IN ('sent', 'failed', 'no_channel')),
  sent_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS bounce_back_log_job_idx ON bounce_back_log (job_id);
CREATE INDEX IF NOT EXISTS bounce_back_log_org_idx ON bounce_back_log (organization_id);

ALTER TABLE bounce_back_log ENABLE ROW LEVEL SECURITY;

-- ─── system_config ───────────────────────────────────────────────────────────
-- AI configuration — context score rubric weights live here, not in code.
-- Recalibrate by UPDATE, no deploy required.
CREATE TABLE IF NOT EXISTS system_config (
  key        TEXT PRIMARY KEY,
  value      JSONB NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Seed: initial context score rubric (Phase 1 weights)
INSERT INTO system_config (key, value)
VALUES (
  'context_score_rubric',
  '{
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
  }'
)
ON CONFLICT (key) DO NOTHING;

-- ─── context_reference_examples ──────────────────────────────────────────────
-- Phase 2: per-org labeled examples for vector-enhanced scoring.
-- Populated automatically by HITL corrections in /dashboard/ops — not seeded manually.
CREATE TABLE IF NOT EXISTS context_reference_examples (
  example_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES organizations(organization_id) ON DELETE CASCADE,
  document_id     UUID REFERENCES documents(document_id) ON DELETE SET NULL,
  label           TEXT NOT NULL CHECK (label IN ('high', 'medium', 'low')),
  label_source    TEXT NOT NULL CHECK (label_source IN ('hitl_correction', 'manual_seed')),
  rubric_score    INTEGER NOT NULL,
  embedding       VECTOR(1024),                -- populated in Phase 2, null until then
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS context_ref_org_idx   ON context_reference_examples (organization_id);
CREATE INDEX IF NOT EXISTS context_ref_label_idx ON context_reference_examples (organization_id, label);

ALTER TABLE context_reference_examples ENABLE ROW LEVEL SECURITY;

-- ─── vendor_baseline_prices view ─────────────────────────────────────────────
-- Baseline Mode pricing reference: 90-day rolling average per org/vendor/SKU.
-- Requires >= 3 invoice samples to be considered reliable.
-- Used by detect_revenue_leakage when no pricing_contracts rows exist for the org.
CREATE OR REPLACE VIEW vendor_baseline_prices AS
SELECT
  i.organization_id,
  i.vendor_name,
  li.description,
  AVG(li.unit_price)    AS baseline_unit_price,
  STDDEV(li.unit_price) AS price_stddev,
  COUNT(*)              AS sample_count
FROM line_items li
JOIN invoices i USING (invoice_id)
WHERE
  i.created_at > NOW() - INTERVAL '90 days'
  AND li.unit_price IS NOT NULL
  AND li.unit_price > 0
GROUP BY i.organization_id, i.vendor_name, li.description
HAVING COUNT(*) >= 3;
