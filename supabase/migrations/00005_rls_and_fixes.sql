-- ============================================================
-- Migration 00005: clarification_question column + RLS policies
-- OmniDrop AI — Beta V1.0
-- Applied: 2026-03-29
-- Author: AI & QA Engineer (T1-01)
-- ============================================================

-- ─── Part 1: ADD COLUMN clarification_question to jobs ────────────────────────
-- This column was referenced in api-contracts.md but not yet added to jobs.
-- Claude's clarifying question for bounce-back notifications is stored here.

ALTER TABLE jobs
  ADD COLUMN IF NOT EXISTS clarification_question TEXT;

-- ─── Part 2: Helper function — resolve organization_id from JWT ───────────────
-- WorkOS AuthKit sets 'org_id' claim in the JWT (the WorkOS org ID string).
-- This function resolves it to our internal organizations.organization_id UUID.
-- SECURITY DEFINER so the function can read organizations even while RLS is active.
-- Placed in public schema (auth schema is restricted on Supabase managed instances).

CREATE OR REPLACE FUNCTION public.current_org_id()
RETURNS UUID
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT organization_id
  FROM public.organizations
  WHERE workos_org_id = (auth.jwt() ->> 'org_id')
  LIMIT 1;
$$;

-- ─── Part 3: RLS Policies ────────────────────────────────────────────────────
-- Strategy:
--   • All authenticated users in the same WorkOS org share the same data scope.
--   • JWT claim 'org_id' (WorkOS org ID string) → organizations.workos_org_id
--     → organizations.organization_id (UUID — the FK used throughout the schema).
--   • Service role key (used by all Celery workers) bypasses RLS entirely.
--     No worker-specific policies are needed.
--   • anon role is blocked by default (no GRANT issued here).
--   • 'sub' claim = WorkOS user_id, used to enforce user_id on locations INSERT.

-- ─── organizations ─────────────────────────────────────────────────────────

-- Users can only read their own org record
CREATE POLICY "organizations: read own org"
  ON organizations
  FOR SELECT
  TO authenticated
  USING (workos_org_id = (auth.jwt() ->> 'org_id'));

-- ─── locations ─────────────────────────────────────────────────────────────

-- SELECT: any user in the org can see all locations in their org
CREATE POLICY "locations: read own org"
  ON locations
  FOR SELECT
  TO authenticated
  USING (organization_id = public.current_org_id());

-- INSERT: user can register a location under their org; user_id must match JWT sub
CREATE POLICY "locations: insert own org"
  ON locations
  FOR INSERT
  TO authenticated
  WITH CHECK (
    organization_id = public.current_org_id()
    AND user_id = (auth.jwt() ->> 'sub')
  );

-- UPDATE: user can edit locations in their org
CREATE POLICY "locations: update own org"
  ON locations
  FOR UPDATE
  TO authenticated
  USING (organization_id = public.current_org_id())
  WITH CHECK (organization_id = public.current_org_id());

-- DELETE: user can remove locations in their org
CREATE POLICY "locations: delete own org"
  ON locations
  FOR DELETE
  TO authenticated
  USING (organization_id = public.current_org_id());

-- ─── jobs ────────────────────────────────────────────────────────────────────
-- READ only — workers write via service role, frontend polls via authenticated role

CREATE POLICY "jobs: read own org"
  ON jobs
  FOR SELECT
  TO authenticated
  USING (organization_id = public.current_org_id());

-- ─── intake_events ───────────────────────────────────────────────────────────
-- No direct organization_id — scope through jobs

CREATE POLICY "intake_events: read own org"
  ON intake_events
  FOR SELECT
  TO authenticated
  USING (
    job_id IN (
      SELECT job_id FROM jobs
      WHERE organization_id = public.current_org_id()
    )
  );

-- ─── documents ───────────────────────────────────────────────────────────────

-- READ
CREATE POLICY "documents: read own org"
  ON documents
  FOR SELECT
  TO authenticated
  USING (organization_id = public.current_org_id());

-- UPDATE: HITL accountants update triage_status on documents in their org
CREATE POLICY "documents: update triage own org"
  ON documents
  FOR UPDATE
  TO authenticated
  USING (organization_id = public.current_org_id())
  WITH CHECK (organization_id = public.current_org_id());

-- ─── invoices ────────────────────────────────────────────────────────────────
-- No direct organization_id FK — scope through documents

CREATE POLICY "invoices: read own org"
  ON invoices
  FOR SELECT
  TO authenticated
  USING (
    document_id IN (
      SELECT document_id FROM documents
      WHERE organization_id = public.current_org_id()
    )
  );

-- ─── line_items ───────────────────────────────────────────────────────────────
-- No direct organization_id — scope through invoices → documents

CREATE POLICY "line_items: read own org"
  ON line_items
  FOR SELECT
  TO authenticated
  USING (
    invoice_id IN (
      SELECT invoice_id FROM invoices
      WHERE document_id IN (
        SELECT document_id FROM documents
        WHERE organization_id = public.current_org_id()
      )
    )
  );

-- ─── document_embeddings ─────────────────────────────────────────────────────
-- Has location_id — scope through locations → organization_id

CREATE POLICY "document_embeddings: read own org"
  ON document_embeddings
  FOR SELECT
  TO authenticated
  USING (
    location_id IN (
      SELECT location_id FROM locations
      WHERE organization_id = public.current_org_id()
    )
  );

-- ─── pricing_contracts ───────────────────────────────────────────────────────
-- Direct organization_id FK — full CRUD for authenticated users in their org

CREATE POLICY "pricing_contracts: read own org"
  ON pricing_contracts
  FOR SELECT
  TO authenticated
  USING (organization_id = public.current_org_id());

CREATE POLICY "pricing_contracts: insert own org"
  ON pricing_contracts
  FOR INSERT
  TO authenticated
  WITH CHECK (organization_id = public.current_org_id());

CREATE POLICY "pricing_contracts: delete own org"
  ON pricing_contracts
  FOR DELETE
  TO authenticated
  USING (organization_id = public.current_org_id());

-- ─── revenue_findings ────────────────────────────────────────────────────────
-- READ only — written exclusively by detect_revenue_leakage Celery task (service role)

CREATE POLICY "revenue_findings: read own org"
  ON revenue_findings
  FOR SELECT
  TO authenticated
  USING (organization_id = public.current_org_id());

-- ─── bounce_back_log ─────────────────────────────────────────────────────────
-- READ only — written by bounce_back Celery task (service role)

CREATE POLICY "bounce_back_log: read own org"
  ON bounce_back_log
  FOR SELECT
  TO authenticated
  USING (organization_id = public.current_org_id());

-- ─── context_reference_examples ──────────────────────────────────────────────
-- Written by HITL triage corrections (authenticated users or service role)

CREATE POLICY "context_reference_examples: read own org"
  ON context_reference_examples
  FOR SELECT
  TO authenticated
  USING (organization_id = public.current_org_id());

CREATE POLICY "context_reference_examples: insert own org"
  ON context_reference_examples
  FOR INSERT
  TO authenticated
  WITH CHECK (organization_id = public.current_org_id());

-- ─── system_config ───────────────────────────────────────────────────────────
-- Global AI config — intentionally NOT org-scoped.
-- Read-only for all authenticated users. Writes are service-role only
-- (rubric recalibration: UPDATE system_config SET value = '...' WHERE key = '...').

ALTER TABLE system_config ENABLE ROW LEVEL SECURITY;

CREATE POLICY "system_config: read for all authenticated"
  ON system_config
  FOR SELECT
  TO authenticated
  USING (true);

-- ─── End of migration 00005 ──────────────────────────────────────────────────
