"""
OmniDrop AI — Document Upload Endpoint
POST /api/v1/documents/upload
"""

import logging
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from backend.services.supabase_client import get_or_create_organization

router = APIRouter()
logger = logging.getLogger(__name__)


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
    Accepts a file upload, creates a job, dispatches process_document.
    Returns immediately — frontend polls GET /jobs/{job_id} for status.

    organization_id is required. location_id is optional — documents can be
    uploaded at the org level without an AccuLynx location.
    """
    # Freemium quota check — WorkOS injects x-workos-org-id for authenticated users.
    workos_org_id = request.headers.get("x-workos-org-id")
    workos_org_name = request.headers.get("x-workos-org-name", "")
    if workos_org_id:
        org = await get_or_create_organization(workos_org_id, workos_org_name)
        if org.get("documents_processed", 0) >= org.get("max_documents", 500):
            raise HTTPException(status_code=402, detail="Document quota reached. Upgrade to continue.")

    job_id = str(uuid4())
    # TODO: Store raw bytes to Supabase Storage, create jobs row, dispatch Celery task
    return {
        "job_id": job_id,
        "organization_id": organization_id,
        "location_id": location_id,
        "status": "queued",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
