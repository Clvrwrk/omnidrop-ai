"""
OmniDrop AI — Settings / Location Management Endpoints

T2-05 (done):
  GET  /api/v1/settings/locations          — list org's locations (api_key_last4 only)
  POST /api/v1/settings/locations          — register a new location + store API key

T2-06 (this session):
  PATCH  /api/v1/settings/locations/{id}                    — update name / rotate key
  DELETE /api/v1/settings/locations/{id}                    — remove location (409 guard)
  PATCH  /api/v1/settings/locations/{id}/notifications      — save Slack webhook URL
  POST   /api/v1/settings/locations/{id}/notifications/test — send test message

T2-07 (next session):
  POST /api/v1/settings/pricing-contracts  — parse CSV/PDF, insert pricing_contracts rows

SECURITY INVARIANT: acculynx_api_key is NEVER returned in any response.
Only the last 4 characters (api_key_last4) are exposed for display purposes.
This is enforced by the _mask_key() helper — always call it before building a response.

NOTIFICATION INVARIANT: Never hardcode Slack logic directly. Always call
get_notification_adapter(channel_config) from notification_service — this is the
channel-agnostic adapter pattern required by CLAUDE.md.
"""

import logging
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, field_validator

from backend.services.supabase_client import (
    get_or_create_organization,
    get_or_create_organization_by_user_id,
    get_supabase_client,
    get_user_count_for_org,
)

router = APIRouter()
logger = logging.getLogger(__name__)


# ── Security helper ────────────────────────────────────────────────────────────

def _mask_key(api_key: str) -> str:
    """Return only the last 4 characters of an API key. Never return the full key."""
    if not api_key:
        return "****"
    return api_key[-4:] if len(api_key) >= 4 else "****"


# ── Auth helper ────────────────────────────────────────────────────────────────

async def _resolve_org(request: Request) -> dict:
    """
    Resolve the org row from WorkOS session headers.
    Raises 401 if no auth context is present.
    """
    workos_org_id = request.headers.get("x-workos-org-id")
    workos_user_id = request.headers.get("x-workos-user-id")
    workos_org_name = request.headers.get("x-workos-org-name", "My Organization")

    if workos_org_id:
        return await get_or_create_organization(workos_org_id, workos_org_name)
    if workos_user_id:
        return await get_or_create_organization_by_user_id(workos_user_id)
    raise HTTPException(status_code=401, detail="Missing authentication context.")


# ── Pydantic request models ────────────────────────────────────────────────────

class CreateLocationRequest(BaseModel):
    name: str
    acculynx_api_key: str
    organization_id: str  # validated against session-derived org below

    @field_validator("acculynx_api_key")
    @classmethod
    def key_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("acculynx_api_key must not be empty.")
        return v.strip()

    @field_validator("name")
    @classmethod
    def name_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("name must not be empty.")
        return v.strip()


class UpdateLocationRequest(BaseModel):
    name: str | None = None
    acculynx_api_key: str | None = None

    @field_validator("acculynx_api_key")
    @classmethod
    def key_must_not_be_empty_if_provided(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("acculynx_api_key must not be empty when provided.")
        return v.strip() if v else v


# ── T2-05: GET /api/v1/settings/locations ─────────────────────────────────────

@router.get(
    "/settings/locations",
    summary="List locations for the authenticated organization",
)
async def list_locations(
    request: Request,
    organization_id: str | None = None,
) -> dict:
    """
    Returns all locations belonging to the authenticated organization.
    api_key_last4 only — full acculynx_api_key is never returned.

    The organization_id query param is accepted per the API contract for
    filtering, but auth is always resolved from the WorkOS session headers.
    The session-derived org is used as the authoritative scope.
    """
    org = await _resolve_org(request)
    session_org_id = str(org["organization_id"])

    # If a caller passes organization_id, it must match the session org.
    # This prevents cross-tenant enumeration.
    if organization_id and organization_id != session_org_id:
        raise HTTPException(
            status_code=403,
            detail="organization_id does not match the authenticated session.",
        )

    client = await get_supabase_client()
    result = await (
        client.table("locations")
        .select(
            "location_id, organization_id, name, acculynx_api_key, "
            "connection_status, created_at, updated_at"
        )
        .eq("organization_id", session_org_id)
        .order("created_at", desc=False)
        .execute()
    )

    locations = [
        {
            "location_id": str(row["location_id"]),
            "organization_id": str(row["organization_id"]),
            "name": row["name"],
            # SECURITY: strip full key — expose last 4 chars only
            "api_key_last4": _mask_key(row.get("acculynx_api_key", "")),
            "connection_status": row.get("connection_status", "untested"),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }
        for row in (result.data or [])
    ]

    logger.debug(
        "list_locations",
        extra={"organization_id": session_org_id, "count": len(locations)},
    )

    return {"locations": locations}


# ── T2-05: POST /api/v1/settings/locations ────────────────────────────────────

@router.post(
    "/settings/locations",
    status_code=201,
    summary="Register a new location with its AccuLynx API key",
)
async def create_location(
    request: Request,
    body: CreateLocationRequest,
) -> dict:
    """
    Creates a new location row, storing the full acculynx_api_key in Supabase.
    Returns api_key_last4 only — full key is never echoed back.

    Auth guards:
      1. Session must be authenticated (401).
      2. body.organization_id must match the session-derived org (403).
      3. Org must not exceed max_users seat limit (403).
    """
    org = await _resolve_org(request)
    session_org_id = str(org["organization_id"])

    # Guard: body org must match session org
    if body.organization_id != session_org_id:
        raise HTTPException(
            status_code=403,
            detail="organization_id does not match the authenticated session.",
        )

    # Guard: seat limit check
    user_count = await get_user_count_for_org(session_org_id)
    max_users = org.get("max_users", 5)
    if user_count >= max_users:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Organization has reached its location limit ({max_users}). "
                "Upgrade your plan to add more locations."
            ),
        )

    client = await get_supabase_client()

    # Derive workos_user_id for the user_id column (locations.user_id is TEXT NOT NULL)
    workos_user_id = (
        request.headers.get("x-workos-user-id")
        or request.headers.get("x-workos-org-id")
        or "unknown"
    )

    location_id = str(uuid4())
    try:
        result = await client.table("locations").insert({
            "location_id": location_id,
            "organization_id": session_org_id,
            "name": body.name,
            "acculynx_api_key": body.acculynx_api_key,   # stored in full, never returned
            "connection_status": "untested",
            "user_id": workos_user_id,
        }).execute()
    except Exception as exc:
        logger.error(
            "create_location: insert failed",
            extra={"organization_id": session_org_id, "error": str(exc)},
        )
        raise HTTPException(status_code=500, detail="Failed to create location. Please retry.")

    row = result.data[0] if result.data else {}

    logger.info(
        "create_location: location created",
        extra={
            "location_id": location_id,
            "organization_id": session_org_id,
            "name": body.name,
        },
    )

    return {
        "location_id": str(row.get("location_id", location_id)),
        "organization_id": session_org_id,
        "name": row.get("name", body.name),
        # SECURITY: only last 4 chars of the key the caller just submitted
        "api_key_last4": _mask_key(body.acculynx_api_key),
        "connection_status": row.get("connection_status", "untested"),
        "created_at": row.get("created_at", datetime.now(timezone.utc).isoformat()),
    }


# ── T2-06: PATCH /api/v1/settings/locations/{location_id} ─────────────────────

@router.patch(
    "/settings/locations/{location_id}",
    summary="Update location name or rotate AccuLynx API key",
)
async def update_location(
    location_id: str,
    body: UpdateLocationRequest,
    request: Request,
) -> dict:
    """
    Updates location name and/or rotates the AccuLynx API key.

    At least one field must be provided (422 if both are null).
    When the API key is rotated, connection_status resets to "untested"
    so the UI knows to re-validate the new key.

    api_key_last4 only in response — full key is never returned.
    """
    if body.name is None and body.acculynx_api_key is None:
        raise HTTPException(
            status_code=422,
            detail="At least one of 'name' or 'acculynx_api_key' must be provided.",
        )

    org = await _resolve_org(request)
    session_org_id = str(org["organization_id"])
    client = await get_supabase_client()

    # Fetch existing row — verify it belongs to this org (tenancy guard)
    existing = await (
        client.table("locations")
        .select("location_id, organization_id, name, acculynx_api_key, connection_status")
        .eq("location_id", location_id)
        .maybe_single()
        .execute()
    )
    if not existing or not existing.data:
        raise HTTPException(status_code=404, detail=f"Location '{location_id}' not found.")
    row = existing.data

    if str(row["organization_id"]) != session_org_id:
        raise HTTPException(
            status_code=403,
            detail="Location does not belong to the authenticated organization.",
        )

    # Build update payload — only mutate fields that were supplied
    update_data: dict = {}
    if body.name is not None:
        update_data["name"] = body.name
    if body.acculynx_api_key is not None:
        update_data["acculynx_api_key"] = body.acculynx_api_key
        # Rotating the key invalidates any prior connection test
        update_data["connection_status"] = "untested"

    try:
        result = await (
            client.table("locations")
            .update(update_data)
            .eq("location_id", location_id)
            .execute()
        )
    except Exception as exc:
        logger.error(
            "update_location: update failed",
            extra={"location_id": location_id, "error": str(exc)},
        )
        raise HTTPException(status_code=500, detail="Failed to update location. Please retry.")

    updated_row = result.data[0] if result.data else {}

    # Determine which api_key to mask — use rotated key if supplied, else existing
    key_for_mask = body.acculynx_api_key or row.get("acculynx_api_key", "")

    logger.info(
        "update_location: location updated",
        extra={
            "location_id": location_id,
            "fields_updated": list(update_data.keys()),
        },
    )

    return {
        "location_id": location_id,
        "name": updated_row.get("name", row["name"]),
        # SECURITY: last 4 chars only — never return the full key
        "api_key_last4": _mask_key(key_for_mask),
        "connection_status": updated_row.get("connection_status", row["connection_status"]),
        "updated_at": updated_row.get("updated_at", datetime.now(timezone.utc).isoformat()),
    }


# ── T2-06: DELETE /api/v1/settings/locations/{location_id} ────────────────────

@router.delete(
    "/settings/locations/{location_id}",
    status_code=204,
    summary="Remove a location",
)
async def delete_location(location_id: str, request: Request) -> Response:
    """
    Deletes a location row.

    Returns 409 Conflict if there are jobs for this location in a non-terminal
    state (queued or processing). Terminal states (complete, failed, bounced)
    are safe — those jobs have finished and their data remains intact.
    """
    org = await _resolve_org(request)
    session_org_id = str(org["organization_id"])
    client = await get_supabase_client()

    # Tenancy check — confirm the location belongs to this org
    existing = await (
        client.table("locations")
        .select("location_id, organization_id")
        .eq("location_id", location_id)
        .maybe_single()
        .execute()
    )
    if not existing or not existing.data:
        raise HTTPException(status_code=404, detail=f"Location '{location_id}' not found.")

    if str(existing.data["organization_id"]) != session_org_id:
        raise HTTPException(
            status_code=403,
            detail="Location does not belong to the authenticated organization.",
        )

    # Block deletion if active jobs exist (queued or processing)
    active_jobs = await (
        client.table("jobs")
        .select("job_id", count="exact")
        .eq("location_id", location_id)
        .in_("status", ["queued", "processing"])
        .execute()
    )
    if active_jobs.count and active_jobs.count > 0:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot delete location: {active_jobs.count} job(s) are still queued or "
                "processing. Wait for them to complete or fail before removing this location."
            ),
        )

    try:
        await (
            client.table("locations")
            .delete()
            .eq("location_id", location_id)
            .execute()
        )
    except Exception as exc:
        logger.error(
            "delete_location: delete failed",
            extra={"location_id": location_id, "error": str(exc)},
        )
        raise HTTPException(status_code=500, detail="Failed to delete location. Please retry.")

    logger.info("delete_location: location deleted", extra={"location_id": location_id})
    return Response(status_code=204)


# ── T2-06: PATCH /api/v1/settings/locations/{location_id}/notifications ────────

class UpdateNotificationsRequest(BaseModel):
    slack_webhook_url: str

    @field_validator("slack_webhook_url")
    @classmethod
    def must_be_slack_url(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith("https://hooks.slack.com/"):
            raise ValueError(
                "slack_webhook_url must be a valid Slack Incoming Webhook URL "
                "(must start with https://hooks.slack.com/)."
            )
        return v


@router.patch(
    "/settings/locations/{location_id}/notifications",
    summary="Save Slack webhook URL for a location's notification channel",
)
async def update_notifications(
    location_id: str,
    body: UpdateNotificationsRequest,
    request: Request,
) -> dict:
    """
    Stores the Slack webhook URL in locations.notification_channels JSONB.

    Shape written to DB: {"slack": {"webhook_url": "<url>"}}
    This is the exact shape get_notification_adapter() in notification_service.py
    reads — do not change the structure without updating the adapter factory.

    Performs a JSONB merge so other future channel keys (acculynx, signal) are
    preserved when only the slack entry is updated.
    """
    org = await _resolve_org(request)
    session_org_id = str(org["organization_id"])
    client = await get_supabase_client()

    # Tenancy check
    existing = await (
        client.table("locations")
        .select("location_id, organization_id, notification_channels")
        .eq("location_id", location_id)
        .maybe_single()
        .execute()
    )
    if not existing or not existing.data:
        raise HTTPException(status_code=404, detail=f"Location '{location_id}' not found.")

    if str(existing.data["organization_id"]) != session_org_id:
        raise HTTPException(
            status_code=403,
            detail="Location does not belong to the authenticated organization.",
        )

    # Merge new slack config into existing notification_channels JSONB.
    # This preserves any other channel keys that may exist.
    current_channels: dict = existing.data.get("notification_channels") or {}
    updated_channels = {
        **current_channels,
        "slack": {"webhook_url": body.slack_webhook_url},
    }

    try:
        result = await (
            client.table("locations")
            .update({"notification_channels": updated_channels})
            .eq("location_id", location_id)
            .execute()
        )
    except Exception as exc:
        logger.error(
            "update_notifications: update failed",
            extra={"location_id": location_id, "error": str(exc)},
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to save notification settings. Please retry.",
        )

    updated_row = result.data[0] if result.data else {}

    logger.info(
        "update_notifications: Slack webhook URL saved",
        extra={"location_id": location_id},
    )

    return {
        "location_id": location_id,
        "notification_channels": updated_row.get("notification_channels", updated_channels),
        "updated_at": updated_row.get("updated_at", datetime.now(timezone.utc).isoformat()),
    }


# ── T2-06: POST /api/v1/settings/locations/{location_id}/notifications/test ────

@router.post(
    "/settings/locations/{location_id}/notifications/test",
    summary="Send a test Slack notification to verify the webhook URL",
)
async def test_notification(
    location_id: str,
    request: Request,
) -> dict:
    """
    Fires a test Slack message through the channel adapter to verify the
    configured webhook URL is reachable and authenticated.

    Uses get_notification_adapter() from notification_service — never calls
    Slack directly. This ensures the test exercises the exact same code path
    as the live bounce_back Celery task.

    Returns 400 if no Slack webhook URL is configured for this location.
    Returns delivery_status "sent" or "failed" depending on Slack's response.
    """
    from backend.services.notification_service import NotificationMessage, get_notification_adapter
    from backend.core.config import get_settings

    org = await _resolve_org(request)
    session_org_id = str(org["organization_id"])
    client = await get_supabase_client()

    # Fetch location — verify tenancy and get notification_channels
    existing = await (
        client.table("locations")
        .select("location_id, organization_id, name, notification_channels")
        .eq("location_id", location_id)
        .maybe_single()
        .execute()
    )
    if not existing or not existing.data:
        raise HTTPException(status_code=404, detail=f"Location '{location_id}' not found.")

    row = existing.data
    if str(row["organization_id"]) != session_org_id:
        raise HTTPException(
            status_code=403,
            detail="Location does not belong to the authenticated organization.",
        )

    channel_config: dict = row.get("notification_channels") or {}
    adapter = get_notification_adapter(channel_config)

    if adapter is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "No Slack webhook URL configured for this location. "
                "Save a webhook URL first via PATCH /settings/locations/{id}/notifications."
            ),
        )

    # Build a representative test message using the adapter's expected TypedDict shape
    settings = get_settings()
    app_base_url = getattr(settings, "app_base_url", None) or "https://app.omnidrop.dev"
    test_deep_link = f"{app_base_url}/dashboard/ops/jobs/test"

    test_message: NotificationMessage = {
        "location_name": row.get("name", "Test Location"),
        "acculynx_job_id": None,
        "file_name": "test-invoice.pdf",
        "document_summary": "This is a test notification from OmniDrop AI.",
        "clarification_question": (
            "Is your Slack notification channel configured correctly? "
            "If you can read this, everything is working."
        ),
        "job_deep_link": test_deep_link,
    }

    # Dispatch through the adapter — never call Slack directly from an API route
    send_result = adapter.send(test_message)
    delivery_status = send_result.get("status", "failed")
    channel = send_result.get("channel", "slack")

    logger.info(
        "test_notification: test message dispatched",
        extra={
            "location_id": location_id,
            "channel": channel,
            "delivery_status": delivery_status,
        },
    )

    return {
        "location_id": location_id,
        "channel": channel,
        "delivery_status": delivery_status,
        "message": (
            "Test notification sent successfully."
            if delivery_status == "sent"
            else "Test notification failed to deliver. Check the webhook URL and try again."
        ),
    }


# ── T2-07 stub (implemented next session) ─────────────────────────────────────

@router.post(
    "/settings/pricing-contracts",
    status_code=201,
    summary="Upload a pricing contract file  [T2-07]",
)
async def upload_pricing_contract(
    request: Request,
    file: UploadFile = File(...),
) -> dict:
    """Stub — implemented in T2-07."""
    raise HTTPException(status_code=501, detail="Not yet implemented. Coming in T2-07.")
