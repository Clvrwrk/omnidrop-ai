"""
OmniDrop AI — Intake Events Endpoint
GET /api/v1/events
"""

from fastapi import APIRouter, Query

router = APIRouter()


@router.get("/events", summary="List recent webhook events")
async def list_events(
    limit: int = Query(default=25, le=100),
    offset: int = Query(default=0, ge=0),
    location_id: str | None = Query(default=None),
) -> dict:
    """Returns recent intake events. Placeholder until Supabase queries are wired."""
    # TODO: Query Supabase intake_events table
    return {
        "events": [],
        "total": 0,
    }
