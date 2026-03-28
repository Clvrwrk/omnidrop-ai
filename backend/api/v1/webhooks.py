"""
OmniDrop AI — AccuLynx Webhook Endpoint

ARCHITECTURE RULE — This endpoint must do EXACTLY FOUR things:
  1. Verify the Hookdeck HMAC-SHA256 signature     -> reject with 401 if invalid
  2. Validate the payload shape with Pydantic       -> reject with 422 if invalid
  3. Dispatch a Celery task and return 200 OK       -> immediately, no waiting
  4. Return 200 OK

It must NEVER:
  - Perform database writes
  - Make AI or Unstructured.io calls
  - Make outbound HTTP requests
  - Block on any I/O
"""

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, Response

from backend.core.security import verify_hookdeck_signature
from backend.workers.intake_tasks import process_document
from shared.models.acculynx import AccuLynxWebhookPayload

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/webhooks/acculynx",
    status_code=200,
    summary="Receive AccuLynx webhook via Hookdeck",
    description=(
        "Validates Hookdeck HMAC signature, dispatches async Celery task, "
        "and immediately returns 200. All document processing is async."
    ),
)
async def receive_acculynx_webhook(
    request: Request,
    payload: AccuLynxWebhookPayload,
    _: None = Depends(verify_hookdeck_signature),
) -> Response:
    """
    Step 1: Hookdeck signature verified by dependency (401 if invalid).
    Step 2: Payload validated by Pydantic (422 if malformed).
    Step 3: Celery task dispatched — non-blocking.
    Step 4: Return 200 immediately.
    """
    job_payload = {
        "job_id": payload.event.job_id,
        "location_id": payload.event.location_id,
        "event_type": payload.event.event_type,
        "document_id": payload.event.document_id,
        "document_url": payload.event.document_url,
        "raw_payload": json.dumps(payload.model_dump(), default=str),
        "received_at": datetime.now(timezone.utc).isoformat(),
    }

    process_document.delay(job_payload)

    logger.info(
        "Webhook dispatched to Celery",
        extra={
            "job_id": job_payload["job_id"],
            "location_id": job_payload["location_id"],
            "event_type": job_payload["event_type"],
        },
    )

    return Response(status_code=200)
