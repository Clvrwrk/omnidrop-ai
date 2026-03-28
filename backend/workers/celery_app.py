"""
OmniDrop AI — Celery Application Configuration

Creates and configures the Celery app instance used by both:
  - The FastAPI backend (to dispatch tasks via .delay() / .apply_async())
  - The Celery worker process (to execute tasks)

Both import from this module to share the same app instance.

Redis is the broker AND result backend, provisioned on Render.com as a
Key Value service. Locally, Redis runs via Docker Compose.

Start the worker locally:
  celery -A backend.workers.celery_app worker --loglevel=info --concurrency=4

Monitor with Flower (optional):
  celery -A backend.workers.celery_app flower
"""

import os

from celery import Celery

# Redis URL — from Render Key Value service in production, Docker Compose locally
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", CELERY_BROKER_URL)

celery_app = Celery(
    "omni_intake",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=["backend.workers.intake_tasks"],
)

celery_app.conf.update(
    # Serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Timezone
    timezone="UTC",
    enable_utc=True,
    # Retry behavior: tasks are re-queued on worker crash (acks late)
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Result expiry: keep results for 24 hours
    result_expires=86400,
    # Concurrency — override at runtime with --concurrency flag
    worker_prefetch_multiplier=1,
)
