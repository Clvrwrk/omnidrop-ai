"""
OmniDrop AI — Sentry Initialization (FastAPI)

Must be called once at application startup, before any routes are registered.
Call configure_sentry() at the top of backend/api/main.py.

Key config: failed_request_status_codes includes 429 to capture AccuLynx
rate-limit errors that bubble up through the backend.
"""

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from backend.core.config import settings


def configure_sentry() -> None:
    """Initialize Sentry for the FastAPI backend."""
    if not settings.sentry_python_dsn:
        return  # Sentry disabled if DSN not configured (e.g., local dev)

    sentry_sdk.init(
        dsn=settings.sentry_python_dsn,
        environment=settings.app_env,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        integrations=[
            # Capture 429 (AccuLynx rate limits) in addition to default 5xx
            StarletteIntegration(
                failed_request_status_codes={429, 500, 502, 503}
            ),
            FastApiIntegration(
                failed_request_status_codes={429, 500, 502, 503}
            ),
        ],
        # Don't send PII (user emails, IPs) by default
        send_default_pii=False,
    )
