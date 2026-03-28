-- =============================================================================
-- OmniDrop AI — Application Tables
-- Phase 2: All 7 tables + pgvector index + RLS enabled
-- =============================================================================

-- ─── locations ────────────────────────────────────────────────────────────────
-- Multi-tenancy root. One row per roofing location per user.
-- AccuLynx issues one API key per location — never a global key.
CREATE TABLE locations (
  location_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id           TEXT NOT NULL,          -- WorkOS user ID
  name              TEXT NOT NULL,
  acculynx_api_key  TEXT NOT NULL,          -- Encrypted at rest (Supabase vault)
  connection_status TEXT NOT NULL DEFAULT 'untested'
                    CHECK (connection_status IN ('active', 'invalid', 'untested')),
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ─── jobs ─────────────────────────────────────────────────────────────────────
-- One job = one document ingestion run (webhook or upload).
CREATE TABLE jobs (
  job_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  location_id   UUID NOT NULL REFERENCES locations(location_id) ON DELETE CASCADE,
  status        TEXT NOT NULL DEFAULT 'queued'
                CHECK (status IN ('queued', 'processing', 'complete', 'failed')),
  file_name     TEXT,
  error_message TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at  TIMESTAMPTZ
);

CREATE INDEX jobs_location_id_idx ON jobs (location_id);
CREATE INDEX jobs_status_idx ON jobs (status);
CREATE INDEX jobs_created_at_idx ON jobs (created_at DESC);

-- ─── intake_events ────────────────────────────────────────────────────────────
-- Raw webhook event log. Append-only.
CREATE TABLE intake_events (
  event_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id      UUID REFERENCES jobs(job_id) ON DELETE SET NULL,
  source      TEXT NOT NULL DEFAULT 'acculynx',
  event_type  TEXT NOT NULL,
  payload     JSONB NOT NULL,
  status      TEXT NOT NULL DEFAULT 'pending'
              CHECK (status IN ('accepted', 'rejected', 'pending')),
  received_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX intake_events_job_id_idx ON intake_events (job_id);
CREATE INDEX intake_events_received_at_idx ON intake_events (received_at DESC);

-- ─── documents ────────────────────────────────────────────────────────────────
-- Parsed document record. Created after Unstructured.io partitioning.
CREATE TABLE documents (
  document_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id        UUID NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
  location_id   UUID NOT NULL REFERENCES locations(location_id) ON DELETE CASCADE,
  document_type TEXT CHECK (document_type IN
                  ('invoice', 'proposal', 'po', 'msds', 'manual', 'warranty', 'unknown')),
  raw_path      TEXT,                       -- Supabase Storage object path
  triage_status TEXT NOT NULL DEFAULT 'pending'
                CHECK (triage_status IN ('pending', 'confirmed', 'rejected')),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX documents_job_id_idx ON documents (job_id);
CREATE INDEX documents_location_id_idx ON documents (location_id);
CREATE INDEX documents_triage_status_idx ON documents (triage_status)
  WHERE triage_status = 'pending';

-- ─── invoices ─────────────────────────────────────────────────────────────────
-- Structured extraction output (Path A). One row per document.
CREATE TABLE invoices (
  invoice_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id      UUID NOT NULL UNIQUE REFERENCES documents(document_id) ON DELETE CASCADE,
  location_id      UUID NOT NULL REFERENCES locations(location_id) ON DELETE CASCADE,
  vendor_name      TEXT,
  invoice_number   TEXT,
  invoice_date     DATE,
  due_date         DATE,
  subtotal         NUMERIC(12, 2),
  tax              NUMERIC(12, 2),
  total            NUMERIC(12, 2),
  notes            TEXT,
  extraction_meta  JSONB,                   -- Per-field confidence scores
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX invoices_location_id_idx ON invoices (location_id);
CREATE INDEX invoices_invoice_date_idx ON invoices (invoice_date DESC);

-- ─── line_items ───────────────────────────────────────────────────────────────
CREATE TABLE line_items (
  line_item_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  invoice_id    UUID NOT NULL REFERENCES invoices(invoice_id) ON DELETE CASCADE,
  description   TEXT,
  quantity      NUMERIC(12, 4),
  unit_price    NUMERIC(12, 2),
  amount        NUMERIC(12, 2),
  sort_order    INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX line_items_invoice_id_idx ON line_items (invoice_id);

-- ─── document_embeddings ──────────────────────────────────────────────────────
-- pgvector store for unstructured path (Path B). One row per semantic chunk.
CREATE TABLE document_embeddings (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id  UUID NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
  location_id  UUID NOT NULL REFERENCES locations(location_id) ON DELETE CASCADE,
  chunk_text   TEXT NOT NULL,
  embedding    VECTOR(1024) NOT NULL,       -- voyage-3 dimension
  metadata     JSONB,                       -- page number, chunk index, etc.
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX document_embeddings_document_id_idx ON document_embeddings (document_id);
CREATE INDEX document_embeddings_location_id_idx ON document_embeddings (location_id);
CREATE INDEX document_embeddings_embedding_idx
  ON document_embeddings
  USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);

-- ─── Row Level Security ──────────────────────────────────────────────────────
-- Enable RLS on all tables. Policies added after WorkOS JWT integration.
ALTER TABLE locations          ENABLE ROW LEVEL SECURITY;
ALTER TABLE jobs               ENABLE ROW LEVEL SECURITY;
ALTER TABLE intake_events      ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents          ENABLE ROW LEVEL SECURITY;
ALTER TABLE invoices           ENABLE ROW LEVEL SECURITY;
ALTER TABLE line_items         ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_embeddings ENABLE ROW LEVEL SECURITY;
