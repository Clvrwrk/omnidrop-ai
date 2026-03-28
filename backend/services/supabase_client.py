"""
OmniDrop AI — Supabase Client

Provides a Supabase async client for database operations.
Uses the service role key for server-side operations (backend + Celery workers).
The service role key must NEVER be exposed to the frontend.
"""

from supabase import AsyncClient, acreate_client

from backend.core.config import get_settings

_client: AsyncClient | None = None


async def get_supabase_client() -> AsyncClient:
    """Returns a singleton Supabase async client using the service role key."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = await acreate_client(
            settings.supabase_url,
            settings.supabase_service_role_key,
        )
    return _client


async def get_organization_by_id(organization_id: str) -> dict | None:
    """Fetch an organization by its internal UUID. Returns None if not found."""
    client = await get_supabase_client()
    result = (
        await client.table("organizations")
        .select("*")
        .eq("organization_id", organization_id)
        .maybe_single()
        .execute()
    )
    return result.data


async def get_organization_by_workos_id(workos_org_id: str) -> dict | None:
    """Fetch an organization by its WorkOS organization ID. Returns None if not found."""
    client = await get_supabase_client()
    result = (
        await client.table("organizations")
        .select("*")
        .eq("workos_org_id", workos_org_id)
        .maybe_single()
        .execute()
    )
    return result.data


async def get_or_create_organization(workos_org_id: str, name: str) -> dict:
    """
    Return the organization for a WorkOS org ID, creating it if it doesn't exist.
    Used during auth callback / first login to ensure every user has an org row.
    """
    existing = await get_organization_by_workos_id(workos_org_id)
    if existing:
        return existing

    client = await get_supabase_client()
    result = (
        await client.table("organizations")
        .insert({"workos_org_id": workos_org_id, "name": name})
        .execute()
    )
    return result.data[0]


async def get_organization_id_for_location(location_id: str) -> str:
    """
    Resolve organization_id from a location_id.
    Used by Celery tasks when a webhook arrives with location_id but no organization_id.

    Raises:
        ValueError: If the location is not found or has no organization.
    """
    client = await get_supabase_client()
    result = (
        await client.table("locations")
        .select("organization_id")
        .eq("location_id", location_id)
        .single()
        .execute()
    )
    if not result.data or not result.data.get("organization_id"):
        raise ValueError(f"No organization found for location {location_id}")
    return result.data["organization_id"]


async def get_user_count_for_org(organization_id: str) -> int:
    """Return the number of distinct users (locations) in an organization."""
    client = await get_supabase_client()
    result = (
        await client.table("locations")
        .select("user_id", count="exact")
        .eq("organization_id", organization_id)
        .execute()
    )
    return result.count or 0


async def get_location_api_key(location_id: str) -> str:
    """
    Fetch the AccuLynx API key for a specific location from Supabase.

    This is the ONLY way to get an AccuLynx API key at task runtime.
    There is no global ACCULYNX_API_KEY in production.

    Raises:
        ValueError: If the location is not found or has no API key.
    """
    client = await get_supabase_client()
    result = (
        await client.table("locations")
        .select("acculynx_api_key")
        .eq("location_id", location_id)
        .single()
        .execute()
    )
    if not result.data or not result.data.get("acculynx_api_key"):
        raise ValueError(f"No API key found for location {location_id}")
    return result.data["acculynx_api_key"]
