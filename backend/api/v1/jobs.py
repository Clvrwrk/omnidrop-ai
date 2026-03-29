"""
OmniDrop AI — Jobs Endpoints
GET /api/v1/jobs           — paginated list scoped to the authenticated org
GET /api/v1/jobs/{job_id}  — single job detail with document join

Both endpoints:
  - Extract organization_id from WorkOS session headers (never from request body)
  - Join jobs → locations (for location_name)
  - Join jobs → documents (for document_type, document_id)
  - Return shapes defined in docs/api-contracts.md §1.3
"""

import logging

from fastapi import APIRouter, HTTPException, Query, Request

from backend.services.supabase_client import (
    get_or_create_organization,
    get_or_create_organization_by_user_id,
    get_supabase_client,
)

router = APIRouter()
logger = logging.getLogger(__name__)


async def _resolve_organization_id(request: Request) -> str:
    """
    Derive the internal organization_id from WorkOS session headers.
    Raises 401 if no auth context is present.
    """
    workos_org_id = request.headers.get("x-workos-org-id")
    workos_user_id = request.headers.get("x-workos-user-id")
    workos_org_name = request.headers.get("x-workos-org-name", "My Organization")

    if workos_org_id:
        org = await get_or_create_organization(workos_org_id, workos_org_name)
    elif workos_user_id:
        org = await get_or_create_organization_by_user_id(workos_user_id)
    else:
        raise HTTPException(status_code=401, detail="Missing authentication context.")

    return org["organization_id"]


def _shape_job_row(row: dict) -> dict:
    """
    Normalise a raw Supabase jobs row (with optional nested location/document)
    into the API contract shape.
    """
    # Supabase returns nested FK joins as nested dicts when using select("*, ...")
    location = row.get("locations") or {}
    document = row.get("documents") or {}

    return {
        "job_id": str(row["job_id"]),
        "organization_id": str(row["organization_id"]) if row.get("organization_id") else None,
        "location_id": str(row["location_id"]) if row.get("location_id") else None,
        "location_name": location.get("name"),
        "status": row.get("status"),
        "document_type": document.get("document_type"),
        "file_name": row.get("file_name"),
        "raw_path": row.get("raw_path"),
        "created_at": row.get("created_at"),
        "completed_at": row.get("completed_at"),
        "error_message": row.get("error_message"),
        "document_id": str(document["document_id"]) if document.get("document_id") else None,
    }


@router.get("/jobs", summary="List jobs for the authenticated organization")
async def list_jobs(
    request: Request,
    location_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """
    Returns a paginated list of jobs scoped to the authenticated organization.
    Optionally filtered by location_id and/or status.

    Joins locations for location_name and documents for document_type + document_id.
    """
    organization_id = await _resolve_organization_id(request)
    client = await get_supabase_client()

    # Build query — left-join locations and documents for enriched response
    query = (
        client.table("jobs")
        .select(
            "job_id, organization_id, location_id, status, file_name, raw_path, "
            "created_at, completed_at, error_message, "
            "locations(name), "
            "documents(document_id, document_type)",
            count="exact",
        )
        .eq("organization_id", organization_id)
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
    )

    if location_id:
        query = query.eq("location_id", location_id)
    if status:
        query = query.eq("status", status)

    result = await query.execute()

    jobs = [_shape_job_row(row) for row in (result.data or [])]
    total = result.count or 0

    logger.debug(
        "list_jobs",
        extra={"organization_id": organization_id, "total": total, "limit": limit, "offset": offset},
    )

    return {
        "jobs": jobs,
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.get("/jobs/{job_id}", summary="Get single job detail")
async def get_job(job_id: str, request: Request) -> dict:
    """
    Returns full detail for a single job.
    Returns 404 if the job does not exist or belongs to a different organization.
    """
    organization_id = await _resolve_organization_id(request)
    client = await get_supabase_client()

    result = await (
        client.table("jobs")
        .select(
            "job_id, organization_id, location_id, status, file_name, raw_path, "
            "created_at, completed_at, error_message, "
            "locations(name), "
            "documents(document_id, document_type)",
        )
        .eq("job_id", job_id)
        .eq("organization_id", organization_id)
        .maybe_single()
        .execute()
    )

    if not result or not result.data:
        raise HTTPException(
            status_code=404,
            detail=f"Job '{job_id}' not found.",
        )

    return _shape_job_row(result.data)
