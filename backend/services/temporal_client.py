"""
OmniDrop AI — Temporal Client Factory

Provides an async Temporal client connected to the configured Temporal server.
Used by the webhook endpoint to start workflows.
"""

from temporalio.client import Client

from backend.core.config import settings


async def get_temporal_client() -> Client:
    """
    Returns a connected Temporal client.
    TODO: Add TLS configuration for non-local environments.
    """
    return await Client.connect(
        settings.temporal_host,
        namespace=settings.temporal_namespace,
    )
