"""
OmniDrop AI — FastAPI Application Entrypoint
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.v1 import webhooks
from backend.core.config import settings
from backend.core.logging import configure_logging
from backend.core.sentry import configure_sentry

# Sentry must be initialized before the FastAPI app is created
configure_sentry()
configure_logging()

app = FastAPI(
    title="OmniDrop AI API",
    version="0.1.0",
    docs_url="/docs" if settings.app_env != "production" else None,
    redoc_url="/redoc" if settings.app_env != "production" else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(webhooks.router, prefix="/api/v1", tags=["webhooks"])


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok", "env": settings.app_env}
