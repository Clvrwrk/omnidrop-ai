"""
OmniDrop AI — Intake Events Endpoint
GET /api/v1/events

Returns recent raw webhook events received from AccuLynx via Hookdeck.
Scoped to the authenticated organization. Supports optional location_id
filter (resolved via join to the jobs table) and pagination.

Response shape matches docs/api-contracts.md §1.3 (Intake Events Feed).
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

    return org["organization_id"]


@router.get("/events", summary="List recent intake events for the authenticated organization")
async def list_events(
    request: Request,
    limit: int = Query(default=25, le=100),
    offset: int = Query(default=0, ge=0),
    location_id: str | None = Query(default=None),
) -> dict:
    """
    Returns recent intake_events scoped to the authenticated organization.

    The intake_events table carries organization_id directly. When location_id is
    supplied, we first resolve the job_ids belonging to that location (within this
    org), then filter events to only those job_ids.

    Pagination: limit + offset. Default limit 25, max 100.
    """
    organization_id = await _resolve_organization_id(request)
    client = await get_supabase_client()

    if location_id:
        # Resolve job_ids for this location so we can filter events
        jobs_result = await (
            client.table("jobs")
            .select("job_id")
            .eq("organization_id", organization_id)
            .eq("location_id", location_id)
            .execute()
        )
        job_ids = [str(row["job_id"]) for row in (jobs_result.data or [])]

        if not job_ids:
            return {"events": [], "total": 0}

        query = (
            client.table("intake_events")
            .select("event_id, job_id, source, event_type, received_at, status", count="exact")
            .eq("organization_id", organization_id)
            .in_("job_id", job_ids)
            .order("received_at", desc=True)
            .range(offset, offset + limit - 1)
        )
    else:
        query = (
            client.table("intake_events")
            .select("event_id, job_id, source, event_type, received_at, status", count="exact")
            .eq("organization_id", organization_id)
            .order("received_at", desc=True)
            .range(offset, offset + limit - 1)
        )

    result = await query.execute()

    events = [
        {
            "event_id": str(row["event_id"]),
            "job_id": str(row["job_id"]) if row.get("job_id") else None,
            "source": row.get("source", "acculynx"),
            "event_type": row.get("event_type"),
            "received_at": row.get("received_at"),
            "status": row.get("status"),
        }
        for row in (result.data or [])
    ]
    total = result.count or 0

    logger.debug(
        "list_events",
        extra={
            "organization_id": organization_id,
            "location_id": location_id,
            "total": total,
            "limit": limit,
            "offset": offset,
        },
    )

    return {"events": events, "total": total}
