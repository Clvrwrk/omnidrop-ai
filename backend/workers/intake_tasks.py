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
    location_id = job_payload.get("location_id")
    organization_id = job_payload.get("organization_id")
    logger.info("process_document started", extra={"job_id": job_id, "location_id": location_id, "organization_id": organization_id})

    # Resolve organization_id from location_id if not provided
    if not organization_id and location_id:
        import asyncio
        from backend.services.supabase_client import get_organization_id_for_location
        organization_id = asyncio.get_event_loop().run_until_complete(
            get_organization_id_for_location(location_id)
        )
        job_payload["organization_id"] = organization_id

    try:
        # TODO: Implementation by AI & QA Engineer
        # 1. Fetch API key: await get_location_api_key(location_id)  (only if location_id present)
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
    import sentry_sdk

    from backend.services.claude_service import ClaudeService

    job_id = parsed_result.get("job_id", "unknown")
    location_id = parsed_result.get("location_id")
    organization_id = parsed_result.get("organization_id", "unknown")
    logger.info("triage_document started", extra={"job_id": job_id})

    try:
        raw_text = parsed_result.get("raw_text", "")
        triage_category = ClaudeService.classify_document(raw_text)

        triaged_result = {
            "job_id": job_id,
            "organization_id": organization_id,
            "location_id": location_id,
            "document_id": parsed_result.get("document_id"),
            "triage_category": triage_category,
            "raw_text": raw_text,
            "file_name": parsed_result.get("file_name"),
            "raw_path": parsed_result.get("raw_path"),
        }

        if triage_category == "structured":
            extract_struct.delay(triaged_result)
        elif triage_category == "unstructured":
            chunk_and_embed.delay(triaged_result)
        else:
            # "unknown" — log to Sentry and mark job as failed
            sentry_sdk.capture_message(
                f"Triage returned 'unknown' for job {job_id}",
                level="warning",
            )
            import asyncio
            asyncio.get_event_loop().run_until_complete(
                _update_job_status(job_id, "failed", error_message="Document classification returned 'unknown'")
            )

        logger.info(
            "triage_document complete",
            extra={"job_id": job_id, "triage_category": triage_category},
        )
        return triaged_result

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
    import asyncio

    from backend.services.claude_service import ClaudeService

    job_id = triaged_result.get("job_id", "unknown")
    location_id = triaged_result.get("location_id")
    organization_id = triaged_result.get("organization_id", "unknown")
    document_id = triaged_result.get("document_id")
    logger.info("extract_struct started", extra={"job_id": job_id})

    try:
        raw_text = triaged_result.get("raw_text", "")

        # 1. Extract invoice fields with confidence scores
        extraction = ClaudeService.extract_invoice_schema(raw_text)

        # 2. Determine triage status via HITL confidence check
        auto_confirm = ClaudeService.should_auto_confirm(extraction)
        triage_status = "confirmed" if auto_confirm else "pending"

        # 3. Write to Supabase
        asyncio.get_event_loop().run_until_complete(
            _save_structured_extraction(
                job_id=job_id,
                organization_id=organization_id,
                location_id=location_id,
                document_id=document_id,
                extraction=extraction,
                triage_status=triage_status,
            )
        )

        logger.info(
            "extract_struct complete",
            extra={"job_id": job_id, "triage_status": triage_status},
        )
        return {"job_id": job_id, "triage_status": triage_status, "extraction": extraction}

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
    import asyncio

    from backend.services.claude_service import ClaudeService

    job_id = triaged_result.get("job_id", "unknown")
    location_id = triaged_result.get("location_id")
    organization_id = triaged_result.get("organization_id", "unknown")
    document_id = triaged_result.get("document_id")
    logger.info("chunk_and_embed started", extra={"job_id": job_id})

    try:
        raw_text = triaged_result.get("raw_text", "")

        # 1. Claude chunks + Voyage AI generates embeddings
        chunks = ClaudeService.chunk_for_rag(raw_text, document_id or job_id)

        # 2. Add organization_id and location_id to each chunk for RLS scoping
        for chunk in chunks:
            chunk["organization_id"] = organization_id
            chunk["location_id"] = location_id

        # 3. Upsert to Supabase document_embeddings table + update job status
        asyncio.get_event_loop().run_until_complete(
            _save_embeddings(job_id=job_id, chunks=chunks)
        )

        logger.info(
            "chunk_and_embed complete",
            extra={"job_id": job_id, "chunk_count": len(chunks)},
        )
        return {"job_id": job_id, "chunk_count": len(chunks)}

    except Exception as exc:
        logger.error("chunk_and_embed failed", extra={"job_id": job_id, "error": str(exc)})
        raise self.retry(exc=exc)


# ── Async helpers for Supabase writes (called from sync Celery tasks) ─────────


async def _update_job_status(
    job_id: str, status: str, error_message: str | None = None
) -> None:
    """Update job status in Supabase."""
    from backend.services.supabase_client import get_supabase_client

    client = await get_supabase_client()
    update_data: dict[str, Any] = {"status": status}
    if status == "complete":
        from datetime import datetime, timezone
        update_data["completed_at"] = datetime.now(timezone.utc).isoformat()
    if error_message:
        update_data["error_message"] = error_message
    await client.table("jobs").update(update_data).eq("job_id", job_id).execute()


async def _save_structured_extraction(
    job_id: str,
    organization_id: str,
    location_id: str | None,
    document_id: str | None,
    extraction: dict[str, Any],
    triage_status: str,
) -> None:
    """Upsert invoice + line_items to Supabase, update job status."""
    from backend.services.supabase_client import get_supabase_client

    client = await get_supabase_client()

    # Update document triage_status if we have a document_id
    if document_id:
        await (
            client.table("documents")
            .update({"triage_status": triage_status, "document_type": "invoice"})
            .eq("document_id", document_id)
            .execute()
        )

    # Extract flat values from confidence-annotated fields
    def _val(field: Any) -> Any:
        if isinstance(field, dict) and "value" in field:
            return field["value"]
        return field

    # Upsert invoice row
    invoice_data = {
        "document_id": document_id,
        "organization_id": organization_id,
        "location_id": location_id,
        "vendor_name": _val(extraction.get("vendor_name")),
        "invoice_number": _val(extraction.get("invoice_number")),
        "invoice_date": _val(extraction.get("invoice_date")),
        "due_date": _val(extraction.get("due_date")),
        "subtotal": _val(extraction.get("subtotal")),
        "tax": _val(extraction.get("tax")),
        "total": _val(extraction.get("total")),
        "notes": _val(extraction.get("notes")),
        "extraction_meta": extraction,  # Full confidence scores for HITL triage
    }
    invoice_resp = await client.table("invoices").insert(invoice_data).execute()
    invoice_id = invoice_resp.data[0]["invoice_id"]

    # Insert line items
    line_items = extraction.get("line_items", [])
    if line_items:
        line_item_rows = []
        for i, item in enumerate(line_items):
            line_item_rows.append({
                "invoice_id": invoice_id,
                "description": _val(item.get("description")),
                "quantity": _val(item.get("quantity")),
                "unit_price": _val(item.get("unit_price")),
                "amount": _val(item.get("amount")),
                "sort_order": i,
            })
        await client.table("line_items").insert(line_item_rows).execute()

    # Mark job complete
    await _update_job_status(job_id, "complete")


async def _save_embeddings(job_id: str, chunks: list[dict[str, Any]]) -> None:
    """Upsert embedding chunks to Supabase document_embeddings, update job status."""
    from backend.services.supabase_client import get_supabase_client

    client = await get_supabase_client()

    if chunks:
        await client.table("document_embeddings").insert(chunks).execute()

    # Mark job complete
    await _update_job_status(job_id, "complete")
