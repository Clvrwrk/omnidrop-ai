# Hookdeck — OmniDrop Reference

## 1. What It Does Here

Hookdeck is the webhook gateway that sits between AccuLynx and OmniDrop's FastAPI
backend. AccuLynx POSTs job events to a Hookdeck source URL; Hookdeck immediately
ACKs AccuLynx (preventing timeouts), queues the event, re-signs it with a separate
Hookdeck signing secret, then forwards it to `POST /api/v1/webhooks/acculynx` on
the OmniDrop backend. This two-layer architecture means the FastAPI endpoint only
ever verifies the Hookdeck HMAC signature — it never sees the raw AccuLynx secret.

Hookdeck also provides automatic retries with exponential backoff if the backend is
temporarily unavailable, a web dashboard for replaying failed events, and a CLI for
local development tunnelling without exposing a public URL.

Files that touch Hookdeck:
- `backend/core/security.py` — `verify_hookdeck_signature()` FastAPI dependency
- `backend/api/v1/webhooks.py` — the single endpoint that consumes Hookdeck deliveries
- `shared/constants.py` — `HOOKDECK_SIGNATURE_HEADER = "x-hookdeck-signature"`
- `backend/core/config.py` — `HOOKDECK_SIGNING_SECRET` setting

## 2. Credentials & Environment Variables

| Variable | Where to Find It | Used By |
|---|---|---|
| `HOOKDECK_SIGNING_SECRET` | Hookdeck Dashboard → your connection → **"Signing Secret"** tab | Backend only — the secret used to verify Hookdeck delivery signatures |

**Two secrets are involved — do not confuse them:**

| Secret | What It Is | Where It Lives |
|---|---|---|
| AccuLynx webhook secret | The secret AccuLynx uses when signing events it sends to Hookdeck | Configured in the Hookdeck **source** settings (AccuLynx side). OmniDrop backend never sees this directly. |
| Hookdeck signing secret | The secret Hookdeck uses when re-signing forwarded events to OmniDrop | `HOOKDECK_SIGNING_SECRET` in OmniDrop `.env` |

**Actual secret value:** [ASK USER] — retrieve via SOP-HOOKDECK-1 below.

## 3. CLI

```bash
# Install the Hookdeck CLI
npm install -g hookdeck-cli
# or
brew install hookdeck/hookdeck/hookdeck

# Authenticate (opens browser)
hookdeck login

# Forward Hookdeck events to your local FastAPI server (port 8000)
# Creates a temporary public URL → routes to localhost
hookdeck listen 8000 acculynx-source
# "acculynx-source" is the name of your Hookdeck source — replace if yours differs

# List all sources in the workspace
hookdeck get sources

# List all connections (source → destination pairings)
hookdeck get connections

# List recent events and their delivery status
hookdeck get events

# Replay a specific failed event by event ID
hookdeck replay <event-id>

# Tail live event logs to the terminal
hookdeck tail

# Check CLI version
hookdeck --version
```

## 4. MCP (Claude Code)

Hookdeck has no MCP server. Use the CLI for local development and the dashboard
for production event management. For documentation lookups:

| Operation | Preferred Tool | Example |
|---|---|---|
| Look up Hookdeck signing docs | `mcp__plugin_context7_context7__resolve-library-id` then `mcp__plugin_context7_context7__query-docs` | `{ "query": "hookdeck webhook signature verification" }` |

## 5. Direct API

Hookdeck exposes a management REST API at `https://api.hookdeck.com/latest/`. Use
it for programmatic event replay or source inspection. The CLI wraps most of these
operations — curl is for debugging only.

```bash
# List all events (requires Hookdeck API key — different from signing secret)
curl -X GET "https://api.hookdeck.com/latest/events" \
  -u "$HOOKDECK_API_KEY:"

# Retrieve a specific event by ID
curl -X GET "https://api.hookdeck.com/latest/events/<event-id>" \
  -u "$HOOKDECK_API_KEY:"

# Manually retry a failed event
curl -X POST "https://api.hookdeck.com/latest/events/<event-id>/retry" \
  -u "$HOOKDECK_API_KEY:"

# List all connections
curl -X GET "https://api.hookdeck.com/latest/connections" \
  -u "$HOOKDECK_API_KEY:"
```

Note: `HOOKDECK_API_KEY` (for the management API) is separate from
`HOOKDECK_SIGNING_SECRET` (for signature verification). The management API key is
only needed for CLI auth and programmatic replays — it is not used in application
code.

## 6. OmniDrop-Specific Patterns

### Signature verification (the production implementation)

```python
# backend/core/security.py
import hashlib
import hmac
from fastapi import HTTPException, Request, status
from shared.constants import HOOKDECK_SIGNATURE_HEADER  # "x-hookdeck-signature"

async def verify_hookdeck_signature(request: Request) -> None:
    """
    FastAPI dependency. Call this first in the webhook endpoint.
    Raises HTTP 401 if the signature is missing or invalid.
    """
    signature_header = request.headers.get(HOOKDECK_SIGNATURE_HEADER)
    if not signature_header:
        raise HTTPException(status_code=401, detail="Missing webhook signature")

    raw_body = await request.body()
    settings = get_settings()

    expected = hmac.new(
        settings.hookdeck_signing_secret.encode(),  # HOOKDECK_SIGNING_SECRET
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    provided = signature_header.removeprefix("sha256=")

    if not hmac.compare_digest(expected, provided):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
```

Key implementation details:
- Header name: `x-hookdeck-signature` (from `shared/constants.py`)
- Signature format: `sha256=<hex-digest>` — strip the prefix before comparing
- Always use `hmac.compare_digest()` — prevents timing attacks
- Sign the **raw request body bytes** — never the parsed JSON

### Webhook endpoint contract (non-negotiable per CLAUDE.md)

```python
# backend/api/v1/webhooks.py — must do exactly these four things in order:
@router.post("/acculynx")
async def acculynx_webhook(
    request: Request,
    _: None = Depends(verify_hookdeck_signature),   # 1. Verify HMAC → 401 if invalid
    payload: AccuLynxWebhookPayload = ...,           # 2. Validate Pydantic → 422 if malformed
):
    process_document.delay(job_payload)              # 3. Dispatch to Celery
    return {"status": "ok"}                         # 4. Return 200 immediately

# This endpoint NEVER calls Unstructured.io, Claude, or Supabase. No exceptions.
```

### Accepted webhook payload shape

Hookdeck forwards the AccuLynx event body unchanged. OmniDrop validates it with
`AccuLynxWebhookPayload` from `shared/models/acculynx.py`:

```python
# shared/models/acculynx.py
class AccuLynxJobEvent(BaseModel):
    event_type: str       # e.g. "job.created", "document.uploaded"
    job_id: str           # AccuLynx job ID
    location_id: str      # Maps to Supabase locations table
    timestamp: datetime
    document_id: str | None
    document_url: str | None  # URL to fetch document bytes from AccuLynx API
    data: dict[str, Any]

class AccuLynxWebhookPayload(BaseModel):
    event: AccuLynxJobEvent
    version: str          # default "1.0"
```

A payload missing any required field returns `422 Unprocessable Entity` — FastAPI /
Pydantic handles this automatically.

### Destination URL per environment

| Environment | Destination URL |
|---|---|
| omnidrop-dev | `https://api.omnidrop.dev/api/v1/webhooks/acculynx` |
| omnidrop-prod | `https://api.omnidrop.ai/api/v1/webhooks/acculynx` |
| Local dev | `http://localhost:8000/api/v1/webhooks/acculynx` (via `hookdeck listen`) |

### AccuLynx timeout constraint

AccuLynx retries if no HTTP response is received within **10 seconds**
(`ACCULYNX_WEBHOOK_TIMEOUT_SECONDS = 10` in `shared/constants.py`). Hookdeck ACKs
AccuLynx immediately and holds the delivery — this is why the gateway exists. The
FastAPI endpoint must still return `200` fast (under 1 second) so Hookdeck's own
delivery timeout is not breached.

### Known gotchas

- **Never verify the AccuLynx signing secret in the FastAPI endpoint.** OmniDrop
  only verifies the Hookdeck signing secret. AccuLynx secret validation happens
  inside Hookdeck's source settings — Hookdeck rejects events that fail that check
  before forwarding them.
- **`HOOKDECK_SIGNING_SECRET` rotates when you click "Rotate" in the dashboard.**
  After rotation, update the env var in Render (or your `.env`) and redeploy before
  the old secret expires — Hookdeck shows both secrets as valid during a grace
  period.
- **The signature is computed over raw bytes, not parsed JSON.** If any middleware
  parses the body before `verify_hookdeck_signature` runs, the body may be consumed
  and the HMAC will fail. FastAPI caches the body after the first `await request.body()`
  call, so this is safe within a single request — but be careful with middleware ordering.
- **`hookdeck listen` requires authentication.** If the CLI session expires, events
  will stop forwarding locally with no obvious error. Run `hookdeck login` again if
  local events stop arriving.
- **Replay from the dashboard re-sends the original body with the original
  signature.** If `HOOKDECK_SIGNING_SECRET` has been rotated since the original
  event was received, replaying it will produce a 401. Use `hookdeck replay <event-id>`
  from the CLI instead — it re-signs with the current secret.

## 7. Human SOPs

### SOP-HOOKDECK-1: Retrieve the Hookdeck Signing Secret

**When:** First-time environment setup, deploying to a new environment, or after a
key rotation.
**Time:** ~5 minutes
**Prerequisite:** You have access to the Hookdeck workspace and the relevant `.env`
file or Render environment group is open.

Step 1. Go to https://dashboard.hookdeck.com and log in.

Step 2. In the left nav, click **"Connections"**.

Step 3. Click the connection for the OmniDrop environment you are configuring
(e.g., `acculynx → omnidrop-dev`).

Step 4. Click the **"Signing Secret"** tab (or look for **"Secret"** in the
connection detail panel).

Step 5. Click **"Reveal"** next to the signing secret value. Copy the full string —
it looks like: `whsec_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX`

Step 6. Paste into your `.env` as:
`HOOKDECK_SIGNING_SECRET=whsec_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX`

Or, for Render deployment, add it to the `omnidrop-secrets` Environment Group (see
`docs/references/render.md` SOP-RENDER-1).

Step 7. Confirm `.env` is in `.gitignore`. Never commit this secret.

Step 8. Tell Claude: `"Hookdeck SOP-1 complete. HOOKDECK_SIGNING_SECRET is set for [environment]. Resume [current task name]."`

✅ Done when: a test event delivered via `hookdeck listen` reaches the local
`/api/v1/webhooks/acculynx` endpoint and returns `200 OK` in the CLI output.

⚠️ If the endpoint returns `401 Invalid webhook signature`: the secret in `.env`
does not match the current signing secret in the dashboard. Re-copy the secret from
Step 5 and verify no trailing whitespace was included.

---

### SOP-HOOKDECK-2: Point a Hookdeck Connection at a New Environment URL

**When:** Deploying to a new environment or changing the backend URL after a Render
service rename.
**Time:** ~5 minutes
**Prerequisite:** The new backend URL is live and returning `200` on `GET /health`.

Step 1. Go to https://dashboard.hookdeck.com and log in.

Step 2. In the left nav, click **"Connections"**.

Step 3. Click the connection you want to update (e.g., `acculynx → omnidrop-dev`).

Step 4. Click **"Edit"** on the destination.

Step 5. In the **"URL"** field, enter the new destination:
`https://api.omnidrop.dev/api/v1/webhooks/acculynx`
(or the prod equivalent: `https://api.omnidrop.ai/api/v1/webhooks/acculynx`)

Step 6. Click **"Save"**.

Step 7. Send a test event using the Hookdeck dashboard **"Send Test Event"** button,
or trigger a real AccuLynx event from a test job.

Step 8. Confirm the event appears in Hookdeck's **"Events"** log with status
`Successful` (green).

Step 9. Tell Claude: `"Hookdeck SOP-2 complete. Connection updated to [URL]. Resume [current task name]."`

✅ Done when: an event shows `Successful` in the Hookdeck events log and the
backend logs show `process_document started` for the corresponding job_id.

⚠️ If events show `Failed` with status `502` or `503`: the backend is not yet live
at the new URL — check the Render deploy logs before retrying.

---

### SOP-HOOKDECK-3: Set Up Local Development Forwarding

**When:** Starting a new local development session where AccuLynx webhook events
need to reach `localhost:8000`.
**Time:** ~3 minutes
**Prerequisite:** Hookdeck CLI is installed (`npm install -g hookdeck-cli`) and you
are logged in (`hookdeck login`).

Step 1. Start your local FastAPI server:
```bash
uvicorn backend.api.main:app --reload --port 8000
```

Step 2. In a second terminal, start the Hookdeck listener:
```bash
hookdeck listen 8000 acculynx-source
```
Replace `acculynx-source` with your actual Hookdeck source name if it differs.

Step 3. Hookdeck CLI will print a public URL like:
`https://events.hookdeck.com/e/src_XXXXXXXXXXXXXXXXX`
Events sent to the Hookdeck source will forward to this tunnel.

Step 4. Trigger a test event from the Hookdeck dashboard (**"Send Test Event"**
on the source) or send a real event from AccuLynx.

Step 5. Confirm in the FastAPI terminal that the request arrived and returned `200`.

Step 6. Tell Claude: `"Hookdeck SOP-3 complete. Local forwarding active on port 8000. Resume [current task name]."`

✅ Done when: a test event appears in the FastAPI server logs with
`process_document started` and returns `200 OK`.

⚠️ If events stop arriving mid-session: the CLI session may have expired. Run
`hookdeck login` again and restart `hookdeck listen`.
