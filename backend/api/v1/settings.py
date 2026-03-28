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

from fastapi import APIRouter, Response
from pydantic import BaseModel

router = APIRouter()


class CreateLocationRequest(BaseModel):
    name: str
    acculynx_api_key: str


class UpdateLocationRequest(BaseModel):
    name: str | None = None
    acculynx_api_key: str | None = None


@router.get("/settings/locations", summary="List user's registered locations")
async def list_locations() -> dict:
    """Returns locations with masked API keys. Placeholder."""
    # TODO: Query Supabase locations table filtered by authenticated user_id
    return {"locations": []}


@router.post("/settings/locations", status_code=201, summary="Register a new location")
async def create_location(body: CreateLocationRequest) -> dict:
    """Creates a new location with AccuLynx API key. Placeholder."""
    # TODO: Insert into Supabase locations table
    location_id = str(uuid4())
    return {
        "location_id": location_id,
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
