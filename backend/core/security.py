"""
OmniDrop AI — Webhook Security

Verifies HMAC-SHA256 signatures on events delivered by Hookdeck.

ARCHITECTURE NOTE:
  AccuLynx no longer POSTs directly to this endpoint.
  AccuLynx → Hookdeck (ACKs immediately) → [queue] → this FastAPI endpoint

  We verify the Hookdeck signing secret (HOOKDECK_SIGNING_SECRET), NOT the
  AccuLynx secret directly. Configure the same ACCULYNX_WEBHOOK_SECRET in your
  Hookdeck source settings so Hookdeck can validate AccuLynx before forwarding.

Hookdeck signing docs:
  https://hookdeck.com/docs/receive-webhooks#verify-webhook-signatures
"""

import hashlib
import hmac
import logging

from fastapi import HTTPException, Request, status

from backend.core.config import settings

logger = logging.getLogger(__name__)

# Hookdeck sends its signature in this header
HOOKDECK_SIGNATURE_HEADER = "X-Hookdeck-Signature"


async def verify_acculynx_signature(request: Request) -> None:
    """
    FastAPI dependency that verifies the Hookdeck HMAC-SHA256 event signature.

    Hookdeck signs the raw request body using HOOKDECK_SIGNING_SECRET and
    sends the digest in the X-Hookdeck-Signature header.

    TODO: Confirm the exact header name and signing format from the Hookdeck
          dashboard once your source is configured.
          Expected header format: "sha256=<hex_digest>"

    Raises:
        HTTPException 401: if the signature header is missing or does not match.
    """
    signature_header = request.headers.get(HOOKDECK_SIGNATURE_HEADER)

    if not signature_header:
        logger.warning("Webhook received without Hookdeck signature header — rejected")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing webhook signature",
        )

    # TODO: Implement once Hookdeck source is configured and signing format confirmed
    # raw_body = await request.body()
    # expected = hmac.new(
    #     settings.hookdeck_signing_secret.encode(),
    #     raw_body,
    #     hashlib.sha256,
    # ).hexdigest()
    # provided = signature_header.removeprefix("sha256=")
    # if not hmac.compare_digest(expected, provided):
    #     logger.warning("Hookdeck signature mismatch — rejected")
    #     raise HTTPException(
    #         status_code=status.HTTP_401_UNAUTHORIZED,
    #         detail="Invalid webhook signature",
    #     )

    raise NotImplementedError(
        "Hookdeck webhook signature verification not yet implemented. "
        "See TODO comments in backend/core/security.py"
    )
