"""
OmniDrop AI — HITL Triage Endpoints

T2-08:
  GET  /api/v1/triage              — list docs with triage_status='needs_clarity'
  GET  /api/v1/triage/{document_id} — full extraction + signed Storage URL (1hr)

T2-09:
  PATCH /api/v1/triage/{document_id} — save HITL corrections → context_reference_examples

Auth: organization_id extracted from WorkOS session headers on every request.
Signed URLs: generated server-side via Supabase Storage create_signed_url (3600s expiry).
Confidence scores: read from invoices.extraction_meta JSONB — the full Claude output
stored by extract_struct. Never recompute — read what was written.

T2-09 notes:
  - action='confirm': triage_status → 'confirmed', no invoice changes, write context example
  - action='reject':  triage_status → 'rejected', no invoice changes, no context example
  - action='correct': apply scalar corrections to invoices, replace line_items entirely,
                      triage_status → 'confirmed', write context example
  - context_reference_examples: label='high', label_source='hitl_correction'
    rubric_score derived from the document's jobs.context_score (0 if absent).
    embedding column left NULL — Phase 2+ vector scoring will populate it.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, field_validator

from backend.services.supabase_client import (
    get_or_create_organization,
    get_or_create_organization_by_user_id,
    get_supabase_client,
)

router = APIRouter()
logger = logging.getLogger(__name__)

# Confidence threshold below which a field is counted as "low confidence"
_LOW_CONFIDENCE_THRESHOLD = 0.8

# Scalar fields that carry confidence scores in extraction_meta
_SCORED_FIELDS = (
    "vendor_name", "invoice_number", "invoice_date",
    "due_date", "subtotal", "tax", "total", "notes",
)

# Map DB triage_status values → API contract status values
_STATUS_MAP = {
    "needs_clarity": "pending",
    "pending":       "pending",
    "confirmed":     "confirmed",
    "rejected":      "rejected",
}


# ── Auth helper ────────────────────────────────────────────────────────────────

async def _resolve_organization_id(request: Request) -> str:
    """Derive internal organization_id from WorkOS session headers. Raises 401 if absent."""
    workos_org_id = request.headers.get("x-workos-org-id")
    workos_user_id = request.headers.get("x-workos-user-id")
    workos_org_name = request.headers.get("x-workos-org-name", "My Organization")

    if workos_org_id:
        org = await get_or_create_organization(workos_org_id, workos_org_name)
    elif workos_user_id:
        org = await get_or_create_organization_by_user_id(workos_user_id)
    else:
        raise HTTPException(status_code=401, detail="Missing authentication context.")

    return str(org["organization_id"])


# ── Confidence helpers ─────────────────────────────────────────────────────────

def _confidence_summary(extraction_meta: dict | None) -> tuple[float, int]:
    """
    Given the full extraction_meta JSONB (Claude's confidence-annotated output),
    return (min_confidence_score, low_confidence_field_count) across all scalar fields.

    Returns (1.0, 0) if extraction_meta is absent or has no scored fields,
    so the document still appears in the queue but with no red flags.
    """
    if not extraction_meta:
        return 1.0, 0

    scores: list[float] = []
    low_count = 0

    for field in _SCORED_FIELDS:
        field_data = extraction_meta.get(field)
        if isinstance(field_data, dict) and "confidence" in field_data:
            c = float(field_data["confidence"])
            scores.append(c)
            if c < _LOW_CONFIDENCE_THRESHOLD:
                low_count += 1

    # Also scan line_items for low-confidence fields
    for item in (extraction_meta.get("line_items") or []):
        if not isinstance(item, dict):
            continue
        for sub_field in ("description", "quantity", "unit_price", "amount"):
            sub_data = item.get(sub_field)
            if isinstance(sub_data, dict) and "confidence" in sub_data:
                c = float(sub_data["confidence"])
                scores.append(c)
                if c < _LOW_CONFIDENCE_THRESHOLD:
                    low_count += 1

    min_score = min(scores) if scores else 1.0
    return round(min_score, 4), low_count


def _build_extraction(extraction_meta: dict | None) -> dict:
    """
    Return the full confidence-annotated extraction shape the API contract expects.

    If extraction_meta is present, return it directly — it was already written in
    the exact contract shape by extract_struct / _save_structured_extraction.
    If absent, return a skeleton with null values and 0.0 confidence so the
    frontend always receives a complete, predictable object.
    """
    if extraction_meta:
        return extraction_meta

    # Skeleton for documents that have no invoice yet (shouldn't normally reach triage)
    skeleton_field: dict = {"value": None, "confidence": 0.0}
    return {
        "vendor_name":    dict(skeleton_field),
        "invoice_number": dict(skeleton_field),
        "invoice_date":   dict(skeleton_field),
        "due_date":       dict(skeleton_field),
        "subtotal":       dict(skeleton_field),
        "tax":            dict(skeleton_field),
        "total":          dict(skeleton_field),
        "notes":          dict(skeleton_field),
        "line_items":     [],
    }


# ── T2-08: GET /api/v1/triage ─────────────────────────────────────────────────

@router.get("/triage", summary="List documents pending HITL review")
async def list_triage(
    request: Request,
    location_id: str | None = Query(default=None),
    limit: int = Query(default=25, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """
    Returns documents with triage_status='needs_clarity' scoped to the authenticated org.

    These are medium-context structured documents where Claude's extraction
    confidence was too low for auto-confirmation. An accountant must review
    each item in the split-screen UI before the pipeline continues.

    Joins:
      documents → jobs (for file_name)
      documents → locations (for location_name)
      documents → invoices (for extraction_meta → confidence summary)

    Confidence fields are computed from invoices.extraction_meta at read time.
    The 0.8 threshold for "low confidence" matches the extract_struct routing logic.
    """
    organization_id = await _resolve_organization_id(request)
    client = await get_supabase_client()

    # Build base query — filter to needs_clarity only, scoped to org
    query = (
        client.table("documents")
        .select(
            "document_id, job_id, location_id, document_type, triage_status, created_at, "
            "jobs(file_name), "
            "locations(name), "
            "invoices(extraction_meta)",
            count="exact",
        )
        .eq("organization_id", organization_id)
        .eq("triage_status", "needs_clarity")
        .order("created_at", desc=False)   # oldest first — FIFO review queue
        .range(offset, offset + limit - 1)
    )

    if location_id:
        query = query.eq("location_id", location_id)

    result = await query.execute()

    items = []
    for row in (result.data or []):
        job = row.get("jobs") or {}
        location = row.get("locations") or {}

        # invoices is a list when using FK join (one doc can have one invoice)
        invoices_join = row.get("invoices")
        invoice = None
        if isinstance(invoices_join, list) and invoices_join:
            invoice = invoices_join[0]
        elif isinstance(invoices_join, dict):
            invoice = invoices_join

        extraction_meta = invoice.get("extraction_meta") if invoice else None
        min_conf, low_count = _confidence_summary(extraction_meta)

        items.append({
            "document_id":              str(row["document_id"]),
            "job_id":                   str(row["job_id"]),
            "file_name":                job.get("file_name"),
            "document_type":            row.get("document_type"),
            "min_confidence_score":     min_conf,
            "low_confidence_field_count": low_count,
            "created_at":               row.get("created_at"),
            "location_name":            location.get("name"),
        })

    total = result.count or 0

    logger.debug(
        "list_triage",
        extra={
            "organization_id": organization_id,
            "location_id": location_id,
            "total": total,
            "limit": limit,
            "offset": offset,
        },
    )

    return {"items": items, "total": total}


# ── T2-08: GET /api/v1/triage/{document_id} ───────────────────────────────────

@router.get("/triage/{document_id}", summary="Full triage detail with signed Storage URL")
async def get_triage_detail(document_id: str, request: Request) -> dict:
    """
    Returns the full extraction with per-field confidence scores and a signed
    Supabase Storage URL for the original document (1-hour expiry).

    Data sources:
      - documents: triage_status, raw_path, document_type
      - jobs: file_name (via documents.job_id)
      - invoices.extraction_meta: full confidence-annotated Claude output
      - Supabase Storage: signed URL generated server-side (never expose service key)

    The extraction field is served exactly as stored by extract_struct —
    the full {"value": ..., "confidence": ...} shape per field.

    Returns 404 if the document doesn't exist or belongs to another org.
    """
    organization_id = await _resolve_organization_id(request)
    client = await get_supabase_client()

    # Fetch document row with all joins in one query
    doc_result = await (
        client.table("documents")
        .select(
            "document_id, job_id, location_id, document_type, "
            "raw_path, triage_status, organization_id, "
            "jobs(file_name, raw_path), "
            "invoices(invoice_id, extraction_meta)",
        )
        .eq("document_id", document_id)
        .eq("organization_id", organization_id)
        .maybe_single()
        .execute()
    )

    if not doc_result or not doc_result.data:
        raise HTTPException(
            status_code=404,
            detail=f"Document '{document_id}' not found.",
        )

    doc = doc_result.data
    job = doc.get("jobs") or {}

    # Resolve the invoice and extraction_meta
    invoices_join = doc.get("invoices")
    invoice = None
    if isinstance(invoices_join, list) and invoices_join:
        invoice = invoices_join[0]
    elif isinstance(invoices_join, dict):
        invoice = invoices_join

    extraction_meta = invoice.get("extraction_meta") if invoice else None
    extraction = _build_extraction(extraction_meta)

    # ── Generate signed Storage URL ────────────────────────────────────────────
    # Prefer documents.raw_path; fall back to jobs.raw_path (set by upload endpoint)
    raw_path: str | None = doc.get("raw_path") or job.get("raw_path")
    document_url: str | None = None

    if raw_path:
        try:
            signed = await client.storage.from_("documents").create_signed_url(
                path=raw_path,
                expires_in=3600,   # 1-hour expiry per API contract
            )
            # Supabase Python SDK returns {"signedURL": "..."} or {"signed_url": "..."}
            document_url = (
                signed.get("signedURL")
                or signed.get("signed_url")
                or signed.get("signedUrl")
            )
        except Exception as exc:
            # Non-fatal: log and continue. The frontend renders the doc fields
            # even without a URL — accountant can still submit corrections.
            logger.warning(
                "get_triage_detail: failed to generate signed URL",
                extra={
                    "document_id": document_id,
                    "raw_path": raw_path,
                    "error": str(exc),
                },
            )

    # Map DB triage_status → API contract status
    db_status = doc.get("triage_status", "pending")
    api_status = _STATUS_MAP.get(db_status, "pending")

    file_name = job.get("file_name") or raw_path.split("/")[-1] if raw_path else None

    logger.debug(
        "get_triage_detail",
        extra={
            "document_id": document_id,
            "organization_id": organization_id,
            "triage_status": db_status,
            "has_signed_url": document_url is not None,
        },
    )

    return {
        "document_id":    str(doc["document_id"]),
        "job_id":         str(doc["job_id"]),
        "file_name":      file_name,
        "document_url":   document_url,
        "extraction":     extraction,
        "status":         api_status,
    }


# ── T2-09: PATCH /api/v1/triage/{document_id} ────────────────────────────────

_VALID_ACTIONS = {"confirm", "reject", "correct"}

# Scalar invoice fields that corrections may include
_INVOICE_SCALAR_FIELDS = (
    "vendor_name", "invoice_number", "invoice_date",
    "due_date", "subtotal", "tax", "total", "notes",
)


class TriagePatchRequest(BaseModel):
    action: str  # "confirm" | "reject" | "correct"
    corrections: dict[str, Any] | None = None

    @field_validator("action")
    @classmethod
    def _validate_action(cls, v: str) -> str:
        if v not in _VALID_ACTIONS:
            raise ValueError(f"action must be one of: {', '.join(sorted(_VALID_ACTIONS))}")
        return v


async def _apply_invoice_corrections(
    client: Any,
    invoice_id: str,
    corrections: dict[str, Any],
) -> None:
    """
    Apply scalar field corrections to invoices and replace line_items.

    Scalar fields are written as their raw values (not the confidence wrapper) —
    the HITL correction IS the confirmed value, confidence is implicitly 1.0.

    Line items are fully replaced: all existing rows for this invoice_id are
    deleted, then new rows are inserted in order. This avoids partial-update
    complexity and ensures the table reflects exactly what the accountant confirmed.
    """
    # ── Scalar fields ──────────────────────────────────────────────────────────
    invoice_update: dict[str, Any] = {}
    for field in _INVOICE_SCALAR_FIELDS:
        if field in corrections:
            invoice_update[field] = corrections[field]

    if invoice_update:
        await (
            client.table("invoices")
            .update(invoice_update)
            .eq("invoice_id", invoice_id)
            .execute()
        )

    # ── Line items (full replace) ──────────────────────────────────────────────
    corrected_items = corrections.get("line_items")
    if corrected_items is not None:
        # Delete all existing line items for this invoice
        await (
            client.table("line_items")
            .delete()
            .eq("invoice_id", invoice_id)
            .execute()
        )

        # Insert corrected items with sort_order preserved
        if corrected_items:
            rows = [
                {
                    "invoice_id":   invoice_id,
                    "description":  item.get("description"),
                    "quantity":     item.get("quantity"),
                    "unit_price":   item.get("unit_price"),
                    "amount":       item.get("amount"),
                    "sort_order":   idx,
                }
                for idx, item in enumerate(corrected_items)
            ]
            await client.table("line_items").insert(rows).execute()


async def _write_context_reference_example(
    client: Any,
    organization_id: str,
    document_id: str,
    context_score: int,
) -> None:
    """
    Write a context_reference_example row for confirmed/corrected documents.

    label='high'                 — accountant confirmed the document is valid
    label_source='hitl_correction'
    rubric_score                 — from jobs.context_score (0 if absent/NULL)
    embedding                    — NULL until Phase 2 vector scoring

    This is fire-and-forget from the endpoint perspective: a failure here is
    logged but does NOT roll back the triage decision. The document is still
    confirmed. The example can be re-derived later if needed.
    """
    await (
        client.table("context_reference_examples")
        .insert({
            "organization_id": organization_id,
            "document_id":     document_id,
            "label":           "high",
            "label_source":    "hitl_correction",
            "rubric_score":    context_score,
            # embedding: NULL — Phase 2 will populate via vector scoring task
        })
        .execute()
    )


@router.patch("/triage/{document_id}", summary="Submit triage decision")
async def patch_triage(
    document_id: str,
    body: TriagePatchRequest,
    request: Request,
) -> dict:
    """
    Accountant submits a triage decision for a document awaiting HITL review.

    Actions:
      confirm  — marks the extraction as correct; writes a context example
      reject   — marks the document as rejected; no invoice changes
      correct  — applies scalar/line-item corrections to invoices, then confirms;
                 writes a context example

    After any action the document exits the triage queue (triage_status no longer
    'needs_clarity'). The response always carries the final status and timestamp.

    Returns 400 if corrections are missing when action='correct'.
    Returns 404 if the document doesn't exist or belongs to another org.
    Returns 409 if the document is already confirmed or rejected (not re-triageable).
    """
    organization_id = await _resolve_organization_id(request)
    client = await get_supabase_client()

    # ── 1. Fetch document (org-scoped, with invoice + job context_score) ───────
    doc_result = await (
        client.table("documents")
        .select(
            "document_id, organization_id, triage_status, "
            "jobs(context_score), "
            "invoices(invoice_id)",
        )
        .eq("document_id", document_id)
        .eq("organization_id", organization_id)
        .maybe_single()
        .execute()
    )

    if not doc_result or not doc_result.data:
        raise HTTPException(
            status_code=404,
            detail=f"Document '{document_id}' not found.",
        )

    doc = doc_result.data
    current_status = doc.get("triage_status", "pending")

    # ── 2. Guard: already decided ──────────────────────────────────────────────
    if current_status in ("confirmed", "rejected"):
        raise HTTPException(
            status_code=409,
            detail=(
                f"Document '{document_id}' is already '{current_status}' "
                "and cannot be re-triaged."
            ),
        )

    # ── 3. Validate corrections presence for 'correct' action ─────────────────
    if body.action == "correct" and not body.corrections:
        raise HTTPException(
            status_code=400,
            detail="corrections must be provided when action='correct'.",
        )

    # ── 4. Resolve invoice_id (needed for correct action) ─────────────────────
    invoices_join = doc.get("invoices")
    invoice = None
    if isinstance(invoices_join, list) and invoices_join:
        invoice = invoices_join[0]
    elif isinstance(invoices_join, dict):
        invoice = invoices_join
    invoice_id: str | None = invoice.get("invoice_id") if invoice else None

    # ── 5. Apply corrections (correct action only) ────────────────────────────
    if body.action == "correct":
        if not invoice_id:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Document '{document_id}' has no invoice record. "
                    "Cannot apply corrections."
                ),
            )
        await _apply_invoice_corrections(client, invoice_id, body.corrections)  # type: ignore[arg-type]

    # ── 6. Update triage_status on documents ──────────────────────────────────
    new_status = "rejected" if body.action == "reject" else "confirmed"
    now_iso = datetime.now(timezone.utc).isoformat()

    await (
        client.table("documents")
        .update({"triage_status": new_status})
        .eq("document_id", document_id)
        .execute()
    )

    # ── 7. Write context reference example (confirm + correct only) ───────────
    if body.action in ("confirm", "correct"):
        # Derive context_score from the joined job row
        job_join = doc.get("jobs")
        job = None
        if isinstance(job_join, list) and job_join:
            job = job_join[0]
        elif isinstance(job_join, dict):
            job = job_join
        context_score: int = int(job.get("context_score") or 0) if job else 0

        try:
            await _write_context_reference_example(
                client, organization_id, document_id, context_score
            )
        except Exception as exc:
            # Non-fatal: log and continue — the triage decision is already committed.
            logger.warning(
                "patch_triage: failed to write context_reference_example",
                extra={
                    "document_id": document_id,
                    "organization_id": organization_id,
                    "error": str(exc),
                },
            )

    logger.info(
        "patch_triage",
        extra={
            "document_id": document_id,
            "organization_id": organization_id,
            "action": body.action,
            "new_status": new_status,
        },
    )

    return {
        "document_id": str(doc["document_id"]),
        "status":      new_status,
        "updated_at":  now_iso,
    }
