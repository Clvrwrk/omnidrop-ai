"""
OmniDrop AI — Supabase Client

Provides a Supabase async client for database operations.
Uses the service role key for server-side operations.
"""

from supabase import AsyncClient, acreate_client

from backend.core.config import settings

_client: AsyncClient | None = None


async def get_supabase_client() -> AsyncClient:
    """
    Returns a singleton Supabase async client.
    TODO: Add connection pooling for high-volume webhook processing.
    """
    global _client
    if _client is None:
        _client = await acreate_client(
            settings.supabase_url,
            settings.supabase_service_role_key,
        )
    return _client
