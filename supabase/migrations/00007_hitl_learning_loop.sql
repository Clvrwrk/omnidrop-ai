-- =============================================================================
-- Migration 00007 — HITL Learning Loop
--
-- Extends context_reference_examples with the correction content needed for
-- few-shot prompting. Without these fields the table only stores labels;
-- with them Claude can learn "here's what was wrong, here's the correction."
--
-- New columns:
--   vendor_name          — enables vendor-scoped example retrieval
--   corrected_extraction — JSONB of human-corrected field values
--   correction_summary   — free-text summary of what changed (for prompt display)
--
-- Existing rows are unaffected (all new columns are nullable).
-- =============================================================================

ALTER TABLE context_reference_examples
  ADD COLUMN IF NOT EXISTS vendor_name         TEXT,
  ADD COLUMN IF NOT EXISTS corrected_extraction JSONB,
  ADD COLUMN IF NOT EXISTS correction_summary   TEXT;

-- Index for vendor-scoped retrieval (used by get_correction_examples helper)
CREATE INDEX IF NOT EXISTS context_ref_vendor_idx
  ON context_reference_examples (organization_id, vendor_name)
  WHERE vendor_name IS NOT NULL;
