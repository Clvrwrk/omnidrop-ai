"""
OmniDrop AI — Settings / Location Management Endpoints
GET    /api/v1/settings/locations
POST   /api/v1/settings/locations
PATCH  /api/v1/settings/locations/{location_id}
DELETE /api/v1/settings/locations/{location_id}

SECURITY: acculynx_api_key is NEVER returned in full — only last 4 chars.
"""

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

router = APIRouter()


class CreateLocationRequest(BaseModel):
    name: str
    acculynx_api_key: str
    organization_id: str


class UpdateLocationRequest(BaseModel):
    name: str | None = None
    acculynx_api_key: str | None = None


@router.get("/settings/locations", summary="List user's registered locations")
async def list_locations(organization_id: str | None = None) -> dict:
    """Returns locations with masked API keys. Filtered by organization_id when provided. Placeholder."""
    # TODO: Query Supabase locations table filtered by organization_id and/or authenticated user_id
    return {"locations": []}


@router.post("/settings/locations", status_code=201, summary="Register a new location")
async def create_location(body: CreateLocationRequest) -> dict:
    """Creates a new location with AccuLynx API key, scoped to an organization."""
    from backend.services.supabase_client import get_organization_by_id, get_user_count_for_org

    org = await get_organization_by_id(body.organization_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    user_count = await get_user_count_for_org(body.organization_id)
    max_users = org.get("max_users", 5)
    if user_count >= max_users:
        raise HTTPException(
            status_code=403,
            detail=f"Organization has reached its user limit ({max_users})",
        )

    # TODO: Insert into Supabase locations table with organization_id
    location_id = str(uuid4())
    return {
        "location_id": location_id,
        "organization_id": body.organization_id,
        "name": body.name,
        "api_key_last4": body.acculynx_api_key[-4:],
        "connection_status": "untested",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


@router.patch("/settings/locations/{location_id}", summary="Update location or rotate key")
async def update_location(location_id: str, body: UpdateLocationRequest) -> dict:
    """Updates location name or API key. Placeholder."""
    # TODO: Update Supabase locations table
    return {
        "location_id": location_id,
        "name": body.name or "",
        "api_key_last4": body.acculynx_api_key[-4:] if body.acculynx_api_key else "****",
        "connection_status": "untested",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.delete(
    "/settings/locations/{location_id}",
    status_code=204,
    summary="Remove a location",
)
async def delete_location(location_id: str) -> Response:
    """Deletes location. Fails 409 if unprocessed jobs exist. Placeholder."""
    # TODO: Check for unprocessed jobs, delete from Supabase
    return Response(status_code=204)
