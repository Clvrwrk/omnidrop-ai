-- =============================================================================
-- OmniDrop AI — Organization Multi-Tenancy
-- Phase 3: organizations table + org_id columns on all tenant-scoped tables
-- =============================================================================

-- ─── organizations ───────────────────────────────────────────────────────────
-- New tenant root. Locations are optional children of organizations.
-- Document upload can work with just an organization_id (no location required).
CREATE TABLE organizations (
  organization_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workos_org_id    TEXT UNIQUE NOT NULL,
  name             TEXT NOT NULL,
  max_users        INTEGER NOT NULL DEFAULT 5,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE organizations ENABLE ROW LEVEL SECURITY;

-- ─── locations: add organization_id ──────────────────────────────────────────
-- Locations become optional children of organizations.
-- NOT NULL enforced after backfill in a future migration.
ALTER TABLE locations
  ADD COLUMN organization_id UUID REFERENCES organizations(organization_id) ON DELETE CASCADE;

CREATE INDEX locations_organization_id_idx ON locations (organization_id);

-- ─── jobs: add organization_id, make location_id nullable ────────────────────
ALTER TABLE jobs
  ADD COLUMN organization_id UUID REFERENCES organizations(organization_id) ON DELETE CASCADE;

ALTER TABLE jobs
  ALTER COLUMN location_id DROP NOT NULL;

CREATE INDEX jobs_organization_id_idx ON jobs (organization_id);

-- ─── documents: add organization_id, make location_id nullable ───────────────
ALTER TABLE documents
  ADD COLUMN organization_id UUID REFERENCES organizations(organization_id) ON DELETE CASCADE;

ALTER TABLE documents
  ALTER COLUMN location_id DROP NOT NULL;

CREATE INDEX documents_organization_id_idx ON documents (organization_id);

-- ─── invoices: add organization_id, make location_id nullable ────────────────
ALTER TABLE invoices
  ADD COLUMN organization_id UUID REFERENCES organizations(organization_id) ON DELETE CASCADE;

ALTER TABLE invoices
  ALTER COLUMN location_id DROP NOT NULL;

CREATE INDEX invoices_organization_id_idx ON invoices (organization_id);

-- ─── document_embeddings: add organization_id, make location_id nullable ─────
ALTER TABLE document_embeddings
  ADD COLUMN organization_id UUID REFERENCES organizations(organization_id) ON DELETE CASCADE;

ALTER TABLE document_embeddings
  ALTER COLUMN location_id DROP NOT NULL;

CREATE INDEX document_embeddings_organization_id_idx ON document_embeddings (organization_id);

-- ─── intake_events: add organization_id ──────────────────────────────────────
ALTER TABLE intake_events
  ADD COLUMN organization_id UUID REFERENCES organizations(organization_id) ON DELETE CASCADE;

CREATE INDEX intake_events_organization_id_idx ON intake_events (organization_id);
