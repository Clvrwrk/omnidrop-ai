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
    location_id: str = Form(...),
) -> dict:
    """
    Accepts a file upload, creates a job, dispatches process_document.
    Returns immediately — frontend polls GET /jobs/{job_id} for status.
    """
    job_id = str(uuid4())
    # TODO: Store raw bytes to Supabase Storage, create jobs row, dispatch Celery task
    return {
        "job_id": job_id,
        "status": "queued",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
