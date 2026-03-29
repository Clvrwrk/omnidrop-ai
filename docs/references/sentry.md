# Sentry — OmniDrop Reference

## 1. What It Does Here

Sentry provides error tracking and performance monitoring across both layers of
OmniDrop. There are two separate Sentry projects — one for the Python backend and
one for the Next.js frontend — each with its own DSN.

The **backend** project captures FastAPI request errors and Celery task failures.
`configure_sentry()` in `backend/core/sentry.py` is called once at FastAPI startup.
It installs `StarletteIntegration` and `FastApiIntegration` with a custom
`failed_request_status_codes` set that includes `429` — this is the mechanism for
alerting on AccuLynx rate-limit breaches (per CLAUDE.md non-negotiable rules). When
a Celery task exhausts all retries, `_on_task_failure` in `intake_tasks.py` calls
`sentry_sdk.capture_exception()` directly with task/job context attached.

The **frontend** project captures browser-side errors and performance data. The
wizard (`npx @sentry/wizard@latest -i nextjs`) generates three config files
(`sentry.client.config.ts`, `sentry.server.config.ts`, `sentry.edge.config.ts`)
that already exist in the repo. Sentry is disabled in both layers when the DSN env
var is not set — safe for local dev without any Sentry account.

Files that touch Sentry:
- `backend/core/sentry.py` — `configure_sentry()`, called from `backend/api/main.py`
- `backend/workers/intake_tasks.py` — `_on_task_failure` calls `sentry_sdk.capture_exception()`
- `frontend/sentry.client.config.ts` — browser runtime (includes Replay integration)
- `frontend/sentry.server.config.ts` — Next.js server runtime
- `frontend/sentry.edge.config.ts` — Next.js edge runtime
- `backend/core/config.py` — `SENTRY_PYTHON_DSN`, `SENTRY_TRACES_SAMPLE_RATE` settings

## 2. Credentials & Environment Variables

| Variable | Layer | Where to Find It |
|---|---|---|
| `SENTRY_PYTHON_DSN` | Backend + Celery workers | Sentry Dashboard → Python project → **Settings → Client Keys (DSN)** |
| `NEXT_PUBLIC_SENTRY_DSN` | Frontend (Next.js) | Sentry Dashboard → Next.js project → **Settings → Client Keys (DSN)** |
| `SENTRY_TRACES_SAMPLE_RATE` | Backend only | Set in `.env` — default `1.0` (100%). Lower to `0.1` in production. |
| `NEXT_PUBLIC_APP_ENV` | Frontend only | Set to `"local"`, `"dev"`, or `"production"` — controls frontend `tracesSampleRate` |

**Critical naming rule (from CLAUDE.md — non-negotiable):**
The backend env var is `SENTRY_PYTHON_DSN`. Never use `SENTRY_DSN` — it will be
silently ignored by `config.py` and Sentry will not initialise.

**Actual DSN values:** [ASK USER] — retrieve via SOP-SENTRY-1 below.

Both DSNs are safe to commit to non-secret config (they are public client-side
identifiers), but treat them as semi-sensitive — anyone with a DSN can send events
to your project. Keep them out of public repos.

## 3. CLI

```bash
# Run the Sentry wizard for Next.js (generates the three frontend config files)
# Only needed once per project, or to upgrade the Sentry Next.js integration
npx @sentry/wizard@latest -i nextjs
# The wizard will: install @sentry/nextjs, create the three config files,
# update next.config.js with withSentryConfig(), and add example error pages.
# Config files already exist in this repo — re-run the wizard only to upgrade.

# Install the Python SDK (already in requirements.txt)
pip install "sentry-sdk[fastapi]"

# Verify backend SDK version
python -c "import sentry_sdk; print(sentry_sdk.VERSION)"

# Verify frontend SDK version
cd frontend && npm list @sentry/nextjs

# Send a test event from the Python backend (run from repo root with .env loaded)
python - <<'EOF'
import sentry_sdk, os
sentry_sdk.init(dsn=os.environ["SENTRY_PYTHON_DSN"], environment="test")
sentry_sdk.capture_message("OmniDrop backend Sentry test event", level="info")
sentry_sdk.flush()  # Required in short-lived scripts — flush before exit
print("Test event sent — check your Sentry dashboard in ~30 seconds")
EOF
```

## 4. MCP (Claude Code)

Sentry has no MCP server. Use the Sentry dashboard for event inspection and the
Python SDK directly for testing. For documentation lookups:

| Operation | Preferred Tool | Example |
|---|---|---|
| Look up SDK integration docs | `mcp__plugin_context7_context7__resolve-library-id` then `mcp__plugin_context7_context7__query-docs` | `{ "query": "sentry-sdk fastapi integration failed_request_status_codes" }` |
| Look up Next.js wizard docs | same | `{ "query": "@sentry/nextjs withSentryConfig options" }` |

## 5. Direct API

Sentry exposes a management REST API. Use it only for scripted alerting setup or
bulk event queries — the dashboard covers all day-to-day operations.

```bash
# List recent issues in a project (requires Sentry Auth Token — not the DSN)
curl -X GET "https://sentry.io/api/0/projects/<org-slug>/<project-slug>/issues/" \
  -H "Authorization: Bearer $SENTRY_AUTH_TOKEN"

# Resolve an issue
curl -X PUT "https://sentry.io/api/0/issues/<issue-id>/" \
  -H "Authorization: Bearer $SENTRY_AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"status": "resolved"}'

# Test that a DSN is valid
curl -X POST "https://o<org-id>.ingest.sentry.io/api/<project-id>/envelope/" \
  -H "Content-Type: application/x-sentry-envelope" \
  --data-raw $'{"dsn":"<YOUR_DSN>"}\n{"type":"session"}\n{"sid":"test"}'
# 200 = DSN valid. 403 = invalid DSN.
```

Note: `SENTRY_AUTH_TOKEN` (for the management API) is separate from the project
DSN. The auth token is only needed for CI/CD release tracking and programmatic
issue management — it is not stored in application config.

## 6. OmniDrop-Specific Patterns

### Backend initialisation (the production implementation)

```python
# backend/core/sentry.py — call configure_sentry() at FastAPI startup
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from backend.core.config import settings

def configure_sentry() -> None:
    if not settings.sentry_python_dsn:
        return  # Disabled in local dev when SENTRY_PYTHON_DSN is not set

    sentry_sdk.init(
        dsn=settings.sentry_python_dsn,          # reads SENTRY_PYTHON_DSN
        environment=settings.app_env,            # "local" | "dev" | "sandbox" | "production"
        traces_sample_rate=settings.sentry_traces_sample_rate,
        integrations=[
            StarletteIntegration(
                failed_request_status_codes={429, 500, 502, 503}
            ),
            FastApiIntegration(
                failed_request_status_codes={429, 500, 502, 503}
            ),
        ],
        send_default_pii=False,  # Never send user emails, IPs, or request bodies
    )
```

The `429` in `failed_request_status_codes` is non-negotiable — it is the mechanism
for capturing AccuLynx rate-limit errors per CLAUDE.md. Do not remove it.

### Celery worker initialisation

`_on_task_failure` calls `sentry_sdk.capture_exception()` — this only works if the
Celery worker process has initialised the SDK before any task runs. Verify that
`configure_sentry()` (or equivalent) is called in `backend/workers/celery_app.py`
worker startup signals. If Celery task failures are not appearing in Sentry, this
is the first thing to check.

### Celery task failure capture

```python
# backend/workers/intake_tasks.py — _on_task_failure fires after all retries exhausted
import sentry_sdk

def _on_task_failure(self, exc, task_id, args, kwargs, einfo):
    sentry_sdk.capture_exception(
        exc,
        extras={"task": self.name, "task_id": task_id, "job_id": job_id},
    )
    # Also updates job status to "failed" in Supabase
```

This is wired to all 7 intake tasks via `on_failure=_on_task_failure`. Do not call
`sentry_sdk.capture_exception()` separately inside task `except` blocks —
`_on_task_failure` is the single capture point for terminal failures.

### Attaching job context to manual captures

When capturing exceptions outside `_on_task_failure`, always attach job context:

```python
import sentry_sdk

with sentry_sdk.push_scope() as scope:
    scope.set_tag("job_id", job_id)
    scope.set_tag("organization_id", organization_id)
    scope.set_extra("task_name", "detect_revenue_leakage")
    sentry_sdk.capture_exception(exc)
```

### Frontend config files (generated by wizard, already in repo)

Three files exist at `frontend/`:

```
frontend/sentry.client.config.ts  ← browser runtime — includes Replay integration
frontend/sentry.server.config.ts  ← Next.js server-side rendering
frontend/sentry.edge.config.ts    ← Next.js edge middleware
```

All three read `NEXT_PUBLIC_SENTRY_DSN` and `NEXT_PUBLIC_APP_ENV`. They are
disabled (`enabled: false`) when `NEXT_PUBLIC_SENTRY_DSN` is not set.

The client config includes Session Replay:
```typescript
// sentry.client.config.ts
Sentry.init({
  dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
  environment: process.env.NEXT_PUBLIC_APP_ENV ?? "local",
  tracesSampleRate: process.env.NEXT_PUBLIC_APP_ENV === "production" ? 0.1 : 1.0,
  replaysSessionSampleRate: 0.1,   // 10% of sessions
  replaysOnErrorSampleRate: 1.0,   // 100% of sessions that contain an error
  integrations: [Sentry.replayIntegration()],
  enabled: !!process.env.NEXT_PUBLIC_SENTRY_DSN,
});
```

**Privacy note on Session Replay:** Replay captures DOM content — invoice totals,
leakage amounts, and vendor names visible in the UI will appear in replay sessions.
Before enabling Replay for external beta users, consider masking sensitive selectors:
```typescript
integrations: [Sentry.replayIntegration({ mask: ['.financial-data', '[data-sensitive]'] })]
```

### Sample rate strategy

| Environment | Backend `SENTRY_TRACES_SAMPLE_RATE` | Frontend `tracesSampleRate` |
|---|---|---|
| `local` | `1.0` (default) | `1.0` |
| `dev` | `1.0` (default) | `1.0` |
| `sandbox` | `1.0` (default) | `1.0` |
| `production` | Set `SENTRY_TRACES_SAMPLE_RATE=0.1` in Render | `0.1` (hardcoded in config) |

### Two Sentry projects — never mix the DSNs

| Project | DSN env var | Purpose |
|---|---|---|
| `omnidrop-python` (or similar) | `SENTRY_PYTHON_DSN` | FastAPI + Celery workers |
| `omnidrop-nextjs` (or similar) | `NEXT_PUBLIC_SENTRY_DSN` | Next.js frontend |

Sending backend events to the frontend DSN produces confusing stack traces with no
context. If you see Python tracebacks in the Sentry Next.js project, a DSN has been
misconfigured.

### Known gotchas

- **`SENTRY_PYTHON_DSN` is the only accepted backend variable name.** `SENTRY_DSN`
  is silently ignored by `config.py`. This is a common mistake.
- **`configure_sentry()` must be called before any route is registered.** Call it
  at the top of `backend/api/main.py`, before `app.include_router(...)`.
- **Celery workers run in a separate process from FastAPI.** Sentry must be
  initialised in the Celery worker entrypoint separately — verify this is wired in
  `celery_app.py` if task failures are not appearing in Sentry.
- **`send_default_pii=False` is set intentionally.** OmniDrop processes financial
  documents — do not change this to `True` without a privacy review.
- **The wizard modifies `next.config.js`** to wrap it with `withSentryConfig()`.
  If re-run, review the diff before committing — it can overwrite customisations.
- **Short-lived scripts must call `sentry_sdk.flush()`** before exit — otherwise
  events may not be sent before the process terminates.
- **The superseded `workers/sentry_init.py`** at the top-level `workers/` directory
  is from the old Temporal.io architecture (see CLAUDE.md superseded list). Do not
  reference or extend it — use `backend/core/sentry.py` only.

## 7. Human SOPs

### SOP-SENTRY-1: Retrieve DSNs and Set Environment Variables

**When:** First-time environment setup, or when rotating DSNs.
**Time:** ~10 minutes (both projects)
**Prerequisite:** You have access to the OmniDrop Sentry organisation and both
`.env` (backend) and `frontend/.env.local` (frontend) are open in your editor.

Step 1. Go to https://sentry.io and log in to the OmniDrop organisation.

Step 2. Click **"Settings"** → **"Projects"**.

Step 3. Click the **Python backend project** (e.g., `omnidrop-python`).

Step 4. Click **"Client Keys (DSN)"** in the project settings sidebar.

Step 5. Copy the DSN value: `https://xxxxxxxx...@o0000000.ingest.sentry.io/0000000`

Step 6. Paste into backend `.env`:
```
SENTRY_PYTHON_DSN=https://xxxxxxxx...
SENTRY_TRACES_SAMPLE_RATE=1.0
```

Step 7. Go back to **"Projects"**, click the **Next.js frontend project**.

Step 8. Repeat Steps 4–5 to copy the frontend DSN.

Step 9. Paste into `frontend/.env.local`:
```
NEXT_PUBLIC_SENTRY_DSN=https://xxxxxxxx...
NEXT_PUBLIC_APP_ENV=dev
```

Step 10. Run the backend smoke test:
```bash
python - <<'EOF'
import os, sentry_sdk
sentry_sdk.init(dsn=os.environ["SENTRY_PYTHON_DSN"], environment="test")
sentry_sdk.capture_message("OmniDrop Sentry SOP-1 test", level="info")
sentry_sdk.flush()
print("Event sent — check Sentry dashboard in ~30 seconds")
EOF
```

Step 11. Tell Claude: `"Sentry SOP-1 complete. SENTRY_PYTHON_DSN and NEXT_PUBLIC_SENTRY_DSN are set. Resume [current task name]."`

✅ Done when: the test event from Step 10 appears in the Sentry backend project.

⚠️ If the event does not appear after 60 seconds: confirm the variable is named
`SENTRY_PYTHON_DSN` (not `SENTRY_DSN`) and that `sentry_sdk.flush()` was called.

---

### SOP-SENTRY-2: Run the Next.js Wizard (Frontend Setup or Upgrade)

**When:** Setting up Sentry for Next.js for the first time, or upgrading `@sentry/nextjs`.
**Time:** ~10 minutes
**Prerequisite:** In the `frontend/` directory, `NEXT_PUBLIC_SENTRY_DSN` is set in
`frontend/.env.local`, Node.js is installed.

Step 1. From the `frontend/` directory:
```bash
npx @sentry/wizard@latest -i nextjs
```

Step 2. When prompted to log in, select the OmniDrop organisation and the Next.js
frontend project.

Step 3. When asked whether to overwrite existing config files: answer **No** if the
files already exist (upgrading only). Answer **Yes** for a clean first-time setup.

Step 4. Review the diff to `next.config.js` — preserve any existing webpack or
image config options.

Step 5. Start the dev server: `npm run dev`. Confirm no Sentry console errors.

Step 6. In the browser console, throw a test error:
```javascript
throw new Error("OmniDrop Sentry frontend test")
```

Step 7. Confirm the error appears in the Sentry Next.js project under **"Issues"**.

Step 8. Tell Claude: `"Sentry SOP-2 complete. Next.js Sentry wizard run. Resume [current task name]."`

✅ Done when: the test error appears in the Sentry Next.js project dashboard.

⚠️ If the wizard prompts for an auth token: create one at
https://sentry.io/settings/account/api/auth-tokens/ with `project:releases` and
`org:read` scopes.
