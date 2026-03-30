# ServiceTitan — OmniDrop Reference

## 1. Overview

**Future Integration — Not Yet Implemented.** OmniDrop currently integrates only
with AccuLynx. ServiceTitan support is planned and this document establishes the
integration pattern to follow when it is built.

ServiceTitan is a field service management platform used by HVAC, plumbing, and
roofing contractors. The OmniDrop integration will receive job and invoice events
from ServiceTitan webhooks and route them through the same Celery processing pipeline
used for AccuLynx.

**Inbound flow (webhooks):** ServiceTitan POSTs job and invoice events to a Hookdeck
source URL. Hookdeck re-signs the event and forwards it to
`POST /api/v1/webhooks/servicetitan`. The webhook payload includes a `tenant_id`
and relevant entity IDs that the Celery pipeline uses to fetch document data via
the ServiceTitan REST API.

**Multi-tenant architecture:** ServiceTitan credentials are per-location, per-client.
There is no global key. Each client location stores its own `app_key`, `client_id`,
`client_secret`, and `tenant_id` in the Supabase `locations` table, fetched at task
runtime by `location_id`. The `/settings` UI lets clients enter and update these
credentials. OAuth 2.0 access tokens are obtained at task runtime using the client
credentials flow and are not stored persistently.

**Base URL pattern:** `https://api.servicetitan.io/v2/tenant/{tenant_id}/`

Files that will touch ServiceTitan (when built):
- `shared/models/servicetitan.py` — webhook payload Pydantic models
- `backend/api/v1/webhooks.py` — webhook ingestion endpoint
- `backend/api/v1/settings.py` — location credential management (masked on read)
- `backend/workers/intake_tasks.py` — `fetch_servicetitan_document` Celery task
- `shared/constants.py` — rate limit constants

## 2. Credentials & Environment Variables

ServiceTitan credentials are **not** stored in the `omnidrop-secrets` environment
group and are **not** set as application-level environment variables. They are
per-location secrets entered by the client via `/settings` and stored in the Supabase
`locations` table.

ServiceTitan uses OAuth 2.0 client credentials flow. Four values are required per
tenant:

| Field | Storage | Exposed To |
|---|---|---|
| `servicetitan_app_key` | Supabase `locations` table, fetched by `location_id` at task runtime | Backend workers only — never returned in API responses |
| `servicetitan_client_id` | Supabase `locations` table | Backend workers only |
| `servicetitan_client_secret` | Supabase `locations` table | Backend workers only — never returned in API responses |
| `servicetitan_tenant_id` | Supabase `locations` table | Backend workers only |
| `api_key_last4` | Derived by `_mask_key()` in `backend/api/v1/settings.py` (applied to `client_secret`) | Frontend `/settings` page (read-only display) |

**There are no ServiceTitan environment variables in OmniDrop. Do not create any.**

### How credentials are stored and retrieved

```python
# backend/api/v1/settings.py — storing credentials (write path)
def _mask_key(key: str) -> str:
    """Returns only the last 4 characters for safe display."""
    return f"****{key[-4:]}"

# backend/workers/intake_tasks.py — retrieving credentials at task runtime
async def _get_servicetitan_credentials(location_id: str) -> dict:
    """Fetch ServiceTitan credentials for a location from Supabase."""
    result = await supabase_client.table("locations") \
        .select(
            "servicetitan_app_key,"
            "servicetitan_client_id,"
            "servicetitan_client_secret,"
            "servicetitan_tenant_id"
        ) \
        .eq("id", location_id) \
        .single() \
        .execute()
    return result.data
```

**Key security rules:**
- `servicetitan_client_secret` is NEVER returned in any API response.
- The `/settings` endpoint only returns `api_key_last4` (masked `client_secret`).
- `SUPABASE_SERVICE_ROLE_KEY` is the only server credential required to read
  location credentials — it must never be exposed to the frontend.
- OAuth access tokens obtained at runtime are used in-memory only and are not
  stored in Supabase or logged.

### OAuth 2.0 Token Flow

ServiceTitan uses the client credentials grant. An access token must be obtained
before each API call (or cached with respect to the token's expiry):

```python
# Token endpoint (not tenant-scoped):
POST https://auth.servicetitan.io/connect/token
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials
&client_id={client_id}
&client_secret={client_secret}
&App-Key: {app_key}   # also passed as a header on all API calls
```

Actual credential values: [ASK USER] (per location, client-provided).

### Credential value

Clients retrieve their ServiceTitan credentials from:
**ServiceTitan Developer Portal → My Apps → [App Name] → Credentials**.
`tenant_id` is visible in ServiceTitan under **Settings → Integrations → API**.
Actual credential values: [ASK USER] (per location, client-provided).

## 3. Key Concepts

### Multi-Tenant Location Model

OmniDrop serves organisations with multiple contractor locations (branches). Each
location maps to one row in the Supabase `locations` table and holds one set of
ServiceTitan credentials. When a webhook arrives, `location_id` in the OmniDrop
payload is the link between the event and the correct credentials.

```
organizations
  └── locations (one row per branch, one credential set per row)
        ├── id (location_id referenced in every webhook and Celery task)
        ├── servicetitan_app_key
        ├── servicetitan_client_id
        ├── servicetitan_client_secret   (never returned to frontend)
        ├── servicetitan_tenant_id
        └── notification_channels JSONB (Slack webhook URL, future adapters)
```

### Webhook Flow

OmniDrop never receives ServiceTitan webhooks directly. The full path:

```
ServiceTitan → Hookdeck source URL → Hookdeck verifies ServiceTitan signature
             → Hookdeck re-signs → POST /api/v1/webhooks/servicetitan
             → FastAPI verifies Hookdeck HMAC → Pydantic validates payload
             → process_document.delay() → 200 OK
```

See `docs/references/hookdeck.md` for the HMAC verification implementation.

### Supported Webhook Events

| Event | Description |
|---|---|
| `job.created` | New job created in ServiceTitan |
| `job.updated` | Existing job modified |
| `invoice.created` | New invoice generated |
| `invoice.updated` | Existing invoice modified |

### Rate Limits

| Limit | Value | Enforcement |
|---|---|---|
| Per tenant | 500 req/min | Celery `rate_limit="10/s"` on fetch tasks (conservative) |
| 429 monitoring | — | Sentry `failed_request_status_codes={429}` |

All ServiceTitan API calls MUST go through Celery tasks. Synchronous calls outside
a Celery task are prohibited — they bypass rate limiting and will hit the tenant
ceiling under real load.

### Celery Rate Limit Pattern

```python
# backend/workers/intake_tasks.py
@celery_app.task(rate_limit="10/s")
def fetch_servicetitan_document(location_id: str, job_id: str, invoice_id: str | None):
    """
    Fetch document/invoice data from ServiceTitan API.
    Credentials are fetched from Supabase using location_id — never from env vars.
    An OAuth access token is obtained at runtime using client credentials flow.
    """
    creds = _get_servicetitan_credentials(location_id)
    token = _get_servicetitan_token(creds)
    ...
```

The `rate_limit="10/s"` decorator is enforced per Celery worker process.
`shared/constants.py` holds the canonical rate limit values — do not hardcode them
elsewhere.

### Webhook Payload Shape (Planned)

To be defined in `shared/models/servicetitan.py`:

```python
class ServiceTitanJobEvent(BaseModel):
    event_type: str        # e.g. "job.created", "invoice.updated"
    job_id: str            # ServiceTitan job ID
    invoice_id: str | None # ServiceTitan invoice ID (if invoice event)
    tenant_id: str         # ServiceTitan tenant ID — used to look up location
    location_id: str       # OmniDrop location UUID — maps to Supabase locations row
    timestamp: datetime
    data: dict[str, Any]

class ServiceTitanWebhookPayload(BaseModel):
    event: ServiceTitanJobEvent
    version: str           # default "1.0"
```

`location_id` in the event body is the key that ties the webhook to the correct
ServiceTitan credentials and Supabase org.

## 4. Integration Points

### Webhook Ingestion (`backend/api/v1/webhooks.py`)

This endpoint MUST do exactly four things in order — no exceptions:

```python
@router.post("/servicetitan")
async def servicetitan_webhook(
    request: Request,
    _: None = Depends(verify_hookdeck_signature),         # 1. Verify HMAC → 401 if invalid
    payload: ServiceTitanWebhookPayload = ...,             # 2. Validate Pydantic → 422 if malformed
):
    process_document.delay(payload.event)                  # 3. Dispatch to Celery
    return {"status": "ok"}                               # 4. Return 200 immediately

# This endpoint NEVER calls Unstructured.io, Claude, or Supabase. No exceptions.
```

### Document Fetch Task (`backend/workers/intake_tasks.py`)

```python
@celery_app.task(rate_limit="10/s")
def fetch_servicetitan_document(
    location_id: str, job_id: str, invoice_id: str | None
) -> bytes:
    creds = _get_servicetitan_credentials(location_id)    # Fetched from Supabase, not env
    token = _get_servicetitan_token(creds)                # OAuth client credentials grant
    base_url = f"https://api.servicetitan.io/v2/tenant/{creds['servicetitan_tenant_id']}"
    endpoint = f"{base_url}/invoices/{invoice_id}" if invoice_id else f"{base_url}/jobs/{job_id}"
    response = httpx.get(
        endpoint,
        headers={
            "Authorization": f"Bearer {token}",
            "App-Key": creds["servicetitan_app_key"],
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.content
```

### Location Credential Management (`backend/api/v1/settings.py`)

```python
# GET /api/v1/settings/locations/{location_id}
# Returns masked client_secret only — never the raw value
{
  "location_id": "...",
  "servicetitan_tenant_id": "...",   # non-secret, safe to return
  "servicetitan_client_id": "...",   # non-secret, safe to return
  "api_key_last4": "a1b2",           # _mask_key(client_secret) output
  "notification_channels": {...}
}

# PUT /api/v1/settings/locations/{location_id}
# Accepts all four raw credential values on write, stores in Supabase, never echoes secrets
```

### Supabase `locations` Table (Additions Required)

```sql
-- Columns to add when ServiceTitan integration is built:
ALTER TABLE locations
    ADD COLUMN servicetitan_app_key        TEXT,
    ADD COLUMN servicetitan_client_id      TEXT,
    ADD COLUMN servicetitan_client_secret  TEXT,  -- Encrypted at rest by Supabase
    ADD COLUMN servicetitan_tenant_id      TEXT;
```

### `shared/constants.py` (Additions Required)

```python
SERVICETITAN_RATE_LIMIT_PER_TENANT = "10/s"   # Conservative vs 500/min published limit
SERVICETITAN_WEBHOOK_TIMEOUT_SECONDS = 10
```

Always read rate limit values from `shared/constants.py`. Do not hardcode them in
task decorators.

## 5. Common Operations

### Add ServiceTitan Credentials for a Location (via UI)

1. Log in to OmniDrop at `app.omnidrop.dev`.
2. Navigate to `/settings`.
3. Select the location from the location picker.
4. Enter the four credential fields: **App Key**, **Client ID**, **Client Secret**,
   **Tenant ID**. Clients retrieve these from the ServiceTitan Developer Portal.
5. Click **Save**. The backend stores all four values in Supabase and returns only
   `api_key_last4` (masked `client_secret`).
6. The displayed value `****XXXX` confirms the credentials were saved.

### Verify a Location's Credentials Are Set (Developer)

```sql
-- Run in Supabase SQL Editor
SELECT id, name, servicetitan_tenant_id, servicetitan_client_id, api_key_last4
FROM locations
WHERE organization_id = '<org_id>';
-- api_key_last4 = NULL means no credentials have been entered yet
-- Never SELECT servicetitan_client_secret directly — use the masked column
```

### Manually Trigger a Document Fetch (Developer)

```python
# Fire the task directly from a Python shell or test
from backend.workers.intake_tasks import fetch_servicetitan_document

result = fetch_servicetitan_document.delay(
    location_id="<location_uuid>",
    job_id="<servicetitan_job_id>",
    invoice_id="<servicetitan_invoice_id>",  # or None for job-only events
)
print(result.get(timeout=30))  # bytes on success
```

### Check ServiceTitan API Connectivity for a Location

```bash
# Obtain token first (server-side only), then:
curl -X GET \
  "https://api.servicetitan.io/v2/tenant/<tenant_id>/jobs/<job_id>" \
  -H "Authorization: Bearer <access_token>" \
  -H "App-Key: <app_key>" \
  -o /dev/null -w "%{http_code}\n"
# 200 = credentials valid and entity exists
# 401 = token invalid or expired (re-run token flow)
# 403 = credentials valid but insufficient scopes
```

### Replay a Missed Webhook Event

Webhook replay is handled via Hookdeck, not ServiceTitan. See
`docs/references/hookdeck.md` SOP-HOOKDECK-1 and the Hookdeck dashboard
**Events → Retry** flow.

### Test the Full Webhook-to-Pipeline Flow (Local Dev)

```bash
# 1. Start FastAPI locally
uvicorn backend.api.main:app --reload --port 8000

# 2. Start Celery worker
celery -A backend.workers.celery_app worker --loglevel=info

# 3. Start Hookdeck local tunnel (see docs/references/hookdeck.md SOP-HOOKDECK-3)
hookdeck listen 8000 servicetitan-source

# 4. Send a test event from the Hookdeck dashboard → "Send Test Event"
# 5. Watch FastAPI logs for "process_document started" and Celery logs for task pickup
```

## 6. Error Handling & Monitoring

### ServiceTitan API Error Codes

| HTTP Status | Meaning | Action |
|---|---|---|
| `200` | Success | Continue pipeline |
| `401` | Token invalid or expired | Re-run OAuth flow; if persistent, check `client_id`/`client_secret` in `/settings` |
| `403` | Valid token, insufficient scopes | Log error, mark job `status='error'`; client must verify API app scopes in ServiceTitan Developer Portal |
| `404` | Entity not found | Log `entity_not_found`, mark job `status='error'`; may indicate a deleted job/invoice on the ServiceTitan side |
| `429` | Rate limit hit | Celery retries with backoff; Sentry captures via `failed_request_status_codes={429}` |
| `5xx` | ServiceTitan server error | Celery retries with exponential backoff up to `max_retries`; alert if sustained |

### Rate Limit Monitoring

```python
# backend/core/sentry.py — 429s are captured as error events
sentry_sdk.init(
    dsn=settings.sentry_python_dsn,
    integrations=[FastApiIntegration(), CeleryIntegration()],
    failed_request_status_codes={429},   # Triggers a Sentry event on every 429
)
```

Set a Sentry alert rule: **more than 5 `429` events in 60 seconds** → page on-call.

### Common Failure Patterns

| Symptom | Likely Cause | Resolution |
|---|---|---|
| `fetch_servicetitan_document` fails with `401` | OAuth token expired or `client_secret` rotated | Re-check credentials in `/settings`; verify token endpoint is reachable |
| Job stuck at `status='processing'`, no Celery activity | Worker not running or Redis connection lost | Check `omnidrop-worker` logs in Render; verify `omnidrop-redis` is running |
| `422 Unprocessable Entity` on webhook endpoint | Payload shape mismatch (ServiceTitan schema changed) | Inspect raw event in Hookdeck dashboard; update `shared/models/servicetitan.py` |
| `401 Invalid webhook signature` on webhook endpoint | `HOOKDECK_SIGNING_SECRET` mismatch | See `docs/references/hookdeck.md` SOP-HOOKDECK-1 |
| No credentials found for `location_id` | Client has not set ServiceTitan credentials yet | Log `missing_servicetitan_credentials`, mark job `status='error'`; surface via onboarding |
| OAuth token request fails | Invalid `app_key`, `client_id`, or `client_secret` | Client must verify credentials in ServiceTitan Developer Portal |

### Structured Logging

Always include `location_id`, `job_id`, `invoice_id`, and `tenant_id` in log entries
for ServiceTitan operations.

```python
import structlog
log = structlog.get_logger()

log.info(
    "fetch_servicetitan_document.started",
    location_id=location_id,
    job_id=job_id,
    invoice_id=invoice_id,
    tenant_id=tenant_id,
)
log.error(
    "fetch_servicetitan_document.failed",
    location_id=location_id,
    job_id=job_id,
    status_code=response.status_code,
    exc_info=True,
)
```

### Sentry Alerts to Configure

| Alert | Condition |
|---|---|
| ServiceTitan 429 spike | More than 5 `429` events in 60 seconds |
| Auth failure | More than 3 `401` errors from `fetch_servicetitan_document` in 10 minutes |
| Document fetch error rate | More than 10% of `fetch_servicetitan_document` tasks in error state |

Configure these in Sentry under **Alerts → Alert Rules** for the backend project.

## 7. SOPs

### SOP-SERVICETITAN-1: Onboard a New Location (Client Adds Their Credentials)

**When:** A new client location is provisioned in OmniDrop and ServiceTitan webhooks
are not yet flowing.
**Time:** ~15 minutes
**Prerequisite:** The location row exists in the Supabase `locations` table (created
during onboarding wizard step 2). The client has their ServiceTitan API credentials
ready from the Developer Portal.

Step 1. Have the client log in to OmniDrop at `app.omnidrop.dev`.

Step 2. Navigate to `/settings`.

Step 3. Select the new location from the location picker.

Step 4. Enter all four credential fields:
- **App Key** — from ServiceTitan Developer Portal → My Apps → [App] → App Key
- **Client ID** — from Developer Portal → My Apps → [App] → Client ID
- **Client Secret** — from Developer Portal → My Apps → [App] → Client Secret
- **Tenant ID** — from ServiceTitan Settings → Integrations → API → Tenant ID

Step 5. Click **Save**. The displayed `client_secret` value changes to `****XXXX`.

Step 6. Verify credentials are stored correctly:
```sql
-- Supabase SQL Editor
SELECT id, name, servicetitan_tenant_id, servicetitan_client_id, api_key_last4
FROM locations
WHERE id = '<location_uuid>';
-- api_key_last4 should now be non-null
```

Step 7. Trigger a test webhook from ServiceTitan or use Hookdeck **"Send Test Event"**
to confirm the full flow works for this location.

Step 8. Confirm in the Celery logs (Render → `omnidrop-worker` → Logs) that
`fetch_servicetitan_document` completed without a `401` error.

Step 9. Tell Claude: `"SOP-SERVICETITAN-1 complete. Location [name/id] credentials configured. Resume [current task name]."`

Done when: a test event flows through the pipeline and the job appears in the OmniDrop
ops dashboard.

---

### SOP-SERVICETITAN-2: Rotate a Location's ServiceTitan Credentials

**When:** A client's ServiceTitan credentials have been revoked, rotated, or are
returning `401` errors.
**Time:** ~10 minutes
**Prerequisite:** The client has new credentials from the ServiceTitan Developer Portal.

Step 1. Have the client log in at `app.omnidrop.dev` and navigate to `/settings`.

Step 2. Select the affected location.

Step 3. Enter the updated credential field(s) — at minimum the new **Client Secret**.

Step 4. Click **Save**. Confirm the `api_key_last4` display updates if the secret changed.

Step 5. Verify the `401` errors stop in Sentry (Sentry → Issues → filter by
`fetch_servicetitan_document`). New events should process successfully within 1–2 minutes.

Step 6. If any jobs were stuck in `status='error'` due to bad credentials, replay them:
```sql
-- Identify affected jobs
SELECT id, status, location_id, created_at
FROM jobs
WHERE location_id = '<location_uuid>'
  AND status = 'error'
  AND created_at > now() - interval '24 hours';
```
Then replay via Hookdeck dashboard for any missed webhook events.

Step 7. Tell Claude: `"SOP-SERVICETITAN-2 complete. Location [name/id] credentials rotated. 401 errors resolved. Resume [current task name]."`

Done when: `fetch_servicetitan_document` tasks for this location complete without errors.

---

### SOP-SERVICETITAN-3: Investigate a Stalled Document Pipeline

**When:** A job or invoice was updated in ServiceTitan but never appears in the
OmniDrop dashboard and no error is visible.
**Time:** ~15 minutes
**Prerequisite:** You have the ServiceTitan `job_id` and/or `invoice_id` for the
stalled document.

Step 1. Check the Hookdeck dashboard for the webhook event:
- Log in to https://dashboard.hookdeck.com
- **Sources → servicetitan-source → Events**
- Search for the `job_id`. Confirm the event was received and its delivery status.

Step 2. If the event shows **"Failed"** delivery: the FastAPI endpoint returned a
non-200. Check the `omnidrop-api` logs in Render for the error. Common causes:
- `401` = `HOOKDECK_SIGNING_SECRET` mismatch (see `docs/references/hookdeck.md` SOP-HOOKDECK-1)
- `422` = Payload schema mismatch (inspect the raw event body in Hookdeck)

Step 3. If the event shows **"Successful"** delivery but the job is not in Supabase:
check the Celery worker logs:
```bash
# Render dashboard → omnidrop-worker → Logs
# Search for the job_id
```

Step 4. If no Celery log entry exists for the `job_id`: the task was never dispatched
or was dropped. Check Redis queue depth via Flower:
```
https://omnidrop-flower.onrender.com
```

Step 5. If the task is in the queue but not processing: the worker may be rate-limited
or at capacity. Check Flower for worker status and active task count.

Step 6. If the task shows as **"FAILURE"** in Flower: expand the traceback. Most
common causes:
- `401 Unauthorized` from ServiceTitan = OAuth token failure (check credentials, follow SOP-SERVICETITAN-2)
- `404 Not Found` from ServiceTitan = job/invoice was deleted in ServiceTitan
- Missing credentials for `location_id` in Supabase (follow SOP-SERVICETITAN-1)

Step 7. Once the root cause is resolved, replay the webhook event from the Hookdeck
dashboard (**"Retry"** on the event) or trigger a new update in ServiceTitan.

Step 8. Confirm the job appears in the OmniDrop ops dashboard within 1–2 minutes.

Step 9. Tell Claude: `"SOP-SERVICETITAN-3 complete. Stalled document [job_id/invoice_id] resolved: [root cause]. Resume [current task name]."`

Done when: the job row exists in Supabase with `status` progressed past `'processing'`.
