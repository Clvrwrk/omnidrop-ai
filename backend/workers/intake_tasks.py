"""
OmniDrop AI — Intake Celery Tasks

These tasks are dispatched by the FastAPI webhook endpoint and executed
asynchronously by the Celery worker process on Render.com.

Pipeline sequence for each AccuLynx webhook event:
  1. process_document   → Unstructured.io parses document into elements
  2. triage_document    → Claude determines document type
  3a. extract_structured  → Claude extracts JSON schema (Invoices/Proposals)
  3b. chunk_and_embed     → Claude chunks + embeddings saved to pgvector (MSDS/Manuals)

Each task in the chain receives the output of the previous task.

RATE LIMIT REMINDER:
  AccuLynx: 30 req/sec per IP, 10 req/sec per API key.
  Use Celery's rate_limit task option when fetching from AccuLynx API.
"""

import logging
from typing import Any

from backend.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="intake.process_document",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    # Respect AccuLynx rate limit: max 10 AccuLynx API calls per second per key
    # rate_limit="10/s",  # Uncomment when AccuLynx fetching is implemented
)
def process_document(self: Any, job_payload: dict[str, Any]) -> dict[str, Any]:
    """
    Task 1: Fetch the document from AccuLynx and parse it with Unstructured.io.

    Args:
        job_payload: The AccuLynx webhook event payload (from FastAPI endpoint).

    Returns:
        Dict with parsed document elements ready for triage.

    TODO:
        1. Fetch document bytes from AccuLynx API using job_payload["job_id"]
        2. Pass bytes to UnstructuredService.partition_document()
        3. Return {"job_id": ..., "elements": [...], "raw_text": ...}
    """
    job_id = job_payload.get("job_id", "unknown")
    logger.info("process_document started", extra={"job_id": job_id})

    try:
        # TODO: Implement
        # from backend.services.unstructured_service import UnstructuredService
        # elements = UnstructuredService.partition_document(document_bytes, filename)
        # return {"job_id": job_id, "elements": elements, "event_type": job_payload["event_type"]}
        raise NotImplementedError("process_document not yet implemented")
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
    Task 2: Triage Agent — Claude determines the document type.

    Document types:
      - "structured"   → Invoice, Sales Proposal (go to extract_structured)
      - "unstructured" → Field Manual, MSDS, Warranty (go to chunk_and_embed)
      - "unknown"      → Log and skip

    Args:
        parsed_result: Output from process_document task.

    Returns:
        Dict with {"doc_type": "structured"|"unstructured"|"unknown", ...parsed_result}

    TODO:
        1. Pass parsed_result["raw_text"] to ClaudeService.classify_document()
        2. Route to appropriate next task based on doc_type
    """
    job_id = parsed_result.get("job_id", "unknown")
    logger.info("triage_document started", extra={"job_id": job_id})

    try:
        # TODO: Implement
        # from backend.services.claude_service import ClaudeService
        # doc_type = ClaudeService.classify_document(parsed_result["raw_text"])
        # result = {**parsed_result, "doc_type": doc_type}
        # if doc_type == "structured":
        #     extract_structured.delay(result)
        # elif doc_type == "unstructured":
        #     chunk_and_embed.delay(result)
        raise NotImplementedError("triage_document not yet implemented")
    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(
    name="intake.extract_structured",
    bind=True,
    max_retries=3,
    default_retry_delay=15,
)
def extract_structured(self: Any, triaged_result: dict[str, Any]) -> dict[str, Any]:
    """
    Task 3a: Claude extracts a strict JSON schema from structured documents.
    Target: Invoices, Sales Proposals.

    Output is saved to Supabase relational tables (jobs, documents, line_items).

    TODO:
        1. Pass triaged_result["raw_text"] to ClaudeService.extract_invoice_schema()
        2. Validate output against Pydantic InvoiceSchema model
        3. Upsert to Supabase relational tables
    """
    job_id = triaged_result.get("job_id", "unknown")
    logger.info("extract_structured started", extra={"job_id": job_id})
    raise NotImplementedError("extract_structured not yet implemented")


@celery_app.task(
    name="intake.chunk_and_embed",
    bind=True,
    max_retries=3,
    default_retry_delay=15,
)
def chunk_and_embed(self: Any, triaged_result: dict[str, Any]) -> dict[str, Any]:
    """
    Task 3b: Chunk unstructured text and save embeddings to Supabase pgvector.
    Target: Field Manuals, MSDS sheets, Warranty documents.

    Output enables semantic search (RAG) over the knowledge base.

    TODO:
        1. Chunk triaged_result["raw_text"] using Unstructured chunking or LangChain
        2. Generate embeddings via Anthropic or OpenAI embeddings API
        3. Upsert to Supabase pgvector table (document_embeddings)
    """
    job_id = triaged_result.get("job_id", "unknown")
    logger.info("chunk_and_embed started", extra={"job_id": job_id})
    raise NotImplementedError("chunk_and_embed not yet implemented")
