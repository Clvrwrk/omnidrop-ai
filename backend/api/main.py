"""
OmniDrop AI — FastAPI Application Entrypoint
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)

from backend.api.v1 import (
    analytics,
    documents,
    events,
    health,
    jobs,
    organizations,
    search,
    settings,
    triage,
    webhooks,
)
from backend.core.config import get_settings
from backend.core.logging import configure_logging
from backend.core.sentry import configure_sentry

# Sentry must be initialized before the FastAPI app is created
configure_sentry()
configure_logging()

_settings = get_settings()

app = FastAPI(
    title="OmniDrop AI API",
    version="0.1.0",
    docs_url="/docs" if _settings.app_env != "production" else None,
    redoc_url="/redoc" if _settings.app_env != "production" else None,
)

_cors = _settings.cors_origins
logger.info("CORS origins: %s (APP_ENV=%s)", _cors, _settings.app_env)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Webhook endpoint — authenticated by Hookdeck HMAC, not WorkOS
app.include_router(webhooks.router, prefix="/api/v1", tags=["webhooks"])

# API contract endpoints — all protected by WorkOS auth (TODO: add auth dependency)
app.include_router(organizations.router, prefix="/api/v1", tags=["organizations"])
app.include_router(documents.router, prefix="/api/v1", tags=["documents"])
app.include_router(jobs.router, prefix="/api/v1", tags=["jobs"])
app.include_router(events.router, prefix="/api/v1", tags=["events"])
app.include_router(analytics.router, prefix="/api/v1", tags=["analytics"])
app.include_router(search.router, prefix="/api/v1", tags=["search"])
app.include_router(triage.router, prefix="/api/v1", tags=["triage"])
app.include_router(settings.router, prefix="/api/v1", tags=["settings"])

# Health check — NOT behind auth (monitoring tools need unauthenticated access)
app.include_router(health.router, prefix="/api/v1", tags=["health"])
