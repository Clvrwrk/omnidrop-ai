"""
OmniDrop AI — Document Upload Endpoint
POST /api/v1/documents/upload

Freemium gate:  org.documents_processed >= org.max_documents → 402
Storage:        upload raw bytes to Supabase Storage bucket "documents"
                at path {org_id}/{job_id}/{filename}
Job row:        INSERT into jobs with status="queued", raw_path set
Celery:         process_document.delay(job_payload) — non-blocking
Response:       202 Accepted immediately; frontend polls GET /jobs/{job_id}
"""

import base64
import logging
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from backend.services.supabase_client import (
    get_or_create_organization,
    get_or_create_organization_by_user_id,
    get_supabase_client,
)

router = APIRouter()
logger = logging.getLogger(__name__)

_ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/tiff",
    "image/webp",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/csv",
}

# 50 MB hard limit — matches the Storage bucket file_size_limit
_MAX_FILE_BYTES = 50 * 1024 * 1024


@router.post(
    "/documents/upload",
    status_code=202,
    summary="Upload a document for processing",
)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    organization_id: str = Form(...),
    location_id: str | None = Form(default=None),
) -> dict:
    """
    Accepts a file upload, validates quota, stores raw bytes to Supabase Storage,
    creates a jobs row, and dispatches process_document.delay() — returns 202 immediately.

    Auth: organization_id is resolved from the WorkOS session headers, not the form body.
    The form organization_id is accepted per the API contract but the internal org row
    is always derived from x-workos-org-id / x-workos-user-id to prevent tenant spoofing.
    """
    # ── 1. Extract WorkOS session context ──────────────────────────────────────
    workos_org_id = request.headers.get("x-workos-org-id")
    workos_user_id = request.headers.get("x-workos-user-id")
    workos_org_name = request.headers.get("x-workos-org-name", "My Organization")

    if not workos_org_id and not workos_user_id:
        raise HTTPException(status_code=401, detail="Missing authentication context.")

    # ── 2. Resolve org row + freemium quota gate ───────────────────────────────
    if workos_org_id:
        org = await get_or_create_organization(workos_org_id, workos_org_name)
    else:
        org = await get_or_create_organization_by_user_id(workos_user_id)

    if org.get("documents_processed", 0) >= org.get("max_documents", 500):
        raise HTTPException(
            status_code=402,
            detail="Document quota reached. Upgrade to continue.",
        )

    # ── 3. Validate file type ──────────────────────────────────────────────────
    content_type = (file.content_type or "").split(";")[0].strip()
    if content_type not in _ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file type '{content_type}'. "
                "Accepted: PDF, JPEG, PNG, TIFF, WebP, XLS/XLSX, CSV."
            ),
        )

    # ── 4. Read bytes + enforce size limit ─────────────────────────────────────
    file_bytes = await file.read()
    if len(file_bytes) > _MAX_FILE_BYTES:
        raise HTTPException(
            status_code=413,
            detail="File exceeds the 50 MB maximum. Please compress or split the document.",
        )

    file_name = file.filename or "document"
    internal_org_id: str = org["organization_id"]
    job_id = str(uuid4())

    # ── 5. Upload raw bytes to Supabase Storage ────────────────────────────────
    # Path: {org_id}/{job_id}/{filename} — scoped by org_id for future RLS policies
    storage_path = f"{internal_org_id}/{job_id}/{file_name}"
    client = await get_supabase_client()

    try:
        await client.storage.from_("documents").upload(
            path=storage_path,
            file=file_bytes,
            file_options={"content-type": content_type, "upsert": "false"},
        )
    except Exception as exc:
        logger.error(
            "upload_document: Storage upload failed",
            extra={"job_id": job_id, "path": storage_path, "error": str(exc)},
        )
        raise HTTPException(status_code=500, detail="File storage failed. Please retry.")

    # ── 6. Insert jobs row with status="queued" ────────────────────────────────
    created_at = datetime.now(timezone.utc).isoformat()
    try:
        await client.table("jobs").insert({
            "job_id": job_id,
            "organization_id": internal_org_id,
            "location_id": location_id,
            "status": "queued",
            "file_name": file_name,
            "raw_path": storage_path,
        }).execute()
    except Exception as exc:
        logger.error(
            "upload_document: failed to insert jobs row",
            extra={"job_id": job_id, "error": str(exc)},
        )
        # Best-effort cleanup of the orphaned Storage object
        try:
            await client.storage.from_("documents").remove([storage_path])
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Failed to create job record. Please retry.")

    # ── 7. Dispatch Celery task — non-blocking ─────────────────────────────────
    # Pass file_bytes_b64 so the worker can process without a round-trip to Storage.
    # The worker falls back to document_url / raw_path download if the key is absent.
    from backend.workers.intake_tasks import process_document

    process_document.delay({
        "job_id": job_id,
        "organization_id": internal_org_id,
        "location_id": location_id,
        "file_name": file_name,
        "raw_path": storage_path,
        "file_bytes_b64": base64.b64encode(file_bytes).decode(),
    })

    logger.info(
        "upload_document: job queued",
        extra={
            "job_id": job_id,
            "organization_id": internal_org_id,
            "location_id": location_id,
            "file_name": file_name,
            "file_size_bytes": len(file_bytes),
        },
    )

    # ── 8. Return 202 immediately ──────────────────────────────────────────────
    return {
        "job_id": job_id,
        "organization_id": internal_org_id,
        "location_id": location_id,
        "status": "queued",
        "created_at": created_at,
    }
