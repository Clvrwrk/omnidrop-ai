# JobTread — OmniDrop Reference

## 1. Overview

**Future Integration — Not Yet Implemented.** OmniDrop currently integrates only
with AccuLynx. JobTread support is planned and this document establishes the
integration pattern to follow when it is built.

JobTread is a project management and financials platform for construction contractors.
The OmniDrop integration will receive project and invoice events from JobTread webhooks
and route them through the same Celery processing pipeline used for AccuLynx.

**Inbound flow (webhooks):** JobTread POSTs project and invoice events to a Hookdeck
source URL. Hookdeck re-signs the event and forwards it to
`POST /api/v1/webhooks/jobtread`. The webhook payload includes a `location_id` and
relevant entity IDs that the Celery pipeline uses to fetch document data via the
JobTread REST API.

**Multi-tenant architecture:** JobTread bearer tokens are per-location, per-client.
There is no global token. Each client location stores its own JobTread bearer token
in the Supabase `locations` table, fetched at task runtime by `location_id`. The
`/settings` UI lets clients enter and update their tokens.

**Auth method:** Bearer token passed as `Authorization: Bearer {token}` header.

**Base URL:** `https://api.jobtread.com/`

Files that will touch JobTread (when built):
- `shared/models/jobtread.py` — webhook payload Pydantic models
- `backend/api/v1/webhooks.py` — webhook ingestion endpoint
- `backend/api/v1/settings.py` — location token management (masked on read)
- `backend/workers/intake_tasks.py` — `fetch_jobtread_document` Celery task
- `shared/constants.py` — rate limit constants

## 2. Credentials & Environment Variables

JobTread bearer tokens are **not** stored in the `omnidrop-secrets` environment group
and are **not** set as application-level environment variables. They are per-location
secrets entered by the client via `/settings` and stored in the Supabase `locations`
table, column `jobtread_api_key`.

| Field | Storage | Exposed To |
|---|---|---|
| `jobtread_api_key` | Supabase `locations` table, fetched by `location_id` at task runtime | Backend workers only — never returned in API responses |
| `api_key_last4` | Derived by `_mask_key()` in `backend/api/v1/settings.py` | Frontend `/settings` page (read-only display) |

**There is no `JOBTREAD_API_KEY` environment variable in OmniDrop. Do not create one.**

### How tokens are stored and retrieved

```python
# backend/api/v1/settings.py — storing a token (write path)
def _mask_key(key: str) -> str:
    """Returns only the last 4 characters for safe display."""
    return f"****{key[-4:]}"

# backend/workers/intake_tasks.py — retrieving a token at task runtime
async def _get_jobtread_api_key(location_id: str) -> str:
    """Fetch the JobTread bearer token for a location from Supabase."""
    result = await supabase_client.table("locations") \
        .select("jobtread_api_key") \
        .eq("id", location_id) \
        .single() \
        .execute()
    return result.data["jobtread_api_key"]
```

**Key security rules:**
- `jobtread_api_key` is NEVER returned in any API response.
- The `/settings` endpoint only returns `api_key_last4`.
- `SUPABASE_SERVICE_ROLE_KEY` is the only server credential required to read
  location tokens — it must never be exposed to the frontend.

### Credential value

The JobTread bearer token for each location is entered by the client at:
`/settings` → Location → JobTread API Token field.

Each client retrieves their token from: JobTread → **Settings → Integrations → API Token**.
Actual token values: [ASK USER] (per location, client-provided).

## 3. Key Concepts

### Multi-Tenant Location Model

OmniDrop serves organisations with multiple contractor locations (branches). Each
location maps to one row in the Supabase `locations` table and holds exactly one
JobTread bearer token. When a webhook arrives, `location_id` in the OmniDrop payload
is the link between the event and the correct token.

```
organizations
  └── locations (one row per branch, one jobtread_api_key per row)
        ├── id (location_id referenced in every webhook and Celery task)
        ├── jobtread_api_key (fetched at task runtime, never in env vars)
        └── notification_channels JSONB (Slack webhook URL, future adapters)
```

### Webhook Flow

OmniDrop never receives JobTread webhooks directly. The full path:

```
JobTread → Hookdeck source URL → Hookdeck verifies JobTread signature
         → Hookdeck re-signs → POST /api/v1/webhooks/jobtread
         → FastAPI verifies Hookdeck HMAC → Pydantic validates payload
         → process_document.delay() → 200 OK
```

See `docs/references/hookdeck.md` for the HMAC verification implementation.

### Supported Webhook Events

| Event | Description |
|---|---|
| `project.created` | New project created in JobTread |
| `project.updated` | Existing project modified |
| `invoice.created` | New invoice generated |
| `invoice.updated` | Existing invoice modified |

### Rate Limits

JobTread does not publicly document its API rate limits. Use a conservative
`rate_limit="5/s"` on all fetch tasks to avoid unexpected throttling.

| Limit | Value | Enforcement |
|---|---|---|
| Per API token | Not documented — use conservative limit | Celery `rate_limit="5/s"` on fetch tasks |
| 429 monitoring | — | Sentry `failed_request_status_codes={429}` |

If 429 errors appear in production, reduce the rate limit further in
`shared/constants.py` and redeploy workers. Do not increase beyond `5/s` without
confirming the actual limit with JobTread support.

All JobTread API calls MUST go through Celery tasks. Synchronous calls outside a
Celery task are prohibited — they bypass rate limiting entirely.

### Celery Rate Limit Pattern

```python
# backend/workers/intake_tasks.py
@celery_app.task(rate_limit="5/s")
def fetch_jobtread_document(location_id: str, project_id: str, invoice_id: str | None):
    """
    Fetch document/project data from JobTread API.
    Bearer token is fetched from Supabase using location_id — never from env vars.
    Rate limit is conservative (5/s) — JobTread does not publish its rate limits.
    """
    api_key = _get_jobtread_api_key(location_id)
    ...
```

The `rate_limit="5/s"` decorator is enforced per Celery worker process.
`shared/constants.py` holds the canonical rate limit values — do not hardcode them
elsewhere.

### Webhook Payload Shape (Planned)

To be defined in `shared/models/jobtread.py`:

```python
class JobTreadProjectEvent(BaseModel):
    event_type: str        # e.g. "project.created", "invoice.updated"
    project_id: str        # JobTread project ID
    invoice_id: str | None # JobTread invoice ID (if invoice event)
    location_id: str       # OmniDrop location UUID — maps to Supabase locations row
    timestamp: datetime
    data: dict[str, Any]

class JobTreadWebhookPayload(BaseModel):
    event: JobTreadProjectEvent
    version: str           # default "1.0"
```

`location_id` in the event body is the key that ties the webhook to the correct
JobTread bearer token and Supabase org.

## 4. Integration Points

### Webhook Ingestion (`backend/api/v1/webhooks.py`)

This endpoint MUST do exactly four things in order — no exceptions:

```python
@router.post("/jobtread")
async def jobtread_webhook(
    request: Request,
    _: None = Depends(verify_hookdeck_signature),      # 1. Verify HMAC → 401 if invalid
    payload: JobTreadWebhookPayload = ...,              # 2. Validate Pydantic → 422 if malformed
):
    process_document.delay(payload.event)              # 3. Dispatch to Celery
    return {"status": "ok"}                            # 4. Return 200 immediately

# This endpoint NEVER calls Unstructured.io, Claude, or Supabase. No exceptions.
```

### Document Fetch Task (`backend/workers/intake_tasks.py`)

```python
@celery_app.task(rate_limit="5/s")
def fetch_jobtread_document(
    location_id: str, project_id: str, invoice_id: str | None
) -> bytes:
    api_key = _get_jobtread_api_key(location_id)    # Fetched from Supabase, not env
    endpoint = (
        f"https://api.jobtread.com/invoices/{invoice_id}"
        if invoice_id
        else f"https://api.jobtread.com/projects/{project_id}"
    )
    response = httpx.get(
        endpoint,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=30,
    )
    response.raise_for_status()
    return response.content
```

### Location Token Management (`backend/api/v1/settings.py`)

```python
# GET /api/v1/settings/locations/{location_id}
# Returns masked token only — never the raw token
{
  "location_id": "...",
  "api_key_last4": "a1b2",   # _mask_key() output
  "notification_channels": {...}
}

# PUT /api/v1/settings/locations/{location_id}
# Accepts the raw token on write, stores it in Supabase, never echoes it back
```

### Supabase `locations` Table (Additions Required)

```sql
-- Column to add when JobTread integration is built:
ALTER TABLE locations
    ADD COLUMN jobtread_api_key TEXT;  -- Encrypted at rest by Supabase, never returned to frontend
```

### `shared/constants.py` (Additions Required)

```python
JOBTREAD_RATE_LIMIT_PER_KEY      = "5/s"   # Conservative — JobTread rate limit not documented
JOBTREAD_WEBHOOK_TIMEOUT_SECONDS = 10
```

Always read rate limit values from `shared/constants.py`. Do not hardcode them in
task decorators. If JobTread documents their rate limit in future, update the constant
and redeploy — do not change the value in individual task files.

## 5. Common Operations

### Add or Update a Location's JobTread API Token (via UI)

1. Log in to OmniDrop at `app.omnidrop.dev`.
2. Navigate to `/settings`.
3. Select the location from the location picker.
4. In the **JobTread API Token** field, paste the token from JobTread.
5. Click **Save**. The backend stores the token in Supabase and returns only `api_key_last4`.
6. The displayed value `****XXXX` confirms the token was saved.

### Verify a Location's Token is Set (Developer)

```sql
-- Run in Supabase SQL Editor
SELECT id, name, api_key_last4
FROM locations
WHERE organization_id = '<org_id>';
-- api_key_last4 = NULL means no token has been entered yet
-- Never SELECT jobtread_api_key directly — use the masked column
```

### Manually Trigger a Document Fetch (Developer)

```python
# Fire the task directly from a Python shell or test
from backend.workers.intake_tasks import fetch_jobtread_document

result = fetch_jobtread_document.delay(
    location_id="<location_uuid>",
    project_id="<jobtread_project_id>",
    invoice_id="<jobtread_invoice_id>",  # or None for project-only events
)
print(result.get(timeout=30))  # bytes on success
```

### Check JobTread API Connectivity for a Location

```bash
# Retrieve the token from Supabase first (server-side only), then:
curl -X GET "https://api.jobtread.com/projects/<project_id>" \
  -H "Authorization: Bearer <api_token>" \
  -o /dev/null -w "%{http_code}\n"
# 200 = token is valid and project exists
# 401 = token is invalid or expired
# 403 = token valid but does not have access to this resource
```

### Replay a Missed Webhook Event

Webhook replay is handled via Hookdeck, not JobTread. See `docs/references/hookdeck.md`
SOP-HOOKDECK-1 and the Hookdeck dashboard **Events → Retry** flow.

### Test the Full Webhook-to-Pipeline Flow (Local Dev)

```bash
# 1. Start FastAPI locally
uvicorn backend.api.main:app --reload --port 8000

# 2. Start Celery worker
celery -A backend.workers.celery_app worker --loglevel=info

# 3. Start Hookdeck local tunnel (see docs/references/hookdeck.md SOP-HOOKDECK-3)
hookdeck listen 8000 jobtread-source

# 4. Send a test event from the Hookdeck dashboard → "Send Test Event"
# 5. Watch FastAPI logs for "process_document started" and Celery logs for task pickup
```

## 6. Error Handling & Monitoring

### JobTread API Error Codes

| HTTP Status | Meaning | Action |
|---|---|---|
| `200` | Success | Continue pipeline |
| `401` | Bearer token invalid or expired | Log error, mark job `status='error'`, alert via Sentry; client must update token in `/settings` |
| `403` | Token valid, insufficient permissions | Log error, mark job `status='error'`; client must check JobTread API token scopes |
| `404` | Entity not found | Log `entity_not_found`, mark job `status='error'`; may indicate a deleted project/invoice on the JobTread side |
| `429` | Rate limit hit | Celery retries with backoff; Sentry captures via `failed_request_status_codes={429}`; reduce `JOBTREAD_RATE_LIMIT_PER_KEY` in `shared/constants.py` if 429s are frequent |
| `5xx` | JobTread server error | Celery retries with exponential backoff up to `max_retries`; alert if sustained |

### Rate Limit Monitoring

```python
# backend/core/sentry.py — 429s are captured as error events
sentry_sdk.init(
    dsn=settings.sentry_python_dsn,
    integrations=[FastApiIntegration(), CeleryIntegration()],
    failed_request_status_codes={429},   # Triggers a Sentry event on every 429
)
```

Set a Sentry alert rule: **more than 3 `429` events in 60 seconds** → page on-call.
Because JobTread's rate limit is undocumented, use a lower threshold than AccuLynx.
Any sustained 429 pattern should prompt a conversation with JobTread support to
confirm the actual limit before adjusting `JOBTREAD_RATE_LIMIT_PER_KEY`.

### Common Failure Patterns

| Symptom | Likely Cause | Resolution |
|---|---|---|
| `fetch_jobtread_document` fails with `401` | Location's bearer token expired or rotated | Client updates token in `/settings`; Sentry alert fires |
| `fetch_jobtread_document` returns `429` | Rate limit exceeded — limit is undocumented | Reduce `JOBTREAD_RATE_LIMIT_PER_KEY` in `shared/constants.py`; confirm actual limit with JobTread support |
| Job stuck at `status='processing'`, no Celery activity | Worker not running or Redis connection lost | Check `omnidrop-worker` logs in Render; verify `omnidrop-redis` is running |
| `422 Unprocessable Entity` on webhook endpoint | Payload shape mismatch (JobTread schema changed) | Inspect raw event in Hookdeck dashboard; update `shared/models/jobtread.py` if schema has changed |
| `401 Invalid webhook signature` on webhook endpoint | `HOOKDECK_SIGNING_SECRET` mismatch | See `docs/references/hookdeck.md` SOP-HOOKDECK-1 |
| No token found for `location_id` | Client has not set their JobTread API token yet | Log `missing_jobtread_token`, mark job `status='error'`; the frontend should surface this via onboarding |

### Structured Logging

Always include `location_id`, `project_id`, and `invoice_id` in log entries for
JobTread operations — these are the primary trace keys when investigating pipeline
failures.

```python
import structlog
log = structlog.get_logger()

log.info(
    "fetch_jobtread_document.started",
    location_id=location_id,
    project_id=project_id,
    invoice_id=invoice_id,
)
log.error(
    "fetch_jobtread_document.failed",
    location_id=location_id,
    project_id=project_id,
    status_code=response.status_code,
    exc_info=True,
)
```

### Sentry Alerts to Configure

| Alert | Condition |
|---|---|
| JobTread 429 spike | More than 3 `429` events in 60 seconds (lower threshold — rate limit undocumented) |
| Token auth failure | More than 3 `401` errors from `fetch_jobtread_document` in 10 minutes |
| Document fetch error rate | More than 10% of `fetch_jobtread_document` tasks in error state |

Configure these in Sentry under **Alerts → Alert Rules** for the backend project.

## 7. SOPs

### SOP-JOBTREAD-1: Onboard a New Location (Client Adds Their API Token)

**When:** A new client location is provisioned in OmniDrop and JobTread webhooks
are not yet flowing.
**Time:** ~10 minutes
**Prerequisite:** The location row exists in the Supabase `locations` table (created
during onboarding wizard step 2). The client has their JobTread API token ready.

Step 1. Have the client log in to OmniDrop at `app.omnidrop.dev`.

Step 2. Navigate to `/settings`.

Step 3. Select the new location from the location picker.

Step 4. In the **JobTread API Token** field, paste the token. The client can find this
in JobTread at: **Settings → Integrations → API Token → Copy**.

Step 5. Click **Save**. The displayed value changes to `****XXXX` (last 4 characters).

Step 6. Verify the token is stored correctly:
```sql
-- Supabase SQL Editor
SELECT id, name, api_key_last4
FROM locations
WHERE id = '<location_uuid>';
-- api_key_last4 should now be non-null
```

Step 7. Trigger a test webhook from JobTread or use Hookdeck **"Send Test Event"**
to confirm the full flow works for this location.

Step 8. Confirm in the Celery logs (Render → `omnidrop-worker` → Logs) that
`fetch_jobtread_document` completed without a `401` error.

Step 9. Tell Claude: `"SOP-JOBTREAD-1 complete. Location [name/id] API token configured. Resume [current task name]."`

Done when: a test event flows through the pipeline and the job appears in the OmniDrop
ops dashboard.

If `fetch_jobtread_document` returns `401` after the token is set: the token may have
been pasted with extra whitespace. Ask the client to re-copy from JobTread and save
again in `/settings`.

---

### SOP-JOBTREAD-2: Rotate a Location's JobTread API Token

**When:** A client's JobTread API token has been revoked, rotated, or is returning
`401` errors.
**Time:** ~5 minutes
**Prerequisite:** The client has the new token from JobTread and can log in to OmniDrop.

Step 1. Have the client log in at `app.omnidrop.dev` and navigate to `/settings`.

Step 2. Select the affected location.

Step 3. In the **JobTread API Token** field, paste the new token.

Step 4. Click **Save**. Confirm the `api_key_last4` display updates.

Step 5. Verify the `401` errors stop in Sentry (Sentry → Issues → filter by
`fetch_jobtread_document`). New events should process successfully within 1–2 minutes
as Celery retries queued tasks.

Step 6. If any jobs were stuck in `status='error'` due to the bad token, replay them:
```sql
-- Identify affected jobs
SELECT id, status, location_id, created_at
FROM jobs
WHERE location_id = '<location_uuid>'
  AND status = 'error'
  AND created_at > now() - interval '24 hours';
```
Then replay via Hookdeck dashboard for any missed webhook events.

Step 7. Tell Claude: `"SOP-JOBTREAD-2 complete. Location [name/id] token rotated. 401 errors resolved. Resume [current task name]."`

Done when: `fetch_jobtread_document` tasks for this location complete without errors.

---

### SOP-JOBTREAD-3: Investigate a Stalled Document Pipeline

**When:** A project or invoice was updated in JobTread but never appears in the
OmniDrop dashboard and no error is visible.
**Time:** ~15 minutes
**Prerequisite:** You have the JobTread `project_id` and/or `invoice_id` for the
stalled document.

Step 1. Check the Hookdeck dashboard for the webhook event:
- Log in to https://dashboard.hookdeck.com
- **Sources → jobtread-source → Events**
- Search for the `project_id`. Confirm the event was received and its delivery status.

Step 2. If the event shows **"Failed"** delivery: the FastAPI endpoint returned a
non-200. Check the `omnidrop-api` logs in Render for the error. Common causes:
- `401` = `HOOKDECK_SIGNING_SECRET` mismatch (see `docs/references/hookdeck.md` SOP-HOOKDECK-1)
- `422` = Payload schema mismatch (inspect the raw event body in Hookdeck)

Step 3. If the event shows **"Successful"** delivery but the job is not in Supabase:
check the Celery worker logs:
```bash
# Render dashboard → omnidrop-worker → Logs
# Search for the project_id
```

Step 4. If no Celery log entry exists for the `project_id`: the task was never dispatched
or was dropped. Check Redis queue depth via Flower:
```
https://omnidrop-flower.onrender.com
```

Step 5. If the task is in the queue but not processing: the worker may be rate-limited.
JobTread's rate limit is undocumented — check Flower for 429 error patterns. If 429s
are present, reduce `JOBTREAD_RATE_LIMIT_PER_KEY` in `shared/constants.py` and
redeploy workers.

Step 6. If the task shows as **"FAILURE"** in Flower: expand the traceback. The most
common causes are:
- `401 Unauthorized` from JobTread = bad or expired token (follow SOP-JOBTREAD-2)
- `404 Not Found` from JobTread = project/invoice was deleted in JobTread
- `429 Too Many Requests` = rate limit hit (reduce `JOBTREAD_RATE_LIMIT_PER_KEY`)
- Missing `location_id` token in Supabase `locations` table (follow SOP-JOBTREAD-1)

Step 7. Once the root cause is resolved, replay the webhook event from the Hookdeck
dashboard (**"Retry"** on the event) or trigger a new update in JobTread.

Step 8. Confirm the job appears in the OmniDrop ops dashboard within 1–2 minutes.

Step 9. Tell Claude: `"SOP-JOBTREAD-3 complete. Stalled document [project_id/invoice_id] resolved: [root cause]. Resume [current task name]."`

Done when: the job row exists in Supabase with `status` progressed past `'processing'`.
