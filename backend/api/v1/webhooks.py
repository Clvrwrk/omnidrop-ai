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

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from backend.core.security import verify_hookdeck_signature
from backend.services.supabase_client import get_or_create_organization
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
    Step 3: Freemium quota check (402 if exceeded) — skipped for Hookdeck-only calls.
    Step 4: Celery task dispatched — non-blocking.
    Step 5: Return 200 immediately.
    """
    # Freemium quota check — WorkOS injects x-workos-org-id for user sessions.
    # Hookdeck-originated calls will not have this header; skip quota check for those.
    workos_org_id = request.headers.get("x-workos-org-id")
    workos_org_name = request.headers.get("x-workos-org-name", "")
    org: dict = {}
    if workos_org_id:
        org = await get_or_create_organization(workos_org_id, workos_org_name)
        if org.get("documents_processed", 0) >= org.get("max_documents", 500):
            raise HTTPException(status_code=402, detail="Document quota reached. Upgrade to continue.")

    job_payload = {
        "job_id": payload.event.job_id,
        "location_id": payload.event.location_id,
        "organization_id": org.get("organization_id") if workos_org_id else None,
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
