"""
OmniDrop AI — Organization Endpoints
GET /api/v1/organizations/me          — lazy-provision org from WorkOS session
GET /api/v1/organizations/me/users    — list users in the authenticated org

Both endpoints extract organization context exclusively from WorkOS session headers
(x-workos-org-id / x-workos-user-id). The org row is created on first access if it
does not yet exist (lazy provisioning pattern).

Response shapes match docs/api-contracts.md §1.2.
"""

import logging

from fastapi import APIRouter, HTTPException, Request

from backend.services.supabase_client import (
    get_or_create_organization,
    get_or_create_organization_by_user_id,
    get_supabase_client,
)

router = APIRouter()
logger = logging.getLogger(__name__)


async def _resolve_org(request: Request) -> dict:
    """
    Resolve (and lazily provision) the org row from WorkOS session headers.

    Priority:
      1. x-workos-org-id  — standard WorkOS SSO / multi-member org
      2. x-workos-user-id — direct email login; creates a personal org keyed on user_id
      3. 401 if neither header is present
    """
    workos_org_id = request.headers.get("x-workos-org-id")
    workos_user_id = request.headers.get("x-workos-user-id")
    workos_org_name = request.headers.get("x-workos-org-name", "My Organization")

    if workos_org_id:
        return await get_or_create_organization(workos_org_id, workos_org_name)
    if workos_user_id:
        return await get_or_create_organization_by_user_id(workos_user_id)
    raise HTTPException(status_code=401, detail="Missing authentication context.")


@router.get(
    "/organizations/me",
    summary="Get (or create) the authenticated user's organization",
)
async def get_my_organization(request: Request) -> dict:
    """
    Returns the organization for the authenticated user.
    Creates the org row on first access (lazy provisioning from WorkOS session).

    Response shape: docs/api-contracts.md §1.2 GET /api/v1/organizations/me
    """
    org = await _resolve_org(request)

    return {
        "organization_id": str(org["organization_id"]),
        "workos_org_id": org.get("workos_org_id"),
        "name": org.get("name"),
        "max_users": org.get("max_users", 5),
        "created_at": org.get("created_at"),
    }


@router.get(
    "/organizations/me/users",
    summary="List users in the authenticated organization",
)
async def list_org_users(request: Request) -> dict:
    """
    Returns the seat count and user list for the authenticated org.
    Users are derived from the locations table (one location row = one user seat).

    Used by /settings to show usage vs max_users.
    Response shape: docs/api-contracts.md §1.2 GET /api/v1/organizations/me/users
    """
    org = await _resolve_org(request)
    organization_id = str(org["organization_id"])

    client = await get_supabase_client()

    # Fetch all locations for this org — each represents one user seat
    result = await (
        client.table("locations")
        .select("user_id, name, created_at")
        .eq("organization_id", organization_id)
        .execute()
    )

    rows = result.data or []
    user_count = len(rows)

    # Map location rows to the user shape the API contract expects
    users = [
        {
            "user_id": row.get("user_id"),
            "name": row.get("name"),
            "created_at": row.get("created_at"),
        }
        for row in rows
    ]

    logger.debug(
        "list_org_users",
        extra={"organization_id": organization_id, "user_count": user_count},
    )

    return {
        "organization_id": organization_id,
        "max_users": org.get("max_users", 5),
        "user_count": user_count,
        "users": users,
    }
