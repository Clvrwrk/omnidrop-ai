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


# ── T2-07: POST /api/v1/settings/pricing-contracts ────────────────────────────

# Maximum pricing contract file size: 10 MB
_CONTRACT_MAX_BYTES = 10 * 1024 * 1024

# CSV column name aliases — case-insensitive, accept common variations
_VENDOR_ALIASES    = {"vendor_name", "vendor", "supplier", "manufacturer"}
_DESC_ALIASES      = {"description", "material_description", "item", "material",
                      "product", "product_name", "line_item", "item_description"}
_PRICE_ALIASES     = {"unit_price", "contracted_unit_price", "price", "cost",
                      "rate", "contracted_price", "contract_price"}
_SKU_ALIASES       = {"sku", "unit", "uom", "unit_of_measure", "part_number",
                      "part_no", "item_no", "item_number", "product_code", "code"}
_EFF_DATE_ALIASES  = {"effective_date", "eff_date", "start_date", "date",
                      "contract_date", "valid_from"}
_EXP_DATE_ALIASES  = {"expiry_date", "expiration_date", "exp_date", "end_date",
                      "valid_to", "valid_until"}


def _normalise_header(h: str) -> str:
    """Lowercase, strip whitespace, collapse internal spaces/hyphens to underscore."""
    import re
    return re.sub(r"[\s\-]+", "_", h.strip().lower())


def _match_col(headers_norm: list[str], aliases: set[str]) -> str | None:
    """Return the first normalised header that appears in the alias set, or None."""
    for h in headers_norm:
        if h in aliases:
            return h
    return None


def _parse_price(raw: str) -> float | None:
    """Parse a price string like '$12.50', '12,500.00', or '12.50'. Returns None on failure."""
    import re
    cleaned = re.sub(r"[^\d.]", "", raw.strip())
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None


def _parse_date(raw: str) -> str | None:
    """
    Try to parse a date string into ISO 8601 (YYYY-MM-DD).
    Accepts: YYYY-MM-DD, MM/DD/YYYY, M/D/YY, YYYY/MM/DD.
    Returns None if unparseable.
    """
    from datetime import datetime
    raw = raw.strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d", "%d-%b-%Y", "%b %d %Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _extract_date_from_filename(filename: str) -> str | None:
    """
    Try to pull an ISO date from a filename like 'acme-pricing-2026-01-01.csv'.
    Returns first YYYY-MM-DD match or None.
    """
    import re
    m = re.search(r"(\d{4}-\d{2}-\d{2})", filename)
    return m.group(1) if m else None


def _parse_csv(
    raw_bytes: bytes,
    organization_id: str,
    filename: str,
) -> tuple[list[dict], list[str], str | None]:
    """
    Parse a CSV pricing contract into pricing_contracts row dicts.

    Returns:
        (rows, vendors_found, effective_date)
        rows: list of dicts ready to INSERT into pricing_contracts
        vendors_found: deduplicated list of vendor names
        effective_date: ISO date string or None
    """
    import csv
    import io

    # Attempt UTF-8 first, fall back to latin-1 for files with funky encodings
    try:
        text = raw_bytes.decode("utf-8-sig")   # utf-8-sig strips the BOM if present
    except UnicodeDecodeError:
        text = raw_bytes.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ValueError("CSV file has no header row.")

    # Build a normalised→original header map
    original_headers = list(reader.fieldnames)
    norm_headers = [_normalise_header(h) for h in original_headers]
    norm_to_orig = dict(zip(norm_headers, original_headers))

    # Map normalised header names to column roles
    vendor_col = _match_col(norm_headers, _VENDOR_ALIASES)
    desc_col   = _match_col(norm_headers, _DESC_ALIASES)
    price_col  = _match_col(norm_headers, _PRICE_ALIASES)
    sku_col    = _match_col(norm_headers, _SKU_ALIASES)
    eff_col    = _match_col(norm_headers, _EFF_DATE_ALIASES)
    exp_col    = _match_col(norm_headers, _EXP_DATE_ALIASES)

    if not vendor_col:
        raise ValueError(
            f"CSV is missing a vendor_name column. "
            f"Recognised aliases: {sorted(_VENDOR_ALIASES)}. "
            f"Found headers: {original_headers}."
        )
    if not price_col:
        raise ValueError(
            f"CSV is missing a unit_price column. "
            f"Recognised aliases: {sorted(_PRICE_ALIASES)}. "
            f"Found headers: {original_headers}."
        )

    rows: list[dict] = []
    vendors: set[str] = set()
    file_effective_date: str | None = _extract_date_from_filename(filename)
    first_date_found: str | None = None

    for line_num, row in enumerate(reader, start=2):  # start=2 because row 1 is header
        # Use original headers to access values, then normalise for role lookup
        def _get(norm_col: str | None) -> str:
            if norm_col is None:
                return ""
            orig = norm_to_orig.get(norm_col, "")
            return (row.get(orig) or "").strip()

        vendor_name = _get(vendor_col)
        if not vendor_name:
            continue   # Skip blank/headerless rows silently

        raw_price = _get(price_col)
        unit_price = _parse_price(raw_price)
        if unit_price is None:
            logger.warning(
                "upload_pricing_contract: skipping row with unparseable price",
                extra={"line": line_num, "raw_price": raw_price, "vendor": vendor_name},
            )
            continue

        description = _get(desc_col) or None
        sku         = _get(sku_col) or None

        # Parse effective/expiry dates from columns if present
        raw_eff = _get(eff_col)
        raw_exp = _get(exp_col)
        effective_date = _parse_date(raw_eff) if raw_eff else None
        expiry_date    = _parse_date(raw_exp) if raw_exp else None

        # Track first date found in data for fallback
        if first_date_found is None and effective_date:
            first_date_found = effective_date

        vendors.add(vendor_name)
        rows.append({
            "organization_id":      organization_id,
            "vendor_name":          vendor_name,
            "description":          description,
            "sku":                  sku,
            "contracted_unit_price": unit_price,
            "effective_date":       effective_date,
            "expiry_date":          expiry_date,
        })

    # Resolve final effective_date: column data → filename → None
    resolved_effective_date = first_date_found or file_effective_date

    return rows, sorted(vendors), resolved_effective_date


def _parse_pdf(
    raw_bytes: bytes,
    organization_id: str,
    filename: str,
) -> tuple[list[dict], list[str], str | None]:
    """
    Parse a PDF pricing contract via Unstructured.io.

    Strategy: use 'fast' — pricing contracts are clean digital PDFs, not
    scanned invoices. Extract table elements first; fall back to heuristic
    line parsing on all text if table extraction yields zero rows.

    Returns:
        (rows, vendors_found, effective_date)
    """
    import re
    from backend.services.unstructured_service import UnstructuredService

    elements = UnstructuredService.partition_document(
        file_bytes=raw_bytes,
        filename=filename,
        document_type_hint="proposal",   # "proposal" → fast strategy
    )

    # ── Step 1: Extract all text lines from Table elements ────────────────────
    table_lines: list[str] = []
    all_lines:   list[str] = []
    file_effective_date = _extract_date_from_filename(filename)

    for el in elements:
        text = el.get("text", "").strip()
        if not text:
            continue
        all_lines.append(text)
        if el.get("type") == "Table":
            table_lines.extend(text.splitlines())

    # ── Step 2: Attempt row extraction from table text ────────────────────────
    rows, vendors, eff_date = _extract_rows_from_lines(
        table_lines if table_lines else all_lines,
        organization_id,
    )

    # If table parsing got nothing, try the full text
    if not rows and table_lines:
        rows, vendors, eff_date = _extract_rows_from_lines(all_lines, organization_id)

    # Try to find an effective date in the full text if not yet found
    if eff_date is None and file_effective_date is None:
        for line in all_lines[:30]:   # Only scan the first 30 lines (header area)
            m = re.search(r"(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})", line)
            if m:
                eff_date = _parse_date(m.group(1))
                if eff_date:
                    break

    return rows, vendors, eff_date or file_effective_date


def _extract_rows_from_lines(
    lines: list[str],
    organization_id: str,
) -> tuple[list[dict], list[str], str | None]:
    """
    Heuristic extraction: scan text lines for pricing rows.

    Looks for lines that contain a price pattern (currency/numeric value).
    Splits each line into: [vendor?] [description] [sku?] [price] [unit?]

    This is best-effort — structured CSV is strongly preferred for accuracy.
    """
    import re

    # Pattern: a standalone decimal number, optionally preceded by $ or currency
    price_re = re.compile(r"\$?\s*(\d{1,3}(?:,\d{3})*(?:\.\d{1,4})?)\s*$")

    rows: list[dict] = []
    vendors: set[str] = set()
    first_date: str | None = None

    # Try to detect a header line to skip it
    header_keywords = {"vendor", "description", "price", "unit", "sku", "item", "cost", "rate"}

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Skip lines that look like headers
        low = line.lower()
        if sum(1 for kw in header_keywords if kw in low) >= 3:
            continue

        # Each line expected to be tab or pipe or multiple-space delimited
        parts = re.split(r"\t|\s{2,}|\|", line)
        parts = [p.strip() for p in parts if p.strip()]

        if len(parts) < 2:
            continue

        # The last part that looks like a price is our unit_price
        price_val: float | None = None
        price_idx: int = -1
        for i in range(len(parts) - 1, -1, -1):
            m = price_re.search(parts[i])
            if m:
                price_val = _parse_price(parts[i])
                price_idx = i
                break

        if price_val is None or price_val <= 0:
            continue

        remaining = [p for j, p in enumerate(parts) if j != price_idx]

        # First remaining part is vendor_name; second (if exists) is description
        vendor_name = remaining[0] if remaining else None
        description = remaining[1] if len(remaining) > 1 else None
        sku         = remaining[2] if len(remaining) > 2 else None

        if not vendor_name:
            continue

        vendors.add(vendor_name)
        rows.append({
            "organization_id":       organization_id,
            "vendor_name":           vendor_name,
            "description":           description,
            "sku":                   sku,
            "contracted_unit_price": price_val,
            "effective_date":        None,
            "expiry_date":           None,
        })

    return rows, sorted(vendors), first_date


@router.post(
    "/settings/pricing-contracts",
    status_code=201,
    summary="Upload a pricing contract (CSV or PDF) — inserts rows into pricing_contracts",
)
async def upload_pricing_contract(
    request: Request,
    file: UploadFile = File(...),
    organization_id: str = Form(...),
) -> dict:
    """
    Accepts a CSV or PDF pricing contract, parses it into structured rows,
    and bulk-inserts them into the pricing_contracts table scoped to the org.

    CSV is strongly preferred — column headers are flexible (vendor_name/vendor/
    supplier, unit_price/price/cost, description/material_description, sku/unit).

    PDF is parsed via Unstructured.io (fast strategy) — table elements are
    extracted first, with a full-text heuristic fallback. Best-effort: structured
    CSV is more reliable for complex layouts.

    No Celery dispatch — pricing contracts are reference data, not pipeline docs.
    Parse and insert happen synchronously in this request.

    Auth: organization_id in form body is validated against the WorkOS session.
    """
    org = await _resolve_org(request)
    session_org_id = str(org["organization_id"])

    # Guard: form org must match session org
    if organization_id != session_org_id:
        raise HTTPException(
            status_code=403,
            detail="organization_id does not match the authenticated session.",
        )

    # ── 1. Validate file type ──────────────────────────────────────────────────
    content_type = (file.content_type or "").split(";")[0].strip().lower()
    filename = file.filename or "contract"

    # Accept by content-type, but also accept .csv files sent as octet-stream
    is_csv = (
        content_type in {"text/csv", "text/plain", "application/csv"}
        or filename.lower().endswith(".csv")
    )
    is_pdf = (
        content_type == "application/pdf"
        or filename.lower().endswith(".pdf")
    )

    if not is_csv and not is_pdf:
        raise HTTPException(
            status_code=415,
            detail=(
                f"Unsupported file type '{content_type}'. "
                "Only CSV and PDF pricing contracts are accepted."
            ),
        )

    # ── 2. Read bytes + size guard ─────────────────────────────────────────────
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(file_bytes) > _CONTRACT_MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail="File exceeds the 10 MB maximum for pricing contracts.",
        )

    # ── 3. Parse into rows ─────────────────────────────────────────────────────
    try:
        if is_csv:
            rows, vendors_found, effective_date = _parse_csv(
                file_bytes, session_org_id, filename
            )
        else:
            rows, vendors_found, effective_date = _parse_pdf(
                file_bytes, session_org_id, filename
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error(
            "upload_pricing_contract: parse failed",
            extra={"filename": filename, "org": session_org_id, "error": str(exc)},
        )
        raise HTTPException(
            status_code=400,
            detail=f"Failed to parse the contract file: {exc}",
        )

    if not rows:
        raise HTTPException(
            status_code=400,
            detail=(
                "No valid pricing rows could be extracted from the file. "
                "Check that the file has vendor_name and unit_price columns (CSV), "
                "or contains a structured pricing table (PDF)."
            ),
        )

    # ── 4. Bulk insert into pricing_contracts ─────────────────────────────────
    client = await get_supabase_client()
    try:
        result = await client.table("pricing_contracts").insert(rows).execute()
    except Exception as exc:
        logger.error(
            "upload_pricing_contract: insert failed",
            extra={
                "org": session_org_id,
                "row_count": len(rows),
                "error": str(exc),
            },
        )
        raise HTTPException(
            status_code=500,
            detail="Rows parsed successfully but database insert failed. Please retry.",
        )

    rows_inserted = len(result.data) if result.data else len(rows)

    logger.info(
        "upload_pricing_contract: complete",
        extra={
            "organization_id": session_org_id,
            "filename": filename,
            "rows_inserted": rows_inserted,
            "vendors_found": vendors_found,
            "effective_date": effective_date,
        },
    )

    # ── 5. Return 201 ─────────────────────────────────────────────────────────
    return {
        "organization_id": session_org_id,
        "rows_inserted": rows_inserted,
        "vendors_found": vendors_found,
        "effective_date": effective_date,
    }
