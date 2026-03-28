"""
OmniDrop AI — Document Processing Activities

Temporal activities for AI document extraction and database sync.
Each activity is a single, retriable unit of work.

RATE LIMIT REMINDER:
  - AccuLynx: 30 req/sec per IP, 10 req/sec per API key
  - Use Temporal's retry policy + backoff for rate limit (429) responses
  - Never make parallel AccuLynx requests that would exceed these limits
"""

import logging

from temporalio import activity

from shared.models.jobs import IntakeJobInput, IntakeJobResult

logger = logging.getLogger(__name__)


@activity.defn
async def extract_documents(job_input: IntakeJobInput) -> IntakeJobResult:
    """
    Fetch documents from AccuLynx and run AI extraction.

    TODO:
      1. Fetch document list from AccuLynx API for job_input.job_id
      2. Download each document (respecting rate limits)
      3. Send to Anthropic API for extraction
      4. Return structured extraction results

    Rate limit handling: Temporal's RetryPolicy with backoff handles 429s.
    """
    logger.info("extract_documents called", extra={"job_id": job_input.job_id})
    raise NotImplementedError("extract_documents not yet implemented")


@activity.defn
async def sync_to_database(result: IntakeJobResult) -> None:
    """
    Write extraction results to Supabase.

    TODO:
      1. Upsert job record with status and metadata
      2. Insert extracted document records
      3. Generate and store pgvector embeddings
    """
    logger.info("sync_to_database called", extra={"job_id": result.job_id})
    raise NotImplementedError("sync_to_database not yet implemented")
