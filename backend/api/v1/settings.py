"""
OmniDrop AI — Settings / Location Management Endpoints

T2-05 (this session):
  GET  /api/v1/settings/locations          — list org's locations (api_key_last4 only)
  POST /api/v1/settings/locations          — register a new location + store API key

T2-06 (next session):
  PATCH /api/v1/settings/locations/{id}                    — update name / rotate key
  PATCH /api/v1/settings/locations/{id}/notifications      — save Slack webhook URL
  POST  /api/v1/settings/locations/{id}/notifications/test — send test message

T2-07 (next session):
  POST /api/v1/settings/pricing-contracts  — parse CSV/PDF, insert pricing_contracts rows

SECURITY INVARIANT: acculynx_api_key is NEVER returned in any response.
Only the last 4 characters (api_key_last4) are exposed for display purposes.
This is enforced by the _mask_key() helper — always call it before building a response.
"""

import logging
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, field_validator

from backend.services.supabase_client import (
    get_or_create_organization,
    get_or_create_organization_by_user_id,
    get_organization_by_id,
    get_supabase_client,
    get_user_count_for_org,
)

router = APIRouter()
logger = logging.getLogger(__name__)


# ── Security helper ────────────────────────────────────────────────────────────

def _mask_key(api_key: str) -> str:
    """Return only the last 4 characters of an API key. Never return the full key."""
    if not api_key:
        return "****"
    return api_key[-4:] if len(api_key) >= 4 else "****"


# ── Auth helper ────────────────────────────────────────────────────────────────

async def _resolve_org(request: Request) -> dict:
    """
    Resolve the org row from WorkOS session headers.
    Raises 401 if no auth context is present.
    """
    workos_org_id = request.headers.get("x-workos-org-id")
    workos_user_id = request.headers.get("x-workos-user-id")
    workos_org_name = request.headers.get("x-workos-org-name", "My Organization")

    if workos_org_id:
        return await get_or_create_organization(workos_org_id, workos_org_name)
    if workos_user_id:
        return await get_or_create_organization_by_user_id(workos_user_id)
    raise HTTPException(status_code=401, detail="Missing authentication context.")


# ── Pydantic request models ────────────────────────────────────────────────────

class CreateLocationRequest(BaseModel):
    name: str
    acculynx_api_key: str
    organization_id: str  # validated against session-derived org below

    @field_validator("acculynx_api_key")
    @classmethod
    def key_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("acculynx_api_key must not be empty.")
        return v.strip()

    @field_validator("name")
    @classmethod
    def name_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("name must not be empty.")
        return v.strip()


class UpdateLocationRequest(BaseModel):
    name: str | None = None
    acculynx_api_key: str | None = None

    @field_validator("acculynx_api_key")
    @classmethod
    def key_must_not_be_empty_if_provided(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("acculynx_api_key must not be empty when provided.")
        return v.strip() if v else v


# ── T2-05: GET /api/v1/settings/locations ─────────────────────────────────────

@router.get(
    "/settings/locations",
    summary="List locations for the authenticated organization",
)
async def list_locations(
    request: Request,
    organization_id: str | None = None,
) -> dict:
    """
    Returns all locations belonging to the authenticated organization.
    api_key_last4 only — full acculynx_api_key is never returned.

    The organization_id query param is accepted per the API contract for
    filtering, but auth is always resolved from the WorkOS session headers.
    The session-derived org is used as the authoritative scope.
    """
    org = await _resolve_org(request)
    session_org_id = str(org["organization_id"])

    # If a caller passes organization_id, it must match the session org.
    # This prevents cross-tenant enumeration.
    if organization_id and organization_id != session_org_id:
        raise HTTPException(
            status_code=403,
            detail="organization_id does not match the authenticated session.",
        )

    client = await get_supabase_client()
    result = await (
        client.table("locations")
        .select(
            "location_id, organization_id, name, acculynx_api_key, "
            "connection_status, created_at, updated_at"
        )
        .eq("organization_id", session_org_id)
        .order("created_at", desc=False)
        .execute()
    )

    locations = [
        {
            "location_id": str(row["location_id"]),
            "organization_id": str(row["organization_id"]),
            "name": row["name"],
            # SECURITY: strip full key — expose last 4 chars only
            "api_key_last4": _mask_key(row.get("acculynx_api_key", "")),
            "connection_status": row.get("connection_status", "untested"),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }
        for row in (result.data or [])
    ]

    logger.debug(
        "list_locations",
        extra={"organization_id": session_org_id, "count": len(locations)},
    )

    return {"locations": locations}


# ── T2-05: POST /api/v1/settings/locations ────────────────────────────────────

@router.post(
    "/settings/locations",
    status_code=201,
    summary="Register a new location with its AccuLynx API key",
)
async def create_location(
    request: Request,
    body: CreateLocationRequest,
) -> dict:
    """
    Creates a new location row, storing the full acculynx_api_key in Supabase.
    Returns api_key_last4 only — full key is never echoed back.

    Auth guards:
      1. Session must be authenticated (401).
      2. body.organization_id must match the session-derived org (403).
      3. Org must not exceed max_users seat limit (403).
    """
    org = await _resolve_org(request)
    session_org_id = str(org["organization_id"])

    # Guard: body org must match session org
    if body.organization_id != session_org_id:
        raise HTTPException(
            status_code=403,
            detail="organization_id does not match the authenticated session.",
        )

    # Guard: seat limit check
    user_count = await get_user_count_for_org(session_org_id)
    max_users = org.get("max_users", 5)
    if user_count >= max_users:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Organization has reached its location limit ({max_users}). "
                "Upgrade your plan to add more locations."
            ),
        )

    client = await get_supabase_client()

    # Derive workos_user_id for the user_id column (locations.user_id is TEXT NOT NULL)
    workos_user_id = (
        request.headers.get("x-workos-user-id")
        or request.headers.get("x-workos-org-id")
        or "unknown"
    )

    location_id = str(uuid4())
    try:
        result = await client.table("locations").insert({
            "location_id": location_id,
            "organization_id": session_org_id,
            "name": body.name,
            "acculynx_api_key": body.acculynx_api_key,   # stored in full, never returned
            "connection_status": "untested",
            "user_id": workos_user_id,
        }).execute()
    except Exception as exc:
        logger.error(
            "create_location: insert failed",
            extra={"organization_id": session_org_id, "error": str(exc)},
        )
        raise HTTPException(status_code=500, detail="Failed to create location. Please retry.")

    row = result.data[0] if result.data else {}

    logger.info(
        "create_location: location created",
        extra={
            "location_id": location_id,
            "organization_id": session_org_id,
            "name": body.name,
        },
    )

    return {
        "location_id": str(row.get("location_id", location_id)),
        "organization_id": session_org_id,
        "name": row.get("name", body.name),
        # SECURITY: only last 4 chars of the key the caller just submitted
        "api_key_last4": _mask_key(body.acculynx_api_key),
        "connection_status": row.get("connection_status", "untested"),
        "created_at": row.get("created_at", datetime.now(timezone.utc).isoformat()),
    }


# ── T2-06 stubs (implemented next session) ────────────────────────────────────

@router.patch(
    "/settings/locations/{location_id}",
    summary="Update location name or rotate API key  [T2-06]",
)
async def update_location(
    location_id: str,
    body: UpdateLocationRequest,
    request: Request,
) -> dict:
    """Stub — implemented in T2-06."""
    raise HTTPException(status_code=501, detail="Not yet implemented. Coming in T2-06.")


@router.delete(
    "/settings/locations/{location_id}",
    status_code=204,
    summary="Remove a location  [T2-06]",
)
async def delete_location(location_id: str, request: Request) -> Response:
    """Stub — implemented in T2-06."""
    raise HTTPException(status_code=501, detail="Not yet implemented. Coming in T2-06.")


@router.patch(
    "/settings/locations/{location_id}/notifications",
    summary="Save Slack webhook URL for a location  [T2-06]",
)
async def update_notifications(
    location_id: str,
    request: Request,
) -> dict:
    """Stub — implemented in T2-06."""
    raise HTTPException(status_code=501, detail="Not yet implemented. Coming in T2-06.")


@router.post(
    "/settings/locations/{location_id}/notifications/test",
    summary="Send a test Slack notification  [T2-06]",
)
async def test_notification(
    location_id: str,
    request: Request,
) -> dict:
    """Stub — implemented in T2-06."""
    raise HTTPException(status_code=501, detail="Not yet implemented. Coming in T2-06.")


# ── T2-07 stub (implemented next session) ─────────────────────────────────────

@router.post(
    "/settings/pricing-contracts",
    status_code=201,
    summary="Upload a pricing contract file  [T2-07]",
)
async def upload_pricing_contract(
    request: Request,
    file: UploadFile = File(...),
) -> dict:
    """Stub — implemented in T2-07."""
    raise HTTPException(status_code=501, detail="Not yet implemented. Coming in T2-07.")
