"""
OmniDrop AI — Organization Endpoints
GET /api/v1/organizations/me          — get or create org from WorkOS session
GET /api/v1/organizations/me/users    — list users in the authenticated org
"""

import logging

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get(
    "/organizations/me",
    summary="Get current user's organization",
)
async def get_my_organization(request: Request) -> dict:
    """
    Returns the organization for the authenticated user.
    Creates the org row on first access (lazy provisioning via WorkOS org ID).

    Requires WorkOS auth — the session must contain org_id and org_name.
    """
    # TODO: Extract from real WorkOS auth session
    workos_org_id = request.headers.get("x-workos-org-id")
    workos_org_name = request.headers.get("x-workos-org-name", "My Organization")

    if not workos_org_id:
        raise HTTPException(status_code=401, detail="Missing organization context")

    from backend.services.supabase_client import get_or_create_organization

    org = await get_or_create_organization(workos_org_id, workos_org_name)
    return org


@router.get(
    "/organizations/me/users",
    summary="List users in the current organization",
)
async def list_org_users(request: Request) -> dict:
    """
    Returns the count and list of users (via locations) in the authenticated org.
    Used by /settings to show seat usage vs max_users.
    """
    workos_org_id = request.headers.get("x-workos-org-id")
    if not workos_org_id:
        raise HTTPException(status_code=401, detail="Missing organization context")

    from backend.services.supabase_client import (
        get_organization_by_workos_id,
        get_supabase_client,
        get_user_count_for_org,
    )

    org = await get_organization_by_workos_id(workos_org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    organization_id = org["organization_id"]
    user_count = await get_user_count_for_org(organization_id)

    # Fetch distinct users with their locations
    client = await get_supabase_client()
    result = (
        await client.table("locations")
        .select("user_id, name, created_at")
        .eq("organization_id", organization_id)
        .execute()
    )

    return {
        "organization_id": organization_id,
        "max_users": org.get("max_users", 5),
        "user_count": user_count,
        "users": result.data or [],
    }
