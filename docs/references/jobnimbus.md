# JobNimbus — OmniDrop Reference

## 1. Overview

**Future Integration — Not Yet Implemented.** OmniDrop currently integrates only
with AccuLynx. JobNimbus support is planned and this document establishes the
integration pattern to follow when it is built.

JobNimbus is a CRM platform used by roofing and exterior contractors to manage
contacts, jobs, and tasks. The OmniDrop integration will receive job, task, and
contact events from JobNimbus webhooks and route them through the same Celery
processing pipeline used for AccuLynx.

**Inbound flow (webhooks):** JobNimbus POSTs job, task, and contact events to a
Hookdeck source URL. Hookdeck re-signs the event and forwards it to
`POST /api/v1/webhooks/jobnimbus`. The webhook payload includes a `location_id`
and relevant entity IDs that the Celery pipeline uses to fetch document data via
the JobNimbus REST API.

**Multi-tenant architecture:** JobNimbus API keys are per-location, per-client.
There is no global key. Each client location stores its own JobNimbus API key in
the Supabase `locations` table, fetched at task runtime by `location_id`. The
`/settings` UI lets clients enter and update their keys.

**Auth method:** API key passed as `Authorization: ApiKey {key}` header.

**Base URL:** `https://app.jobnimbus.com/api1/`

Files that will touch JobNimbus (when built):
- `shared/models/jobnimbus.py` — webhook payload Pydantic models
- `backend/api/v1/webhooks.py` — webhook ingestion endpoint
- `backend/api/v1/settings.py` — location key management (masked on read)
- `backend/workers/intake_tasks.py` — `fetch_jobnimbus_document` Celery task
- `shared/constants.py` — rate limit constants

## 2. Credentials & Environment Variables

JobNimbus API keys are **not** stored in the `omnidrop-secrets` environment group
and are **not** set as application-level environment variables. They are per-location
secrets entered by the client via `/settings` and stored in the Supabase `locations`
table, column `jobnimbus_api_key`.

| Field | Storage | Exposed To |
|---|---|---|
| `jobnimbus_api_key` | Supabase `locations` table, fetched by `location_id` at task runtime | Backend workers only — never returned in API responses |
| `api_key_last4` | Derived by `_mask_key()` in `backend/api/v1/settings.py` | Frontend `/settings` page (read-only display) |

**There is no `JOBNIMBUS_API_KEY` environment variable in OmniDrop. Do not create one.**

### How keys are stored and retrieved

```python
# backend/api/v1/settings.py — storing a key (write path)
def _mask_key(key: str) -> str:
    """Returns only the last 4 characters for safe display."""
    return f"****{key[-4:]}"

# backend/workers/intake_tasks.py — retrieving a key at task runtime
async def _get_jobnimbus_api_key(location_id: str) -> str:
    """Fetch the JobNimbus API key for a location from Supabase."""
    result = await supabase_client.table("locations") \
        .select("jobnimbus_api_key") \
        .eq("id", location_id) \
        .single() \
        .execute()
    return result.data["jobnimbus_api_key"]
```

**Key security rules:**
- `jobnimbus_api_key` is NEVER returned in any API response.
- The `/settings` endpoint only returns `api_key_last4`.
- `SUPABASE_SERVICE_ROLE_KEY` is the only server credential required to read
  location keys — it must never be exposed to the frontend.

### Credential value

The JobNimbus API key for each location is entered by the client at:
`/settings` → Location → JobNimbus API Key field.

Each client retrieves their key from: JobNimbus → **Settings → API Keys → Generate Key**.
Actual key values: [ASK USER] (per location, client-provided).

## 3. Key Concepts

### Multi-Tenant Location Model

OmniDrop serves organisations with multiple contractor locations (branches). Each
location maps to one row in the Supabase `locations` table and holds exactly one
JobNimbus API key. When a webhook arrives, `location_id` in the OmniDrop payload
is the link between the event and the correct API key.

```
organizations
  └── locations (one row per branch, one jobnimbus_api_key per row)
        ├── id (location_id referenced in every webhook and Celery task)
        ├── jobnimbus_api_key (fetched at task runtime, never in env vars)
        └── notification_channels JSONB (Slack webhook URL, future adapters)
```

### Webhook Flow

OmniDrop never receives JobNimbus webhooks directly. The full path:

```
JobNimbus → Hookdeck source URL → Hookdeck verifies JobNimbus signature
          → Hookdeck re-signs → POST /api/v1/webhooks/jobnimbus
          → FastAPI verifies Hookdeck HMAC → Pydantic validates payload
          → process_document.delay() → 200 OK
```

See `docs/references/hookdeck.md` for the HMAC verification implementation.

### Supported Webhook Events

| Event | Description |
|---|---|
| `job.created` | New job created in JobNimbus |
| `job.updated` | Existing job modified |
| `task.created` | New task created |
| `task.updated` | Existing task modified |
| `contact.created` | New contact created |
| `contact.updated` | Existing contact modified |

### Rate Limits

| Limit | Value | Enforcement |
|---|---|---|
| Per API key | 100 req/min | Celery `rate_limit="10/s"` on fetch tasks (conservative) |
| 429 monitoring | — | Sentry `failed_request_status_codes={429}` |

All JobNimbus API calls MUST go through Celery tasks. Synchronous calls outside a
Celery task are prohibited — they bypass rate limiting and will hit the per-key
ceiling under any real load.

### Celery Rate Limit Pattern

```python
# backend/workers/intake_tasks.py
@celery_app.task(rate_limit="10/s")
def fetch_jobnimbus_document(location_id: str, job_id: str):
    """
    Fetch document/job data from JobNimbus API.
    API key is fetched from Supabase using location_id — never from env vars.
    """
    api_key = _get_jobnimbus_api_key(location_id)
    ...
```

The `rate_limit="10/s"` decorator is enforced per Celery worker process.
`shared/constants.py` holds the canonical rate limit values — do not hardcode them
elsewhere.

### Webhook Payload Shape (Planned)

To be defined in `shared/models/jobnimbus.py`:

```python
class JobNimbusJobEvent(BaseModel):
    event_type: str        # e.g. "job.created", "task.updated", "contact.created"
    record_id: str         # JobNimbus entity ID (job, task, or contact)
    record_type: str       # "job" | "task" | "contact"
    location_id: str       # OmniDrop location UUID — maps to Supabase locations row
    timestamp: datetime
    data: dict[str, Any]

class JobNimbusWebhookPayload(BaseModel):
    event: JobNimbusJobEvent
    version: str           # default "1.0"
```

`location_id` in the event body is the key that ties the webhook to the correct
JobNimbus API key and Supabase org.

## 4. Integration Points

### Webhook Ingestion (`backend/api/v1/webhooks.py`)

This endpoint MUST do exactly four things in order — no exceptions:

```python
@router.post("/jobnimbus")
async def jobnimbus_webhook(
    request: Request,
    _: None = Depends(verify_hookdeck_signature),       # 1. Verify HMAC → 401 if invalid
    payload: JobNimbusWebhookPayload = ...,              # 2. Validate Pydantic → 422 if malformed
):
    process_document.delay(payload.event)               # 3. Dispatch to Celery
    return {"status": "ok"}                             # 4. Return 200 immediately

# This endpoint NEVER calls Unstructured.io, Claude, or Supabase. No exceptions.
```

### Document Fetch Task (`backend/workers/intake_tasks.py`)

```python
@celery_app.task(rate_limit="10/s")
def fetch_jobnimbus_document(location_id: str, job_id: str) -> bytes:
    api_key = _get_jobnimbus_api_key(location_id)   # Fetched from Supabase, not env
    response = httpx.get(
        f"https://app.jobnimbus.com/api1/jobs/{job_id}",
        headers={"Authorization": f"ApiKey {api_key}"},
        timeout=30,
    )
    response.raise_for_status()
    return response.content
```

### Location Key Management (`backend/api/v1/settings.py`)

```python
# GET /api/v1/settings/locations/{location_id}
# Returns masked key only — never the raw key
{
  "location_id": "...",
  "api_key_last4": "a1b2",   # _mask_key() output
  "notification_channels": {...}
}

# PUT /api/v1/settings/locations/{location_id}
# Accepts the raw key on write, stores it in Supabase, never echoes it back
```

### Supabase `locations` Table (Additions Required)

```sql
-- Column to add when JobNimbus integration is built:
ALTER TABLE locations
    ADD COLUMN jobnimbus_api_key TEXT;  -- Encrypted at rest by Supabase, never returned to frontend
```

### `shared/constants.py` (Additions Required)

```python
JOBNIMBUS_RATE_LIMIT_PER_KEY      = "10/s"   # Conservative vs 100/min published limit
JOBNIMBUS_WEBHOOK_TIMEOUT_SECONDS = 10
```

Always read rate limit values from `shared/constants.py`. Do not hardcode them in
task decorators.

## 5. Common Operations

### Add or Update a Location's JobNimbus API Key (via UI)

1. Log in to OmniDrop at `app.omnidrop.dev`.
2. Navigate to `/settings`.
3. Select the location from the location picker.
4. In the **JobNimbus API Key** field, paste the key from JobNimbus.
5. Click **Save**. The backend stores the key in Supabase and returns only `api_key_last4`.
6. The displayed value `****XXXX` confirms the key was saved.

### Verify a Location's Key is Set (Developer)

```sql
-- Run in Supabase SQL Editor
SELECT id, name, api_key_last4
FROM locations
WHERE organization_id = '<org_id>';
-- api_key_last4 = NULL means no key has been entered yet
-- Never SELECT jobnimbus_api_key directly — use the masked column
```

### Manually Trigger a Document Fetch (Developer)

```python
# Fire the task directly from a Python shell or test
from backend.workers.intake_tasks import fetch_jobnimbus_document

result = fetch_jobnimbus_document.delay(
    location_id="<location_uuid>",
    job_id="<jobnimbus_job_id>",
)
print(result.get(timeout=30))  # bytes on success
```

### Check JobNimbus API Connectivity for a Location

```bash
# Retrieve the key from Supabase first (server-side only), then:
curl -X GET "https://app.jobnimbus.com/api1/jobs/<job_id>" \
  -H "Authorization: ApiKey <api_key>" \
  -o /dev/null -w "%{http_code}\n"
# 200 = key is valid and job exists
# 401 = key is invalid or expired
# 403 = key valid but does not have access to this resource
```

### Replay a Missed Webhook Event

Webhook replay is handled via Hookdeck, not JobNimbus. See `docs/references/hookdeck.md`
SOP-HOOKDECK-1 and the Hookdeck dashboard **Events → Retry** flow.

### Test the Full Webhook-to-Pipeline Flow (Local Dev)

```bash
# 1. Start FastAPI locally
uvicorn backend.api.main:app --reload --port 8000

# 2. Start Celery worker
celery -A backend.workers.celery_app worker --loglevel=info

# 3. Start Hookdeck local tunnel (see docs/references/hookdeck.md SOP-HOOKDECK-3)
hookdeck listen 8000 jobnimbus-source

# 4. Send a test event from the Hookdeck dashboard → "Send Test Event"
# 5. Watch FastAPI logs for "process_document started" and Celery logs for task pickup
```

## 6. Error Handling & Monitoring

### JobNimbus API Error Codes

| HTTP Status | Meaning | Action |
|---|---|---|
| `200` | Success | Continue pipeline |
| `401` | API key invalid or expired | Log error, mark job `status='error'`, alert via Sentry; client must update key in `/settings` |
| `403` | Key valid, insufficient permissions | Log error, mark job `status='error'`; client must check JobNimbus API key permissions |
| `404` | Entity not found | Log `entity_not_found`, mark job `status='error'`; may indicate a deleted record on the JobNimbus side |
| `429` | Rate limit hit | Celery retries with backoff; Sentry captures via `failed_request_status_codes={429}` |
| `5xx` | JobNimbus server error | Celery retries with exponential backoff up to `max_retries`; alert if sustained |

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
JobNimbus has a lower published rate limit (100 req/min) than AccuLynx, so a single
location generating high document volume can hit this ceiling quickly. Review
`shared/constants.py` if 429s become frequent.

### Common Failure Patterns

| Symptom | Likely Cause | Resolution |
|---|---|---|
| `fetch_jobnimbus_document` fails with `401` | Location's API key expired or rotated | Client updates key in `/settings`; Sentry alert fires |
| Job stuck at `status='processing'`, no Celery activity | Worker not running or Redis connection lost | Check `omnidrop-worker` logs in Render; verify `omnidrop-redis` is running |
| `422 Unprocessable Entity` on webhook endpoint | Payload shape mismatch (JobNimbus schema changed) | Inspect raw event in Hookdeck dashboard; update `shared/models/jobnimbus.py` if schema has changed |
| `401 Invalid webhook signature` on webhook endpoint | `HOOKDECK_SIGNING_SECRET` mismatch | See `docs/references/hookdeck.md` SOP-HOOKDECK-1 |
| Celery task never picks up `fetch_jobnimbus_document` | `rate_limit="10/s"` queue at capacity | Check Flower (`omnidrop-flower.onrender.com`) for queue depth; scale worker concurrency if needed |
| No key found for `location_id` | Client has not set their JobNimbus API key yet | Log `missing_jobnimbus_key`, mark job `status='error'`; the frontend should surface this via onboarding |

### Structured Logging

Always include `location_id`, `job_id`, and `record_type` in log entries for
JobNimbus operations — these are the primary trace keys when investigating pipeline
failures.

```python
import structlog
log = structlog.get_logger()

log.info(
    "fetch_jobnimbus_document.started",
    location_id=location_id,
    job_id=job_id,
    record_type=record_type,
)
log.error(
    "fetch_jobnimbus_document.failed",
    location_id=location_id,
    job_id=job_id,
    status_code=response.status_code,
    exc_info=True,
)
```

### Sentry Alerts to Configure

| Alert | Condition |
|---|---|
| JobNimbus 429 spike | More than 5 `429` events in 60 seconds |
| Key auth failure | More than 3 `401` errors from `fetch_jobnimbus_document` in 10 minutes |
| Document fetch error rate | More than 10% of `fetch_jobnimbus_document` tasks in error state |

Configure these in Sentry under **Alerts → Alert Rules** for the backend project.

## 7. SOPs

### SOP-JOBNIMBUS-1: Onboard a New Location (Client Adds Their API Key)

**When:** A new client location is provisioned in OmniDrop and JobNimbus webhooks
are not yet flowing.
**Time:** ~10 minutes
**Prerequisite:** The location row exists in the Supabase `locations` table (created
during onboarding wizard step 2). The client has their JobNimbus API key ready.

Step 1. Have the client log in to OmniDrop at `app.omnidrop.dev`.

Step 2. Navigate to `/settings`.

Step 3. Select the new location from the location picker.

Step 4. In the **JobNimbus API Key** field, paste the key. The client can find this
in JobNimbus at: **Settings → API Keys → Generate Key → Copy**.

Step 5. Click **Save**. The displayed value changes to `****XXXX` (last 4 characters).

Step 6. Verify the key is stored correctly:
```sql
-- Supabase SQL Editor
SELECT id, name, api_key_last4
FROM locations
WHERE id = '<location_uuid>';
-- api_key_last4 should now be non-null
```

Step 7. Trigger a test webhook from JobNimbus or use Hookdeck **"Send Test Event"**
to confirm the full flow works for this location.

Step 8. Confirm in the Celery logs (Render → `omnidrop-worker` → Logs) that
`fetch_jobnimbus_document` completed without a `401` error.

Step 9. Tell Claude: `"SOP-JOBNIMBUS-1 complete. Location [name/id] API key configured. Resume [current task name]."`

Done when: a test event flows through the pipeline and the job appears in the OmniDrop
ops dashboard.

If `fetch_jobnimbus_document` returns `401` after the key is set: the key may have
been pasted with extra whitespace. Ask the client to re-copy from JobNimbus and save
again in `/settings`.

---

### SOP-JOBNIMBUS-2: Rotate a Location's JobNimbus API Key

**When:** A client's JobNimbus API key has been revoked, rotated, or is returning
`401` errors.
**Time:** ~5 minutes
**Prerequisite:** The client has the new key from JobNimbus and can log in to OmniDrop.

Step 1. Have the client log in at `app.omnidrop.dev` and navigate to `/settings`.

Step 2. Select the affected location.

Step 3. In the **JobNimbus API Key** field, paste the new key.

Step 4. Click **Save**. Confirm the `api_key_last4` display updates.

Step 5. Verify the `401` errors stop in Sentry (Sentry → Issues → filter by
`fetch_jobnimbus_document`). New events should process successfully within 1–2 minutes
as Celery retries queued tasks.

Step 6. If any jobs were stuck in `status='error'` due to the bad key, replay them:
```sql
-- Identify affected jobs
SELECT id, status, location_id, created_at
FROM jobs
WHERE location_id = '<location_uuid>'
  AND status = 'error'
  AND created_at > now() - interval '24 hours';
```
Then replay via Hookdeck dashboard for any missed webhook events.

Step 7. Tell Claude: `"SOP-JOBNIMBUS-2 complete. Location [name/id] key rotated. 401 errors resolved. Resume [current task name]."`

Done when: `fetch_jobnimbus_document` tasks for this location complete without errors.

---

### SOP-JOBNIMBUS-3: Investigate a Stalled Document Pipeline

**When:** A job or contact was updated in JobNimbus but never appears in the OmniDrop
dashboard and no error is visible.
**Time:** ~15 minutes
**Prerequisite:** You have the JobNimbus `record_id` and `record_type` for the stalled
document.

Step 1. Check the Hookdeck dashboard for the webhook event:
- Log in to https://dashboard.hookdeck.com
- **Sources → jobnimbus-source → Events**
- Search for the `record_id`. Confirm the event was received and its delivery status.

Step 2. If the event shows **"Failed"** delivery: the FastAPI endpoint returned a
non-200. Check the `omnidrop-api` logs in Render for the error. Common causes:
- `401` = `HOOKDECK_SIGNING_SECRET` mismatch (see `docs/references/hookdeck.md` SOP-HOOKDECK-1)
- `422` = Payload schema mismatch (inspect the raw event body in Hookdeck)

Step 3. If the event shows **"Successful"** delivery but the job is not in Supabase:
check the Celery worker logs:
```bash
# Render dashboard → omnidrop-worker → Logs
# Search for the record_id
```

Step 4. If no Celery log entry exists for the `record_id`: the task was never dispatched
or was dropped. Check Redis queue depth via Flower:
```
https://omnidrop-flower.onrender.com
```

Step 5. If the task is in the queue but not processing: the worker may be rate-limited
or at capacity. Check Flower for worker status and active task count. Note: JobNimbus
has a lower rate limit (100 req/min) than AccuLynx — high-volume locations may saturate
the queue faster.

Step 6. If the task shows as **"FAILURE"** in Flower: expand the traceback. The most
common causes are:
- `401 Unauthorized` from JobNimbus = bad API key (follow SOP-JOBNIMBUS-2)
- `404 Not Found` from JobNimbus = record was deleted in JobNimbus
- Missing `location_id` key in Supabase `locations` table (follow SOP-JOBNIMBUS-1)

Step 7. Once the root cause is resolved, replay the webhook event from the Hookdeck
dashboard (**"Retry"** on the event) or trigger a new update in JobNimbus.

Step 8. Confirm the job appears in the OmniDrop ops dashboard within 1–2 minutes.

Step 9. Tell Claude: `"SOP-JOBNIMBUS-3 complete. Stalled document [record_id] resolved: [root cause]. Resume [current task name]."`

Done when: the job row exists in Supabase with `status` progressed past `'processing'`.
