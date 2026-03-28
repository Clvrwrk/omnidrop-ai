"""
OmniDrop AI — HITL Triage Endpoints
GET  /api/v1/triage
GET  /api/v1/triage/{document_id}
PATCH /api/v1/triage/{document_id}
"""

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter()


class TriagePatchRequest(BaseModel):
    action: str  # "confirm" | "reject" | "correct"
    corrections: dict[str, Any] | None = None


@router.get("/triage", summary="List documents pending human review")
async def list_triage(
    location_id: str | None = Query(default=None),
    limit: int = Query(default=25, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """Returns triage queue. Placeholder."""
    # TODO: Query documents where triage_status = 'pending'
    return {
        "items": [],
        "total": 0,
    }


@router.get("/triage/{document_id}", summary="Get full triage detail for review")
async def get_triage_detail(document_id: str) -> dict:
    """Returns extraction with confidence scores + signed PDF URL. Placeholder."""
    # TODO: Join documents + invoices + extraction_meta, generate signed URL
    return {
        "document_id": document_id,
        "job_id": None,
        "file_name": None,
        "document_url": None,
        "extraction": {},
        "status": "pending",
    }


@router.patch("/triage/{document_id}", summary="Submit triage decision")
async def patch_triage(document_id: str, body: TriagePatchRequest) -> dict:
    """Accountant confirms, rejects, or corrects extraction. Placeholder."""
    # TODO: Update documents.triage_status, apply corrections to invoices/line_items
    from datetime import datetime, timezone

    return {
        "document_id": document_id,
        "status": "confirmed" if body.action == "confirm" else "rejected",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
