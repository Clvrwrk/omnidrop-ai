"""
OmniDrop AI — Organization Endpoints
GET /api/v1/organizations/me          — get or create org from WorkOS session
GET /api/v1/organizations/me/users    — list users in the authenticated org
"""

import logging

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()
logger = logging.getLogger(__name__)


async def _resolve_org(request: Request) -> dict:
    """
    Resolve the org row from request headers.
    Accepts x-workos-org-id (WorkOS org) or falls back to x-workos-user-id
    (direct signup without a WorkOS org — creates a personal org on first call).
    """
    from backend.services.supabase_client import (
        get_or_create_organization,
        get_or_create_organization_by_user_id,
    )

    workos_org_id = request.headers.get("x-workos-org-id")
    workos_user_id = request.headers.get("x-workos-user-id")
    workos_org_name = request.headers.get("x-workos-org-name", "My Organization")

    if workos_org_id:
        return await get_or_create_organization(workos_org_id, workos_org_name)
    if workos_user_id:
        return await get_or_create_organization_by_user_id(workos_user_id)
    raise HTTPException(status_code=401, detail="Missing authentication context")


@router.get(
    "/organizations/me",
    summary="Get current user's organization",
)
async def get_my_organization(request: Request) -> dict:
    """
    Returns the organization for the authenticated user.
    Creates the org row on first access (lazy provisioning).
    Accepts WorkOS org ID or falls back to WorkOS user ID for direct signups.
    """
    return await _resolve_org(request)


@router.get(
    "/organizations/me/users",
    summary="List users in the current organization",
)
async def list_org_users(request: Request) -> dict:
    """
    Returns the count and list of users (via locations) in the authenticated org.
    Used by /settings to show seat usage vs max_users.
    """
    org = await _resolve_org(request)

    from backend.services.supabase_client import (
        get_supabase_client,
        get_user_count_for_org,
    )

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
