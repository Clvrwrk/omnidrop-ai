"""
OmniDrop AI — System Health Endpoint
GET /api/v1/health

NOT behind WorkOS auth — monitoring tools need unauthenticated access.
"""

import logging
import time
from datetime import datetime, timezone

from fastapi import APIRouter

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health", summary="System health check")
async def health_check() -> dict:
    """
    Checks Supabase, Redis, and Celery worker connectivity.
    Used by /dashboard admin view and external monitoring.
    """
    checks: dict = {}
    overall = "healthy"

    # Supabase check
    try:
        from backend.services.supabase_client import get_supabase_client

        start = time.monotonic()
        client = await get_supabase_client()
        await client.table("locations").select("location_id").limit(1).execute()
        latency = int((time.monotonic() - start) * 1000)
        checks["supabase"] = {"status": "ok", "latency_ms": latency}
    except Exception as exc:
        logger.error("Health check: Supabase error", extra={"error": str(exc)})
        checks["supabase"] = {"status": "error", "latency_ms": 0}
        overall = "degraded"

    # Redis check
    try:
        from backend.workers.celery_app import celery_app

        start = time.monotonic()
        celery_app.connection_or_acquire(block=True)
        latency = int((time.monotonic() - start) * 1000)
        checks["redis"] = {"status": "ok", "latency_ms": latency}
    except Exception as exc:
        logger.error("Health check: Redis error", extra={"error": str(exc)})
        checks["redis"] = {"status": "error", "latency_ms": 0}
        overall = "degraded"

    # Celery worker check
    try:
        from backend.workers.celery_app import celery_app

        inspect = celery_app.control.inspect()
        active = inspect.active() or {}
        active_count = sum(len(tasks) for tasks in active.values())
        # Queue depth via Redis LLEN
        with celery_app.connection_or_acquire() as conn:
            queue_depth = conn.default_channel.client.llen("celery") or 0
        checks["celery_workers"] = {
            "status": "ok" if active_count > 0 or queue_depth == 0 else "error",
            "active_count": active_count,
            "queue_depth": queue_depth,
        }
    except Exception as exc:
        logger.error("Health check: Celery error", extra={"error": str(exc)})
        checks["celery_workers"] = {
            "status": "error",
            "active_count": 0,
            "queue_depth": 0,
        }
        overall = "degraded"

    if all(c.get("status") == "error" for c in checks.values()):
        overall = "down"

    return {
        "status": overall,
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
