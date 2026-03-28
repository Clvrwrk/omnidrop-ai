"""
OmniDrop AI — Document Upload Endpoint
POST /api/v1/documents/upload
"""

import logging
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, File, Form, UploadFile

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post(
    "/documents/upload",
    status_code=202,
    summary="Upload a document for processing",
)
async def upload_document(
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
    job_id = str(uuid4())
    # TODO: Store raw bytes to Supabase Storage, create jobs row, dispatch Celery task
    return {
        "job_id": job_id,
        "organization_id": organization_id,
        "location_id": location_id,
        "status": "queued",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
