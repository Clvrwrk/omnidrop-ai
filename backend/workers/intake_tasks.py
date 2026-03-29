"""
OmniDrop AI — Intake Celery Tasks

Dispatched by the FastAPI webhook endpoint, executed by the Celery worker.

Pipeline sequence:
  1. process_document        -> fetch from AccuLynx + Unstructured.io parse
  2. score_context           -> Claude scores 0-100, routes low/medium/high
     - low (0-39)            -> bounce_back (notify field, stop)
     - medium/high (40-100)  -> triage_document
  3. triage_document         -> Claude classifies document type
  4a. extract_struct         -> Claude extracts JSON schema (invoices/proposals)
      - high context only    -> detect_revenue_leakage
  4b. chunk_and_embed        -> Claude chunks + pgvector embeddings (manuals/MSDS)
  5. detect_revenue_leakage  -> Compare line items against pricing reference

RATE LIMIT RULES:
  - AccuLynx API: 30 req/sec per IP, 10 req/sec per API key
  - rate_limit="10/s" on ALL tasks that call AccuLynx API
  - Tasks calling Claude/Unstructured do NOT need AccuLynx rate limits
"""

import logging
from typing import Any

import sentry_sdk

from backend.workers.celery_app import celery_app
from shared.constants import ACCULYNX_RATE_LIMIT

logger = logging.getLogger(__name__)


# ── Shared on_failure handler ─────────────────────────────────────────────────


def _on_task_failure(self: Any, exc: Exception, task_id: str, args: tuple, kwargs: dict, einfo: Any) -> None:
    """
    Fires after all retries are exhausted on any intake task.

    - Logs the failure with full context to Sentry.
    - Updates the job status to 'failed' in Supabase so the UI reflects the error.
    - job_id is always the first positional arg OR present in the first dict arg.
    """
    # Resolve job_id from args — all tasks receive a dict payload as their first arg
    job_id: str = "unknown"
    if args:
        first_arg = args[0]
        if isinstance(first_arg, dict):
            job_id = first_arg.get("job_id", "unknown")

    logger.error(
        "Celery task exhausted all retries",
        extra={"task": self.name, "task_id": task_id, "job_id": job_id, "error": str(exc)},
    )

    sentry_sdk.capture_exception(
        exc,
        extras={"task": self.name, "task_id": task_id, "job_id": job_id},
    )

    if job_id != "unknown":
        import asyncio
        asyncio.get_event_loop().run_until_complete(
            _update_job_status(job_id, "failed", error_message=f"{self.name} failed after retries: {exc}")
        )


@celery_app.task(
    name="intake.process_document",
    bind=True,
    max_retries=3,
    retry_backoff=True,
    default_retry_delay=30,
    rate_limit=ACCULYNX_RATE_LIMIT,
    on_failure=_on_task_failure,
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

    import asyncio
    import base64

    import httpx

    from backend.services.supabase_client import get_location_api_key
    from backend.services.unstructured_service import UnstructuredService

    # ── Step 1: Resolve document source fields ─────────────────────────────────
    document_url = job_payload.get("document_url") or job_payload.get("event", {}).get("document_url")
    document_id = job_payload.get("document_id") or job_payload.get("event", {}).get("document_id")
    # acculynx_job_id is the AccuLynx job ID (same as job_id from the webhook event)
    acculynx_job_id = job_payload.get("job_id")

    # Derive file_name from document_url if not explicitly provided
    file_name = job_payload.get("file_name")
    if not file_name and document_url:
        file_name = document_url.rstrip("/").split("/")[-1].split("?")[0] or "document"

    # ── Step 2: Fetch location API key (skip for direct uploads) ───────────────
    api_key: str | None = None
    if location_id:
        try:
            api_key = asyncio.get_event_loop().run_until_complete(
                get_location_api_key(location_id)
            )
        except ValueError as exc:
            logger.warning(
                "process_document: no API key for location, proceeding without auth",
                extra={"job_id": job_id, "location_id": location_id, "error": str(exc)},
            )

    # ── Step 3: Fetch document bytes ───────────────────────────────────────────
    file_bytes: bytes
    if document_url:
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        try:
            with httpx.Client(timeout=60) as http_client:
                response = http_client.get(document_url, headers=headers, follow_redirects=True)
                response.raise_for_status()
                file_bytes = response.content
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            if status_code == 429:
                logger.warning("process_document: 429 from AccuLynx, backing off", extra={"job_id": job_id})
                raise self.retry(countdown=60, exc=exc)
            elif status_code in (401, 403):
                logger.error(
                    "process_document: auth error fetching document — not retrying",
                    extra={"job_id": job_id, "status_code": status_code},
                )
                asyncio.get_event_loop().run_until_complete(
                    _update_job_status(job_id, "failed", error_message=f"HTTP {status_code} fetching document")
                )
                return {"job_id": job_id, "error": f"HTTP {status_code}"}
            else:
                logger.error("process_document: HTTP error fetching document", extra={"job_id": job_id, "error": str(exc)})
                raise self.retry(exc=exc)
    elif job_payload.get("file_bytes_b64"):
        # Direct upload path — bytes supplied as base64
        file_bytes = base64.b64decode(job_payload["file_bytes_b64"])
        if not file_name:
            file_name = "document"
    else:
        # No URL and no bytes — nothing to fetch
        logger.error(
            "process_document: no document_url and no file_bytes_b64 — cannot fetch document",
            extra={"job_id": job_id},
        )
        asyncio.get_event_loop().run_until_complete(
            _update_job_status(job_id, "failed", error_message="No document source available")
        )
        return {"job_id": job_id, "error": "no_document_source"}

    # ── Step 4: Parse with Unstructured.io ─────────────────────────────────────
    try:
        elements = UnstructuredService.partition_document(
            file_bytes=file_bytes,
            filename=file_name or "document",
            document_type_hint="unknown",
        )
        raw_text = UnstructuredService.elements_to_text(elements)
    except Exception as exc:
        logger.error("process_document: Unstructured.io parsing failed", extra={"job_id": job_id, "error": str(exc)})
        asyncio.get_event_loop().run_until_complete(
            _update_job_status(job_id, "failed", error_message=f"Unstructured.io error: {exc}")
        )
        raise self.retry(exc=exc)

    # ── Step 5: Create/update job record in Supabase ───────────────────────────
    asyncio.get_event_loop().run_until_complete(
        _upsert_job(
            job_id=job_id,
            organization_id=organization_id,
            location_id=location_id,
            file_name=file_name,
        )
    )

    # ── Step 6: Build result and chain to score_context ────────────────────────
    processed_result = {
        "job_id": job_id,
        "organization_id": organization_id,
        "location_id": location_id,
        "document_id": document_id,
        "acculynx_job_id": acculynx_job_id,
        "file_name": file_name,
        "raw_text": raw_text,
        "raw_path": None,
        "element_count": len(elements),
    }

    score_context.delay(processed_result)

    logger.info(
        "process_document complete",
        extra={"job_id": job_id, "element_count": len(elements), "raw_text_len": len(raw_text)},
    )
    return processed_result


@celery_app.task(
    name="intake.triage_document",
    bind=True,
    max_retries=3,
    retry_backoff=True,
    default_retry_delay=15,
    on_failure=_on_task_failure,
)
def triage_document(self: Any, parsed_result: dict[str, Any]) -> dict[str, Any]:
    """
    Task 3: Claude classifies the document type.

    Called by score_context for medium/high-context documents.
    Routes to:
      - extract_struct (structured: invoice, proposal, PO)
      - chunk_and_embed (unstructured: MSDS, manual, warranty)

    Args:
        parsed_result: ScoredDocumentResult-shaped dict from score_context.

    Returns:
        TriagedDocumentResult-shaped dict.
    """
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
            # Propagate context scoring fields for downstream tasks
            "context_routing": parsed_result.get("context_routing"),
            "context_score": parsed_result.get("score"),
            "acculynx_job_id": parsed_result.get("acculynx_job_id"),
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
    retry_backoff=True,
    default_retry_delay=15,
    on_failure=_on_task_failure,
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
    context_routing = triaged_result.get("context_routing")
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

        extraction_result = {
            "job_id": job_id,
            "organization_id": organization_id,
            "location_id": location_id,
            "document_id": document_id,
            "triage_status": triage_status,
            "extraction": extraction,
            "context_routing": context_routing,
            "acculynx_job_id": triaged_result.get("acculynx_job_id"),
        }

        logger.info(
            "extract_struct complete",
            extra={"job_id": job_id, "triage_status": triage_status, "context_routing": context_routing},
        )

        # Chain to leakage detection only for high-context documents
        if extraction_result.get("context_routing") == "high":
            detect_revenue_leakage.delay(extraction_result)

        return extraction_result

    except Exception as exc:
        logger.error("extract_struct failed", extra={"job_id": job_id, "error": str(exc)})
        raise self.retry(exc=exc)


@celery_app.task(
    name="intake.chunk_and_embed",
    bind=True,
    max_retries=3,
    retry_backoff=True,
    default_retry_delay=15,
    on_failure=_on_task_failure,
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


@celery_app.task(
    name="intake.score_context",
    bind=True,
    max_retries=3,
    retry_backoff=True,
    default_retry_delay=15,
    on_failure=_on_task_failure,
)
def score_context(self: Any, processed_result: dict[str, Any]) -> dict[str, Any]:
    """
    Task 2: Claude scores the document 0–100 using configurable rubric.

    Routes to:
      - bounce_back (low: 0–39) — do NOT proceed to triage
      - triage_document (medium: 40–79) — process but flag for Ops review
      - triage_document (high: 80–100) — full pipeline + leakage detection

    Args:
        processed_result: ProcessedDocumentResult-shaped dict from process_document.
    """
    import asyncio

    from backend.services.claude_service import ClaudeService

    job_id = processed_result.get("job_id", "unknown")
    location_id = processed_result.get("location_id")
    organization_id = processed_result.get("organization_id", "unknown")
    logger.info("score_context started", extra={"job_id": job_id})

    try:
        raw_text = processed_result.get("raw_text", "")
        file_name = processed_result.get("file_name", "")

        # Score document with Claude
        score_result = asyncio.get_event_loop().run_until_complete(
            ClaudeService.score_context(raw_text, file_name)
        )

        score = score_result.get("score")
        routing = score_result.get("routing")

        # Persist score to jobs table
        asyncio.get_event_loop().run_until_complete(
            _update_job_context_score(job_id, score, routing)
        )

        scored_result = {
            "job_id": job_id,
            "organization_id": organization_id,
            "location_id": location_id,
            "document_id": processed_result.get("document_id"),
            "raw_text": raw_text,
            "file_name": file_name,
            "raw_path": processed_result.get("raw_path"),
            "score": score,
            "routing": routing,
            # context_routing mirrors routing so downstream tasks can read either key
            "context_routing": routing,
            "breakdown": score_result.get("breakdown"),
            "document_summary": score_result.get("document_summary"),
            "clarification_question": score_result.get("clarification_question"),
            "acculynx_job_id": processed_result.get("acculynx_job_id"),
        }

        logger.info(
            "score_context complete",
            extra={"job_id": job_id, "score": score, "routing": routing},
        )

        if routing == "low":
            bounce_back.delay(scored_result)
        elif routing in ("medium", "high"):
            triage_document.delay(scored_result)
        else:
            logger.warning(
                "score_context returned unexpected routing value",
                extra={"job_id": job_id, "routing": routing},
            )

        return scored_result

    except Exception as exc:
        logger.error("score_context failed", extra={"job_id": job_id, "error": str(exc)})
        raise self.retry(exc=exc)


@celery_app.task(
    name="intake.bounce_back",
    bind=True,
    max_retries=3,
    retry_backoff=True,
    default_retry_delay=30,
    on_failure=_on_task_failure,
)
def bounce_back(self: Any, scored_result: dict[str, Any]) -> dict[str, Any]:
    """
    Low-context path (score 0–39).
    Sends notification to field contact via configured channel.
    Does NOT route to Ops. Does NOT attempt extraction.
    """
    import asyncio

    from backend.services.notification_service import NotificationMessage, get_notification_adapter
    from backend.core.config import get_settings

    job_id = scored_result.get("job_id", "unknown")
    location_id = scored_result.get("location_id")
    organization_id = scored_result.get("organization_id", "unknown")
    logger.info("bounce_back started", extra={"job_id": job_id})

    try:
        settings = get_settings()
        app_base_url = getattr(settings, "app_base_url", None) or "https://omnidrop.dev"
        deep_link = f"{app_base_url}/dashboard/ops/jobs/{job_id}"

        message = NotificationMessage(
            job_id=job_id,
            organization_id=organization_id,
            location_id=location_id,
            score=scored_result.get("score"),
            document_summary=scored_result.get("document_summary"),
            clarification_question=scored_result.get("clarification_question"),
            file_name=scored_result.get("file_name"),
            deep_link=deep_link,
        )

        # Fetch location row for notification_channels config
        location = asyncio.get_event_loop().run_until_complete(
            _get_location_row(location_id)
        ) if location_id else {}

        notification_channels = location.get("notification_channels") if location else None
        adapter = get_notification_adapter(notification_channels) if notification_channels else None

        if adapter is None:
            channel_used = "none"
            delivery_status = "no_channel"
            logger.warning(
                "bounce_back: no notification channel configured",
                extra={"job_id": job_id, "location_id": location_id},
            )
        else:
            send_result = adapter.send(message)
            channel_used = send_result.get("channel", "unknown")
            delivery_status = send_result.get("status", "unknown")

        # Write to bounce_back_log table
        asyncio.get_event_loop().run_until_complete(
            _write_bounce_back_log(
                job_id=job_id,
                organization_id=organization_id,
                location_id=location_id,
                score=scored_result.get("score"),
                channel_used=channel_used,
                delivery_status=delivery_status,
                deep_link=deep_link,
            )
        )

        # Update job status to "bounced"
        asyncio.get_event_loop().run_until_complete(
            _update_job_status(job_id, "bounced")
        )

        logger.info(
            "bounce_back complete",
            extra={"job_id": job_id, "channel_used": channel_used, "delivery_status": delivery_status},
        )

        return {
            "job_id": job_id,
            "organization_id": organization_id,
            "location_id": location_id,
            "channel_used": channel_used,
            "delivery_status": delivery_status,
        }

    except Exception as exc:
        logger.error("bounce_back failed", extra={"job_id": job_id, "error": str(exc)})
        raise self.retry(exc=exc)


@celery_app.task(
    name="intake.detect_revenue_leakage",
    bind=True,
    max_retries=3,
    retry_backoff=True,
    default_retry_delay=15,
    on_failure=_on_task_failure,
)
def detect_revenue_leakage(self: Any, extraction_result: dict[str, Any]) -> dict[str, Any]:
    """
    Task 5: Compare extracted line items against pricing reference.
    Only called for HIGH-context structured documents.

    Contract Mode: query pricing_contracts by organization_id.
    Baseline Mode: query vendor_baseline_prices view (fallback, ≥3 samples).
    No reference: log leakage_skipped_reason, skip gracefully.
    """
    import asyncio

    from backend.services.claude_service import ClaudeService

    job_id = extraction_result.get("job_id", "unknown")
    organization_id = extraction_result.get("organization_id", "unknown")
    location_id = extraction_result.get("location_id")
    logger.info("detect_revenue_leakage started", extra={"job_id": job_id})

    try:
        # Step 1: Try pricing_contracts (Contract Mode)
        contracts = asyncio.get_event_loop().run_until_complete(
            _query_pricing_contracts(organization_id)
        )

        if contracts:
            pricing_reference = contracts
            reference_mode = "contract"
        else:
            # Step 2: Fall back to vendor_baseline_prices view (Baseline Mode, ≥3 samples)
            baseline_rows = asyncio.get_event_loop().run_until_complete(
                _query_vendor_baseline_prices(organization_id)
            )
            if baseline_rows:
                # Rename baseline_unit_price to contracted_unit_price for ClaudeService compatibility
                pricing_reference = [
                    {**row, "contracted_unit_price": row["baseline_unit_price"]}
                    for row in baseline_rows
                ]
                reference_mode = "baseline"
            else:
                # Step 3: No pricing reference available — skip gracefully
                asyncio.get_event_loop().run_until_complete(
                    _update_job_leakage_skipped(job_id, "no_pricing_reference")
                )
                logger.info(
                    "detect_revenue_leakage skipped: no pricing reference",
                    extra={"job_id": job_id, "organization_id": organization_id},
                )
                return {"job_id": job_id, "finding_count": 0, "total_leakage_amount": 0.0}

        # Flatten confidence wrappers from extraction to plain values
        raw_line_items = extraction_result.get("extraction", {}).get("line_items", [])
        line_items = [
            {
                "description": item["description"]["value"] if isinstance(item.get("description"), dict) else item.get("description"),
                "unit_price": item["unit_price"]["value"] if isinstance(item.get("unit_price"), dict) else item.get("unit_price"),
                "quantity": item["quantity"]["value"] if isinstance(item.get("quantity"), dict) else item.get("quantity"),
            }
            for item in raw_line_items
        ]

        # Detect leakage with Claude
        leakage_result = asyncio.get_event_loop().run_until_complete(
            ClaudeService.detect_leakage(line_items, pricing_reference, reference_mode)
        )

        findings = leakage_result.get("findings", [])
        invoice_id = extraction_result.get("extraction", {}).get("invoice_id")

        # Write each finding to revenue_findings table
        if findings:
            asyncio.get_event_loop().run_until_complete(
                _write_revenue_findings(
                    findings=findings,
                    job_id=job_id,
                    organization_id=organization_id,
                    location_id=location_id,
                    invoice_id=invoice_id,
                    reference_mode=reference_mode,
                )
            )

        total_leakage = sum(f.get("leakage_amount", 0.0) for f in findings)
        finding_count = len(findings)

        logger.info(
            "detect_revenue_leakage complete",
            extra={"job_id": job_id, "finding_count": finding_count, "total_leakage_amount": total_leakage},
        )

        return {
            "job_id": job_id,
            "finding_count": finding_count,
            "total_leakage_amount": total_leakage,
        }

    except Exception as exc:
        logger.error("detect_revenue_leakage failed", extra={"job_id": job_id, "error": str(exc)})
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


async def _update_job_context_score(job_id: str, score: int | None, routing: str | None) -> None:
    """Persist context score and routing to the jobs table."""
    from backend.services.supabase_client import get_supabase_client

    client = await get_supabase_client()
    await (
        client.table("jobs")
        .update({"context_score": score, "context_routing": routing})
        .eq("job_id", job_id)
        .execute()
    )


async def _get_location_row(location_id: str) -> dict | None:
    """Fetch a location row from Supabase by location_id."""
    from backend.services.supabase_client import get_supabase_client

    client = await get_supabase_client()
    result = (
        await client.table("locations")
        .select("*")
        .eq("location_id", location_id)
        .maybe_single()
        .execute()
    )
    return result.data


async def _write_bounce_back_log(
    job_id: str,
    organization_id: str,
    location_id: str | None,
    score: int | None,
    channel_used: str,
    delivery_status: str,
    deep_link: str,
) -> None:
    """Write a row to the bounce_back_log table."""
    from backend.services.supabase_client import get_supabase_client

    client = await get_supabase_client()
    await client.table("bounce_back_log").insert({
        "job_id": job_id,
        "organization_id": organization_id,
        "location_id": location_id,
        "context_score": score,
        "channel_used": channel_used,
        "delivery_status": delivery_status,
        "deep_link": deep_link,
    }).execute()


async def _update_job_leakage_skipped(job_id: str, reason: str) -> None:
    """Record why leakage detection was skipped on the jobs table."""
    from backend.services.supabase_client import get_supabase_client

    client = await get_supabase_client()
    await (
        client.table("jobs")
        .update({"leakage_skipped_reason": reason})
        .eq("job_id", job_id)
        .execute()
    )


async def _query_pricing_contracts(organization_id: str) -> list[dict[str, Any]]:
    """Return pricing_contracts rows for an organization, or empty list if none."""
    from backend.services.supabase_client import get_supabase_client

    client = await get_supabase_client()
    result = (
        await client.table("pricing_contracts")
        .select("vendor_name, description, contracted_unit_price")
        .eq("organization_id", organization_id)
        .execute()
    )
    return result.data or []


async def _query_vendor_baseline_prices(organization_id: str) -> list[dict[str, Any]]:
    """Return vendor_baseline_prices view rows with sample_count >= 3, or empty list."""
    from backend.services.supabase_client import get_supabase_client

    client = await get_supabase_client()
    result = (
        await client.table("vendor_baseline_prices")
        .select("vendor_name, description, baseline_unit_price, sample_count")
        .eq("organization_id", organization_id)
        .gte("sample_count", 3)
        .execute()
    )
    return result.data or []


async def _upsert_job(
    job_id: str,
    organization_id: str | None,
    location_id: str | None,
    file_name: str | None,
) -> None:
    """Update job status to 'processing', inserting a new row if one doesn't exist yet."""
    from backend.services.supabase_client import get_supabase_client

    client = await get_supabase_client()
    update_result = (
        await client.table("jobs")
        .update({"status": "processing", "file_name": file_name})
        .eq("job_id", job_id)
        .execute()
    )
    if not update_result.data:
        # Row not yet created by the webhook endpoint — insert it
        await client.table("jobs").insert({
            "job_id": job_id,
            "organization_id": organization_id,
            "location_id": location_id,
            "status": "processing",
            "file_name": file_name,
        }).execute()


async def _write_revenue_findings(
    findings: list[dict[str, Any]],
    job_id: str,
    organization_id: str,
    location_id: str | None,
    invoice_id: str | None,
    reference_mode: str,
) -> None:
    """Insert revenue leakage findings into the revenue_findings table."""
    from backend.services.supabase_client import get_supabase_client

    client = await get_supabase_client()

    rows = []
    for finding in findings:
        rows.append({
            "job_id": job_id,
            "organization_id": organization_id,
            "location_id": location_id,
            "invoice_id": invoice_id,
            "line_item_id": finding.get("line_item_id"),
            "contract_id": finding.get("contract_id"),  # None for baseline mode
            "reference_mode": reference_mode,
            "vendor_name": finding.get("vendor_name"),
            "sku": finding.get("sku"),
            "invoiced_unit_price": finding.get("invoiced_unit_price"),
            "reference_unit_price": finding.get("reference_unit_price"),
            "quantity": finding.get("quantity"),
            "leakage_amount": finding.get("leakage_amount"),
        })

    if rows:
        await client.table("revenue_findings").insert(rows).execute()
