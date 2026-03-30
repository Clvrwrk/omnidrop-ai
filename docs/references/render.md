# Render.com — OmniDrop Reference

## 1. What It Does Here

Render.com is the cloud hosting platform for the entire OmniDrop AI stack. Every
service — FastAPI backend, Celery worker, Redis broker, and Next.js frontend — runs
on Render and is defined as Infrastructure as Code in `render.yaml` at the repo root.

Render handles TLS termination, auto-scaling, health-check-based traffic routing,
and zero-downtime deploys. When a push lands on `main`, Render auto-deploys all
services in the blueprint simultaneously.

**Environment pipeline:**

| Environment | URL | Purpose |
|---|---|---|
| Dev (alpha) | `app.omnidrop.dev` | Alpha user validation, primary deploy target |
| Prod | `app.omnidrop.ai` | V1.0 production (promote from dev after validation) |

All active development targets `app.omnidrop.dev`. Do not deploy directly to prod
without explicit approval from Lead.

**Services defined in `render.yaml`:**

| Service Name | Type | Runtime | Role |
|---|---|---|---|
| `omnidrop-api` | Web service | Python | FastAPI backend — receives Hookdeck webhooks, serves API endpoints |
| `omnidrop-worker` | Background worker | Python | Celery — runs the full document processing pipeline |
| `omnidrop-redis` | Redis (Key Value) | — | Celery broker + result backend |
| `omnidrop-frontend` | Web service | Node | Next.js 15 frontend (managed in dashboard — see note below) |
| `omnidrop-flower` | Web service (optional) | Python | Flower — Celery monitoring UI, remove before prod |

Note: `omnidrop-frontend` is temporarily removed from the `render.yaml` blueprint
and is managed directly in the Render dashboard until environment group linking is
resolved. The comment in `render.yaml` has the context.

Files that touch Render:
- `render.yaml` — blueprint defining all services and env var wiring
- `backend/core/config.py` — `Pydantic BaseSettings` reads env vars injected by Render
- `backend/core/sentry.py` — reads `SENTRY_PYTHON_DSN` (set via `omnidrop-secrets`)
- `backend/workers/celery_app.py` — reads `CELERY_BROKER_URL` and `CELERY_RESULT_BACKEND`

## 2. Credentials & Environment Variables

All secrets are managed in a single Render Environment Group named `omnidrop-secrets`.
This group is linked to both `omnidrop-api` and `omnidrop-worker` via `fromGroup` in
`render.yaml`. Populate the group in the Render Dashboard **before the first deploy**
— this is a known first-deploy blocker.

### `omnidrop-secrets` Environment Group

| Variable | Where to Find It | Used By |
|---|---|---|
| `APP_SECRET_KEY` | Generate locally: `openssl rand -hex 32` | FastAPI — [ASK USER] |
| `APP_BASE_URL` | `https://omnidrop.dev` (deep links in bounce-back notifications) | Backend + worker |
| `SUPABASE_URL` | Supabase Dashboard → **Project Settings → API → Project URL** | Backend + worker — [ASK USER] |
| `SUPABASE_KEY` | Supabase Dashboard → **Project Settings → API → anon/public key** | Frontend only — [ASK USER] |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase Dashboard → **Project Settings → API → service_role key** | Backend + worker only — NEVER expose to browser — [ASK USER] |
| `ANTHROPIC_API_KEY` | Anthropic Console → **API Keys** | Worker (Claude calls) — [ASK USER] |
| `VOYAGE_API_KEY` | Voyage AI Dashboard → **API Keys** | Worker (embeddings) — [ASK USER] |
| `HOOKDECK_SIGNING_SECRET` | Hookdeck Dashboard → connection → **Signing Secret** tab | Backend (`security.py` HMAC verification) — [ASK USER] |
| `WORKOS_API_KEY` | WorkOS Dashboard → **API Keys** | Backend (server-side SDK) — [ASK USER] |
| `WORKOS_CLIENT_ID` | WorkOS Dashboard → **Applications** → your app | Backend + frontend middleware — [ASK USER] |
| `WORKOS_COOKIE_PASSWORD` | Generate locally: `openssl rand -hex 32` | Next.js session encryption — [ASK USER] |
| `UNSTRUCTURED_API_KEY` | Unstructured.io Dashboard → **API Keys** | Worker (document parsing) — [ASK USER] |
| `SENTRY_PYTHON_DSN` | Sentry Dashboard → **Project → SDK Setup → DSN** | Backend + worker error tracking — [ASK USER] |

**Key rules:**
- `SUPABASE_SERVICE_ROLE_KEY` is server-side only — never set it as a frontend env var.
- The backend Sentry DSN variable is `SENTRY_PYTHON_DSN`, not `SENTRY_DSN`. Using the wrong name means errors are silently swallowed.
- AccuLynx API keys are **not** in this group — they are per-location, stored in Supabase, and fetched at task runtime by `location_id`.

### Service-level env vars (set directly in `render.yaml`, not secrets)

| Variable | Value | Service |
|---|---|---|
| `APP_ENV` | `dev` | `omnidrop-api`, `omnidrop-worker` |
| `PYTHON_VERSION` | `3.11.0` | All Python services |
| `CELERY_BROKER_URL` | Auto-wired from `omnidrop-redis` connection string | `omnidrop-api`, `omnidrop-worker` |
| `CELERY_RESULT_BACKEND` | Auto-wired from `omnidrop-redis` connection string | `omnidrop-api`, `omnidrop-worker` |

Render resolves `fromService` references automatically — you do not set
`CELERY_BROKER_URL` or `CELERY_RESULT_BACKEND` manually.

## 3. Key Concepts

### Blueprint (Infrastructure as Code)

`render.yaml` is a Render Blueprint — a declarative spec for every service, its
build/start commands, env var wiring, and auto-deploy behaviour. When the repo is
connected in the Render dashboard and the Blueprint is applied, Render provisions all
services defined in the file.

Blueprint deploy triggers: push to `main` with `autoDeploy: true` on each service.

### Environment Groups

An Environment Group is a named set of key-value secrets managed in the Render
dashboard (not in the repo). Services reference a group with `fromGroup: omnidrop-secrets`
in `render.yaml`. Updating a secret in the group and clicking **"Save"** propagates
the new value to all linked services on their next deploy.

**The group must exist in the dashboard before the blueprint is first applied.** If
it is missing, the deploy fails with a group-not-found error.

### Health Checks

`omnidrop-api` declares `healthCheckPath: /api/v1/health`. Render polls this path
after each deploy before routing traffic to the new instance. If `/api/v1/health`
does not return `200` within the timeout window, Render rolls back to the previous
deployment automatically.

The Celery worker (`omnidrop-worker`) is a `type: worker` — it has no HTTP surface
and does not require a health check path.

### Auto-Deploy from `main`

All services have `autoDeploy: true` and `branch: main`. Every merge to `main`
triggers a parallel deploy of `omnidrop-api`, `omnidrop-worker`, and `omnidrop-flower`.

A GitHub Actions workflow (`.github/workflows/deploy-dev.yml`) is planned but not yet
implemented. Until it is wired, deploys fire directly from the Render GitHub integration.

### Redis (`omnidrop-redis`)

Render provisions Redis as a `type: redis` Key Value service. It is internal-only
(`ipAllowList: []`) — no public access. The connection string is automatically
injected into `omnidrop-api` and `omnidrop-worker` via `fromService` references.

`maxmemoryPolicy: noeviction` is set to ensure queued Celery tasks are never silently
dropped when memory pressure is high. Do not change this without understanding the
implications for task durability.

### Regions

All services are in `region: oregon` (`us-west-2`). Keep all services in the same
region to minimise Redis and internal latency.

## 4. Integration Points

### `render.yaml` — Blueprint definition

```yaml
# Key sections to understand:
- type: web          # omnidrop-api: FastAPI, health-checked, public
- type: worker       # omnidrop-worker: Celery, no HTTP surface
- type: redis        # omnidrop-redis: internal broker

# Auto-wired connection string (no manual secret needed):
- key: CELERY_BROKER_URL
  fromService:
    name: omnidrop-redis
    type: redis
    property: connectionString

# Shared secrets pulled from dashboard group:
- fromGroup: omnidrop-secrets
```

### `backend/core/config.py` — Reading Render-injected env vars

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_env: str = "dev"
    celery_broker_url: str
    celery_result_backend: str
    supabase_url: str
    supabase_service_role_key: str
    anthropic_api_key: str
    voyage_api_key: str
    hookdeck_signing_secret: str
    workos_api_key: str
    workos_client_id: str
    sentry_python_dsn: str        # Note: SENTRY_PYTHON_DSN, not SENTRY_DSN
    unstructured_api_key: str

    class Config:
        env_file = ".env"
```

### `backend/core/sentry.py` — Backend Sentry init

```python
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.celery import CeleryIntegration
from backend.core.config import get_settings

def init_sentry():
    settings = get_settings()
    sentry_sdk.init(
        dsn=settings.sentry_python_dsn,     # reads SENTRY_PYTHON_DSN
        integrations=[FastApiIntegration(), CeleryIntegration()],
        traces_sample_rate=0.1,
        failed_request_status_codes={429},  # AccuLynx rate limit monitoring
    )
```

### Build commands per service

| Service | Build Command | Start Command |
|---|---|---|
| `omnidrop-api` | `pip install ./shared && pip install -r backend/requirements.txt` | `uvicorn backend.api.main:app --host 0.0.0.0 --port $PORT` |
| `omnidrop-worker` | `pip install ./shared && pip install -r backend/requirements.txt` | `celery -A backend.workers.celery_app worker --loglevel=info --concurrency=4` |
| `omnidrop-flower` | `pip install ./shared && pip install -r backend/requirements.txt` | `celery -A backend.workers.celery_app flower --loglevel=info` |

`./shared` is installed first because `backend` depends on the shared Pydantic models.
Order matters — reversing the commands will cause an import error at startup.

### Frontend (`omnidrop-frontend`)

The Next.js service is managed directly in the Render dashboard (not in `render.yaml`)
until environment group linking is resolved. Expected configuration:
- Runtime: Node
- Build command: `cd frontend && npm ci && npm run build`
- Start command: `cd frontend && npm start`
- Environment: `NEXT_PUBLIC_WORKOS_CLIENT_ID`, `NEXT_PUBLIC_APP_URL`, `SUPABASE_KEY`,
  `NEXT_PUBLIC_SUPABASE_URL`, `SENTRY_DSN` (Next.js uses the standard `SENTRY_DSN` —
  only the Python backend uses `SENTRY_PYTHON_DSN`)

## 5. Common Operations

### Trigger a manual deploy

```bash
# Via Render dashboard: Services → omnidrop-api → "Manual Deploy" → "Deploy latest commit"

# Via Render CLI (if installed):
render deploy --service omnidrop-api
render deploy --service omnidrop-worker
```

### View live logs

```bash
# Render dashboard: Services → <service name> → "Logs" tab
# Logs stream in real-time. Filter by log level using the search box.

# Render CLI:
render logs --service omnidrop-api --tail
render logs --service omnidrop-worker --tail
```

### Update a secret in `omnidrop-secrets`

1. Render Dashboard → **Environment Groups** → `omnidrop-secrets`
2. Find the key, click the pencil icon, update the value
3. Click **"Save"**
4. Re-deploy all linked services (Render may prompt automatically):
   - `omnidrop-api` → Manual Deploy
   - `omnidrop-worker` → Manual Deploy

### Scale the Celery worker (concurrency)

Edit `render.yaml`:

```yaml
- type: worker
  name: omnidrop-worker
  startCommand: celery -A backend.workers.celery_app worker --loglevel=info --concurrency=8
```

Commit and push to `main`. Auto-deploy will apply the change.

Alternatively, upgrade the Render plan (`starter` → `standard`) for more CPU/RAM
before increasing concurrency above 4.

### Upgrade a service plan

Render Dashboard → Services → `<service>` → **"Settings"** → **"Instance Type"** →
select the new plan → **"Save"**. A redeploy is triggered automatically.

Current plans: all services are on `starter` (dev). Do not upgrade without Lead approval.

### Roll back a deploy

Render Dashboard → Services → `<service>` → **"Events"** → find the previous
successful deploy → click **"Rollback to this deploy"**.

Note: rolling back the API but not the worker (or vice versa) can cause task schema
mismatches if Pydantic models changed between deploys. Roll back both together.

### Check health check status

```bash
curl https://api.omnidrop.dev/api/v1/health
# Expected: {"status": "ok"}
```

If Render's health check is failing, this is the first command to run. A `5xx` here
means the service did not start correctly — check the deploy logs for the Python
traceback.

### Check Flower (Celery monitoring)

```
https://omnidrop-flower.onrender.com
```

Flower shows active workers, task queue depth, and individual task history. Use it
to confirm the worker picked up a task after an API webhook delivery. Remove or
restrict access before promoting to prod.

## 6. Error Handling & Monitoring

### Deploy failures

| Symptom | Likely Cause | Resolution |
|---|---|---|
| Build fails: `ModuleNotFoundError: shared` | `pip install ./shared` ran after backend install | Check build command order in `render.yaml` |
| Build fails: `group not found: omnidrop-secrets` | Environment Group not created in dashboard | Follow SOP-RENDER-1 before deploying |
| Health check timeout after deploy | FastAPI failed to start | Check deploy logs for Python traceback; usually a missing env var in `omnidrop-secrets` |
| Worker exits immediately | `CELERY_BROKER_URL` not resolved | Confirm `omnidrop-redis` service is running and the `fromService` reference is correct |
| `SENTRY_PYTHON_DSN` not capturing errors | Wrong variable name used | Confirm `config.py` reads `SENTRY_PYTHON_DSN` (not `SENTRY_DSN`) and the group has the right key name |

### Runtime errors

| Scenario | Behaviour |
|---|---|
| FastAPI raises unhandled exception | Sentry captures via `FastApiIntegration` — check Sentry project for the backend DSN |
| Celery task raises unhandled exception | Sentry captures via `CeleryIntegration` — same DSN |
| AccuLynx returns `429` | Sentry captures via `failed_request_status_codes={429}` — triggers alert |
| Redis connection lost | Celery retries with backoff; after max retries, task moves to dead-letter queue |
| Worker OOM | Render restarts the process automatically; add alert in Render dashboard if this repeats |

### Structured logging

Both `omnidrop-api` and `omnidrop-worker` use `backend/core/logging.py` for structured
JSON logs. Render streams all stdout/stderr to the Logs tab. Always include
`organization_id` and `job_id` in log entries — these are the primary trace keys.

```python
import structlog
log = structlog.get_logger()

log.info("process_document.started", job_id=job_id, organization_id=org_id)
```

### Sentry alerts to configure

| Alert | Condition |
|---|---|
| Worker crash loop | Service restart count > 3 in 10 minutes |
| Health check failure | `GET /api/v1/health` non-200 for 2+ consecutive checks |
| AccuLynx 429 spike | More than 5 `429` events in 60 seconds |
| Task failure rate | `>10%` of Celery tasks in error state |

Configure these in Sentry under **Alerts → Alert Rules** for the backend project.

## 7. SOPs

### SOP-RENDER-1: Populate `omnidrop-secrets` Before First Deploy

**When:** Initial environment setup — must be done before the first blueprint deploy.
**Time:** ~20 minutes
**Prerequisite:** You have credentials for Supabase, Anthropic, Voyage AI, Hookdeck,
WorkOS, Unstructured.io, and Sentry for this environment.

Step 1. Log in to https://dashboard.render.com.

Step 2. In the left nav, click **"Environment Groups"**.

Step 3. Click **"New Environment Group"** and name it `omnidrop-secrets`.

Step 4. Add each secret below. Use **"Add Secret File"** for sensitive values;
use **"Add Environment Variable"** for non-secret values:

```
APP_SECRET_KEY          = [generate: openssl rand -hex 32]
APP_BASE_URL            = https://omnidrop.dev
SUPABASE_URL            = [ASK USER]
SUPABASE_KEY            = [ASK USER]
SUPABASE_SERVICE_ROLE_KEY = [ASK USER]
ANTHROPIC_API_KEY       = [ASK USER]
VOYAGE_API_KEY          = [ASK USER]
HOOKDECK_SIGNING_SECRET = [ASK USER]
WORKOS_API_KEY          = [ASK USER]
WORKOS_CLIENT_ID        = [ASK USER]
WORKOS_COOKIE_PASSWORD  = [generate: openssl rand -hex 32]
UNSTRUCTURED_API_KEY    = [ASK USER]
SENTRY_PYTHON_DSN       = [ASK USER]
```

Step 5. Click **"Save"**.

Step 6. Connect the GitHub repo: **Dashboard → New → Blueprint**. Select the
OmniDrop AI repo and point Render at `render.yaml`.

Step 7. Render will provision all services. Watch the deploy logs for each service.

Step 8. Verify the API is live:
```bash
curl https://api.omnidrop.dev/api/v1/health
# Expected: {"status": "ok"}
```

Step 9. Tell Claude: `"SOP-RENDER-1 complete. omnidrop-secrets populated and first deploy succeeded. Resume [current task name]."`

Done when: all services show **"Live"** in the Render dashboard and `/api/v1/health` returns `200`.

If the worker exits immediately after deploy: confirm `omnidrop-redis` started first
and check that `CELERY_BROKER_URL` resolved correctly in the worker's environment
variables tab.

---

### SOP-RENDER-2: Deploy a Code Change to Dev

**When:** Merging a feature branch to `main` and confirming it reaches `app.omnidrop.dev`.
**Time:** ~5–10 minutes (Render build + health check time)
**Prerequisite:** The PR is approved and merged to `main`.

Step 1. Push or merge to `main`. Render auto-deploy triggers within ~30 seconds.

Step 2. Watch the deploy in the Render dashboard:
- **Dashboard → Services → `omnidrop-api` → "Events"** — confirm a new deploy appears.
- Click the deploy to stream build logs in real time.

Step 3. Confirm both services deploy successfully:
- `omnidrop-api` — status changes to **"Live"**
- `omnidrop-worker` — status changes to **"Live"** (no health check, so confirm via logs)

Step 4. Verify health check:
```bash
curl https://api.omnidrop.dev/api/v1/health
# Expected: {"status": "ok"}
```

Step 5. Smoke-test the changed feature end-to-end.

Step 6. Tell Claude: `"SOP-RENDER-2 complete. [feature name] deployed to omnidrop.dev. Resume [current task name]."`

If the health check fails and Render rolls back: check the deploy logs for the Python
traceback. The most common causes are a missing env var or an import error in newly
added code.

---

### SOP-RENDER-3: Rotate a Secret in `omnidrop-secrets`

**When:** A credential is compromised or rotated upstream (e.g., Hookdeck signing
secret rotation, Supabase key regeneration).
**Time:** ~10 minutes
**Prerequisite:** You have the new credential value from the upstream provider.

Step 1. Obtain the new secret value from the upstream provider dashboard.

Step 2. Render Dashboard → **Environment Groups** → `omnidrop-secrets`.

Step 3. Find the relevant key, click the pencil icon, paste the new value.

Step 4. Click **"Save"**.

Step 5. Redeploy all linked services to pick up the new value:
- **Services → `omnidrop-api` → "Manual Deploy"**
- **Services → `omnidrop-worker` → "Manual Deploy"**

Step 6. Confirm both services return to **"Live"** status.

Step 7. Verify the rotated credential works end-to-end (e.g., for `HOOKDECK_SIGNING_SECRET`,
send a test event via the Hookdeck dashboard and confirm `200` in the API logs).

Step 8. Tell Claude: `"SOP-RENDER-3 complete. [KEY_NAME] rotated. Services redeployed. Resume [current task name]."`

If a service fails to start after the rotation: the new secret value may have been
pasted with extra whitespace. Re-copy from the provider and update again.

---

### SOP-RENDER-4: Roll Back a Broken Deploy

**When:** A deploy to `main` has broken the live environment and must be reversed
immediately.
**Time:** ~3 minutes
**Prerequisite:** You know which service is broken and the previous deploy was healthy.

Step 1. Render Dashboard → **Services → `omnidrop-api` → "Events"**.

Step 2. Find the last deploy marked **"Live"** before the broken one.

Step 3. Click **"Rollback to this deploy"** and confirm.

Step 4. Repeat for `omnidrop-worker` (roll back to the same commit to avoid schema
mismatches between API and worker).

Step 5. Verify:
```bash
curl https://api.omnidrop.dev/api/v1/health
# Expected: {"status": "ok"}
```

Step 6. File a note in the team Slack with: the broken commit hash, what broke, and
the rollback commit hash.

Step 7. Tell Claude: `"SOP-RENDER-4 complete. Rolled back to [commit hash]. Environment stable. Resume [current task name]."`

Do not roll back `omnidrop-redis` — Redis state (task queue contents) is independent
of the application code and should not be disturbed during a code rollback.
