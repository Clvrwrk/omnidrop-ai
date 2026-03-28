"""
OmniDrop AI — Intake Celery Tasks

Dispatched by the FastAPI webhook endpoint, executed by the Celery worker.

Pipeline sequence:
  1. process_document   -> fetch from AccuLynx + Unstructured.io parse
  2. triage_document    -> Claude classifies document type
  3a. extract_struct    -> Claude extracts JSON schema (invoices/proposals)
  3b. chunk_and_embed   -> Claude chunks + pgvector embeddings (manuals/MSDS)

RATE LIMIT RULES:
  - AccuLynx API: 30 req/sec per IP, 10 req/sec per API key
  - rate_limit="10/s" on ALL tasks that call AccuLynx API
  - Tasks calling Claude/Unstructured do NOT need AccuLynx rate limits
"""

import logging
from typing import Any

from backend.workers.celery_app import celery_app
from shared.constants import ACCULYNX_RATE_LIMIT

logger = logging.getLogger(__name__)


@celery_app.task(
    name="intake.process_document",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    rate_limit=ACCULYNX_RATE_LIMIT,
)
def process_document(self: Any, job_payload: dict[str, Any]) -> dict[str, Any]:
    """
    Task 1: Fetch the document from AccuLynx and parse with Unstructured.io.

    Uses location_id to fetch the per-location AccuLynx API key from Supabase.
    There is NO global ACCULYNX_API_KEY — each location has its own.

    Args:
        job_payload: CeleryJobPayload-shaped dict from the webhook endpoint.

    Returns:
        ProcessedDocumentResult-shaped dict for triage_document.
    """
    job_id = job_payload.get("job_id", "unknown")
    location_id = job_payload.get("location_id", "unknown")
    logger.info("process_document started", extra={"job_id": job_id, "location_id": location_id})

    try:
        # TODO: Implementation by AI & QA Engineer
        # 1. Fetch API key: await get_location_api_key(location_id)
        # 2. Fetch document bytes from AccuLynx API using that key
        # 3. Pass bytes to UnstructuredService.partition_document()
        # 4. Return ProcessedDocumentResult dict
        raise NotImplementedError("process_document not yet implemented")
    except NotImplementedError:
        raise
    except Exception as exc:
        logger.error("process_document failed", extra={"job_id": job_id, "error": str(exc)})
        raise self.retry(exc=exc)


@celery_app.task(
    name="intake.triage_document",
    bind=True,
    max_retries=3,
    default_retry_delay=15,
)
def triage_document(self: Any, parsed_result: dict[str, Any]) -> dict[str, Any]:
    """
    Task 2: Claude classifies the document type.

    Routes to:
      - extract_struct (structured: invoice, proposal, PO)
      - chunk_and_embed (unstructured: MSDS, manual, warranty)

    Args:
        parsed_result: ProcessedDocumentResult-shaped dict from process_document.

    Returns:
        TriagedDocumentResult-shaped dict.
    """
    job_id = parsed_result.get("job_id", "unknown")
    logger.info("triage_document started", extra={"job_id": job_id})

    try:
        # TODO: Implementation by AI & QA Engineer
        # 1. ClaudeService.classify_document(parsed_result["raw_text"])
        # 2. Route: extract_struct.delay(result) or chunk_and_embed.delay(result)
        raise NotImplementedError("triage_document not yet implemented")
    except NotImplementedError:
        raise
    except Exception as exc:
        logger.error("triage_document failed", extra={"job_id": job_id, "error": str(exc)})
        raise self.retry(exc=exc)


@celery_app.task(
    name="intake.extract_struct",
    bind=True,
    max_retries=3,
    default_retry_delay=15,
)
def extract_struct(self: Any, triaged_result: dict[str, Any]) -> dict[str, Any]:
    """
    Task 3a: Claude extracts structured JSON from invoices/proposals.

    Output saved to Supabase: jobs, documents, invoices, line_items tables.

    Args:
        triaged_result: TriagedDocumentResult-shaped dict from triage_document.
    """
    job_id = triaged_result.get("job_id", "unknown")
    logger.info("extract_struct started", extra={"job_id": job_id})

    try:
        # TODO: Implementation by AI & QA Engineer
        # 1. ClaudeService.extract_invoice_schema(triaged_result["raw_text"])
        # 2. Validate with InvoiceExtraction Pydantic model
        # 3. Upsert to Supabase relational tables
        raise NotImplementedError("extract_struct not yet implemented")
    except NotImplementedError:
        raise
    except Exception as exc:
        logger.error("extract_struct failed", extra={"job_id": job_id, "error": str(exc)})
        raise self.retry(exc=exc)


@celery_app.task(
    name="intake.chunk_and_embed",
    bind=True,
    max_retries=3,
    default_retry_delay=15,
)
def chunk_and_embed(self: Any, triaged_result: dict[str, Any]) -> dict[str, Any]:
    """
    Task 3b: Chunk unstructured text and save embeddings to pgvector.

    Enables RAG semantic search over manuals, MSDS sheets, warranties.

    Args:
        triaged_result: TriagedDocumentResult-shaped dict from triage_document.
    """
    job_id = triaged_result.get("job_id", "unknown")
    logger.info("chunk_and_embed started", extra={"job_id": job_id})

    try:
        # TODO: Implementation by AI & QA Engineer
        # 1. ClaudeService.chunk_for_rag(triaged_result["raw_text"])
        # 2. Generate embeddings
        # 3. Upsert to Supabase document_embeddings table
        raise NotImplementedError("chunk_and_embed not yet implemented")
    except NotImplementedError:
        raise
    except Exception as exc:
        logger.error("chunk_and_embed failed", extra={"job_id": job_id, "error": str(exc)})
        raise self.retry(exc=exc)
