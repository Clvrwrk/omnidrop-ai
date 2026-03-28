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
