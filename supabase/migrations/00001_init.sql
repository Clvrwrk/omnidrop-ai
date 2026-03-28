-- =============================================================================
-- OmniDrop AI — Initial Database Migration
-- =============================================================================

-- Enable pgvector for document embeddings
CREATE EXTENSION IF NOT EXISTS vector;

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =============================================================================
-- TODO: Define application tables once data model is finalized.
-- Suggested tables (implement in subsequent migrations):
--
-- jobs                — AccuLynx jobs being tracked
--   id, acculynx_job_id, status, created_at, updated_at
--
-- intake_events       — Webhook events received from AccuLynx
--   id, job_id (FK), event_type, raw_payload, received_at, processed_at
--
-- documents           — Extracted documents per job
--   id, job_id (FK), acculynx_document_id, filename, extracted_text, metadata
--
-- document_embeddings — pgvector embeddings for semantic search
--   id, document_id (FK), embedding vector(1536), model_used, created_at
--
-- sync_log            — dlt pipeline run history
--   id, pipeline_name, status, rows_loaded, started_at, completed_at
-- =============================================================================

-- Placeholder: confirm extensions are enabled
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
        RAISE EXCEPTION 'pgvector extension is required but not installed';
    END IF;
END $$;
