-- Migration 00006: make document_embeddings.location_id nullable
-- Reason: org-level document uploads have no location_id but may still
-- produce unstructured documents that go through chunk_and_embed.
-- The RLS policy scopes through locations, so NULL location_id rows are
-- only accessible via service role (workers). Frontend search is always
-- location-scoped and will naturally exclude NULL rows via the RLS join.
ALTER TABLE document_embeddings ALTER COLUMN location_id DROP NOT NULL;
