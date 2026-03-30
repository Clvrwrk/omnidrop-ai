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
    return result.data if result else None


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
    return result.data if result else None


async def get_or_create_organization_by_user_id(workos_user_id: str) -> dict:
    """
    Find or create an org keyed on a WorkOS user ID.
    Used when a user signs up without a WorkOS org (direct email login).
    The synthetic workos_org_id is prefixed with 'user_' to distinguish it.
    """
    synthetic_id = f"user_{workos_user_id}"
    existing = await get_organization_by_workos_id(synthetic_id)
    if existing:
        return existing

    client = await get_supabase_client()
    result = (
        await client.table("organizations")
        .insert({"workos_org_id": synthetic_id, "name": "My Organization"})
        .execute()
    )
    return result.data[0]


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


async def get_correction_examples(
    organization_id: str,
    vendor_name: str | None = None,
    limit: int = 5,
) -> list[dict]:
    """
    Fetch recent HITL correction examples for few-shot prompting.

    Prioritises vendor-specific examples (same vendor_name) when vendor_name
    is supplied. Falls back to org-level examples if fewer than `limit` vendor
    examples exist, so Claude always gets the most relevant context available.

    Returns list of dicts with keys:
        vendor_name, corrected_extraction, correction_summary, created_at
    Only rows that have corrected_extraction populated are returned (i.e. rows
    written after migration 00007 — older confirm-only rows are excluded).
    """
    client = await get_supabase_client()

    results: list[dict] = []

    # 1. Vendor-specific examples first (if vendor_name known)
    if vendor_name:
        r = await (
            client.table("context_reference_examples")
            .select("vendor_name, corrected_extraction, correction_summary, created_at")
            .eq("organization_id", organization_id)
            .eq("vendor_name", vendor_name)
            .not_.is_("corrected_extraction", "null")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        results = r.data or []

    # 2. Top up with org-level examples if we don't have enough
    if len(results) < limit:
        remaining = limit - len(results)
        existing_vendors = {r["vendor_name"] for r in results if r.get("vendor_name")}
        q = (
            client.table("context_reference_examples")
            .select("vendor_name, corrected_extraction, correction_summary, created_at")
            .eq("organization_id", organization_id)
            .not_.is_("corrected_extraction", "null")
            .order("created_at", desc=True)
            .limit(remaining + len(existing_vendors))  # fetch extra to filter dupes
        )
        r2 = await q.execute()
        for row in (r2.data or []):
            if row.get("vendor_name") not in existing_vendors:
                results.append(row)
            if len(results) >= limit:
                break

    return results


async def get_system_config(key: str) -> dict | None:
    """Fetch a config value from the system_config table by key."""
    client = await get_supabase_client()
    result = (
        await client.table("system_config")
        .select("value")
        .eq("key", key)
        .maybe_single()
        .execute()
    )
    if result and result.data:
        return result.data["value"]
    return None
