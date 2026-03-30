# Celery Beat (Scheduled Jobs) — OmniDrop Reference

## 1. What It Does Here

Celery Beat is the scheduler component of the Celery task queue system. It runs as a
separate process that periodically dispatches tasks to the Celery worker queue at
configured intervals. OmniDrop uses Celery Beat — not an external cron service — to
run all time-based background operations.

Beat does not execute tasks itself. It acts as a timer that publishes task messages to
the Redis broker on schedule. The `omnidrop-worker` process picks up those messages and
executes them exactly like any other Celery task.

**Key distinction:** Beat and the Celery worker MUST run as separate processes. Running
Beat inside the same process as the worker (`--beat` flag on the worker) causes duplicate
task execution and must never be done in production.

**Scheduled tasks in OmniDrop:**

| Task | Schedule | Purpose |
|---|---|---|
| `daily_leakage_report` | Daily at 00:00 UTC | Summarise `revenue_findings` and post to org admin Slack channels |
| `reset_freemium_quotas` | 1st of each month, 00:00 UTC | Reset `documents_processed` counter for freemium orgs |
| `cleanup_stale_jobs` | Daily at 01:00 UTC | Mark jobs stuck in `processing` > 24 h as `failed` |
| `refresh_vendor_baseline` | Weekly, Sunday 02:00 UTC | Rematerialise `vendor_baseline_prices` view (future) |

**Services defined in `render.yaml` that involve Beat:**

| Service Name | Type | Role |
|---|---|---|
| `omnidrop-beat` | Background worker | Celery Beat scheduler — dispatches timed tasks to Redis |
| `omnidrop-worker` | Background worker | Celery worker — executes all tasks, including Beat-dispatched ones |
| `omnidrop-redis` | Redis (Key Value) | Shared broker used by both Beat and the worker |

Files that define Beat behaviour:
- `backend/workers/celery_app.py` — `beat_schedule` dict, `crontab` definitions
- `render.yaml` — `omnidrop-beat` service definition and start command
- `backend/core/config.py` — reads `CELERY_BROKER_URL` used by Beat

## 2. Credentials & Environment Variables

Celery Beat uses the same Redis broker as the worker. No additional secrets are needed
beyond those already in `omnidrop-secrets`.

### Shared secrets (from `omnidrop-secrets` Environment Group)

| Variable | Where to Find It | Used By |
|---|---|---|
| `CELERY_BROKER_URL` | Auto-wired by Render from `omnidrop-redis` `connectionString` | Beat + Worker |
| `CELERY_RESULT_BACKEND` | Auto-wired by Render from `omnidrop-redis` `connectionString` | Beat + Worker |
| `SENTRY_PYTHON_DSN` | Sentry Dashboard → **Project → SDK Setup → DSN** | Beat process error tracking — [ASK USER] |
| `SUPABASE_URL` | Supabase Dashboard → **Project Settings → API → Project URL** | Beat tasks that query Supabase — [ASK USER] |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase Dashboard → **Project Settings → API → service_role key** | Beat tasks that write to Supabase — NEVER expose to browser — [ASK USER] |

**Key rules:**
- Beat itself does not need `ANTHROPIC_API_KEY` or `VOYAGE_API_KEY` — it only
  dispatches tasks. The worker that executes those tasks does need those keys.
- `CELERY_BROKER_URL` is auto-resolved by Render via `fromService` — do not set it
  manually in the dashboard.
- The Beat process reads the same `backend/core/config.py` settings as the worker.
  Any missing env var will cause Beat to fail at startup.

## 3. Key Concepts

### Celery Beat vs. Celery Worker

Beat is a scheduler, not an executor. The process split is:

```
omnidrop-beat   → Reads beat_schedule → Publishes task message to Redis at the right time
omnidrop-redis  → Holds the message in the queue
omnidrop-worker → Pulls message from Redis → Executes the task function
```

Never use `celery worker --beat` (the combined flag) in production. It runs Beat
inside the worker process, which causes duplicate task dispatches when the worker is
restarted or scaled.

### `beat_schedule` in `celery_app.py`

All scheduled tasks are declared in the `beat_schedule` dict inside
`backend/workers/celery_app.py`. Each entry maps a human-readable name to a task
path, schedule, and optional arguments:

```python
from celery.schedules import crontab
from backend.workers.celery_app import celery_app

celery_app.conf.beat_schedule = {
    "daily-leakage-report": {
        "task": "backend.workers.scheduled_tasks.daily_leakage_report",
        "schedule": crontab(hour=0, minute=0),        # 00:00 UTC daily
    },
    "reset-freemium-quotas": {
        "task": "backend.workers.scheduled_tasks.reset_freemium_quotas",
        "schedule": crontab(hour=0, minute=0, day_of_month=1),  # 1st of month
    },
    "cleanup-stale-jobs": {
        "task": "backend.workers.scheduled_tasks.cleanup_stale_jobs",
        "schedule": crontab(hour=1, minute=0),        # 01:00 UTC daily
    },
    "refresh-vendor-baseline": {
        "task": "backend.workers.scheduled_tasks.refresh_vendor_baseline",
        "schedule": crontab(hour=2, minute=0, day_of_week=0),  # Sunday 02:00 UTC
    },
}
```

### `crontab` Schedule Format

Celery uses `celery.schedules.crontab` — not Unix cron strings. Parameters:

| Parameter | Default | Meaning |
|---|---|---|
| `minute` | `"*"` | Minute(s) to fire (0–59) |
| `hour` | `"*"` | Hour(s) to fire in UTC (0–23) |
| `day_of_week` | `"*"` | Day of week (0 = Sunday, 6 = Saturday) |
| `day_of_month` | `"*"` | Day of month (1–31) |
| `month_of_year` | `"*"` | Month (1–12) |

All times are **UTC**. OmniDrop has no timezone-aware Beat configuration — if a task
must fire at a specific local time for users, convert to UTC before setting the schedule.

### Beat Persistence (`--schedule` / `celerybeat-schedule`)

By default, Beat stores its last-run timestamps in a local file called
`celerybeat-schedule`. On Render, this file lives on the ephemeral filesystem and is
lost on every restart. This is acceptable for OmniDrop's scheduled tasks — Beat will
simply re-evaluate which tasks are due on startup and run any that were missed.

If strict at-most-once semantics are required in the future, consider using
`django-celery-beat` or a database-backed scheduler. For now, the file-based default
is sufficient.

### Sentry Monitoring for Beat Tasks

`sentry-sdk[celery]` instruments both the worker and the Beat process. Long-running
or failing Beat-dispatched tasks appear in Sentry under the same backend project as
regular Celery tasks.

Beat itself (the scheduler process) does not execute task code — Sentry will only
capture exceptions that occur in the Beat scheduler logic itself (e.g., misconfigured
schedule). Task failures are captured by the worker's Sentry integration.

## 4. Integration Points

### `backend/workers/celery_app.py` — Beat schedule definition

```python
# beat_schedule is the single source of truth for all scheduled tasks.
# Add new scheduled tasks here — do not configure schedules elsewhere.

from celery import Celery
from celery.schedules import crontab
from backend.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "omnidrop",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.beat_schedule = {
    "daily-leakage-report": {
        "task": "backend.workers.scheduled_tasks.daily_leakage_report",
        "schedule": crontab(hour=0, minute=0),
    },
    # ... other schedules
}

celery_app.conf.timezone = "UTC"
```

### `render.yaml` — Beat service definition

```yaml
- type: worker
  name: omnidrop-beat
  env: python
  region: oregon
  branch: main
  autoDeploy: true
  buildCommand: pip install ./shared && pip install -r backend/requirements.txt
  startCommand: celery -A backend.workers.celery_app beat --loglevel=info
  envVars:
    - key: APP_ENV
      value: dev
    - key: PYTHON_VERSION
      value: 3.11.0
    - key: CELERY_BROKER_URL
      fromService:
        name: omnidrop-redis
        type: redis
        property: connectionString
    - key: CELERY_RESULT_BACKEND
      fromService:
        name: omnidrop-redis
        type: redis
        property: connectionString
    - fromGroup: omnidrop-secrets
```

### `backend/workers/scheduled_tasks.py` — Task implementations

Scheduled tasks are defined in a dedicated module (separate from `intake_tasks.py`)
to keep pipeline tasks and maintenance tasks clearly separated:

```python
from backend.workers.celery_app import celery_app
from backend.services.supabase_client import get_supabase_client
import structlog

log = structlog.get_logger()

@celery_app.task
async def daily_leakage_report():
    """Generate and Slack-post revenue_findings summary to org admins."""
    ...

@celery_app.task
async def reset_freemium_quotas():
    """Reset documents_processed=0 for all orgs on freemium plan."""
    ...

@celery_app.task
async def cleanup_stale_jobs():
    """Mark jobs stuck in processing > 24h as failed."""
    ...

@celery_app.task
async def refresh_vendor_baseline():
    """Rematerialise vendor_baseline_prices view. Future task."""
    ...
```

### Supabase tables touched by Beat tasks

| Task | Tables Read | Tables Written |
|---|---|---|
| `daily_leakage_report` | `revenue_findings`, `organizations`, `locations` | — (sends Slack, no DB write) |
| `reset_freemium_quotas` | `organizations` | `organizations.documents_processed` |
| `cleanup_stale_jobs` | `jobs` | `jobs.status`, `jobs.error_message` |
| `refresh_vendor_baseline` | `invoices`, `line_items` | `vendor_baseline_prices` (materialised view) |

### Slack notifications from Beat tasks

`daily_leakage_report` routes through the same channel adapter pattern as the
`bounce_back` pipeline task:

```python
channel_config = location["notification_channels"]
adapter = get_notification_adapter(channel_config)  # SlackAdapter (alpha)
adapter.send(report_message)
```

Never hardcode Slack webhook URLs in the task — read them from
`locations.notification_channels` via Supabase.

## 5. Common Operations

### Add a new scheduled task

1. Implement the task function in `backend/workers/scheduled_tasks.py` with
   the `@celery_app.task` decorator.

2. Add an entry to `beat_schedule` in `backend/workers/celery_app.py`:

```python
"my-new-task": {
    "task": "backend.workers.scheduled_tasks.my_new_task",
    "schedule": crontab(hour=3, minute=30),  # 03:30 UTC daily
},
```

3. Commit and push to `main`. Both `omnidrop-beat` and `omnidrop-worker` will
   redeploy automatically. Beat picks up the new schedule on its next start.

### Trigger a scheduled task manually (for testing)

```bash
# From a shell with the Python environment active and CELERY_BROKER_URL set:
celery -A backend.workers.celery_app call backend.workers.scheduled_tasks.cleanup_stale_jobs

# Or from a Python REPL:
from backend.workers.scheduled_tasks import cleanup_stale_jobs
cleanup_stale_jobs.delay()
```

Use Flower (`https://omnidrop-flower.onrender.com`) to confirm the task was received
and executed by the worker.

### Change a task's schedule

Edit the `crontab(...)` definition in `beat_schedule` inside
`backend/workers/celery_app.py`. Commit and push. The new schedule takes effect when
`omnidrop-beat` restarts after the deploy.

### Disable a scheduled task temporarily

Comment out or remove its entry from `beat_schedule`. Commit and push. The task will
no longer be dispatched until the entry is restored. Do not delete the task function
itself — only remove the schedule entry.

### Check Beat is running and dispatching tasks

```bash
# Render dashboard → Services → omnidrop-beat → Logs
# Look for lines like:
# [INFO/MainProcess] beat: Starting...
# [INFO/MainProcess] Scheduler: Sending due task daily-leakage-report (backend.workers.scheduled_tasks.daily_leakage_report)
```

If no "Sending due task" lines appear after the expected schedule time, Beat may not
be running. Check the service status in the Render dashboard.

### View Beat task history in Flower

```
https://omnidrop-flower.onrender.com
```

Navigate to **Tasks** → filter by task name (e.g.,
`backend.workers.scheduled_tasks.cleanup_stale_jobs`). Flower shows when the task
was received, started, and whether it succeeded or failed.

## 6. Error Handling & Monitoring

### Beat-specific failure modes

| Symptom | Likely Cause | Resolution |
|---|---|---|
| Beat exits immediately at startup | `CELERY_BROKER_URL` not resolved or Redis not running | Confirm `omnidrop-redis` is live; check `fromService` wiring in `render.yaml` |
| Beat starts but tasks never appear in Flower | Beat is connected to a different broker than the worker | Confirm both `omnidrop-beat` and `omnidrop-worker` read `CELERY_BROKER_URL` from the same `fromService` reference |
| Task dispatched but never executed | Worker is not running or has no capacity | Check `omnidrop-worker` status in Render; check Flower for queue depth |
| Duplicate task executions | `--beat` flag used on the worker (combined mode) | Split Beat into its own `omnidrop-beat` service; never use `celery worker --beat` |
| Task missed after Beat restart | `celerybeat-schedule` file lost (ephemeral disk) | Expected behaviour — Beat re-evaluates schedule on startup and runs overdue tasks |
| Scheduled task fails silently | Task function raises unhandled exception | Sentry captures via `CeleryIntegration`; check Sentry for the backend DSN project |

### Runtime error behaviour

| Scenario | Behaviour |
|---|---|
| Scheduled task raises an unhandled exception | Sentry captures via `CeleryIntegration`; task enters `FAILURE` state in result backend |
| Redis connection lost during dispatch | Beat retries the dispatch with exponential backoff; logs a `ConnectionError` |
| Supabase query fails inside a scheduled task | Task raises an exception; Sentry captures it; no automatic retry unless `autoretry_for` is configured on the task |
| `daily_leakage_report` Slack POST fails | `SlackAdapter.send()` raises; Sentry captures; report is not re-sent (acceptable data loss for non-critical notification) |
| `cleanup_stale_jobs` fails partway through | Jobs already updated retain their `failed` status; remaining jobs stay in `processing` until the next daily run |

### Structured logging in scheduled tasks

Always include `job_id` or `organization_id` in log entries where applicable:

```python
log.info("cleanup_stale_jobs.started")
log.info("cleanup_stale_jobs.job_marked_failed", job_id=job_id, reason="timeout_exceeded_24h")
log.info("cleanup_stale_jobs.complete", updated_count=n)
```

### Sentry alerts to configure

| Alert | Condition |
|---|---|
| Beat process crash | `omnidrop-beat` service restarts > 2 times in 30 minutes |
| Scheduled task failure | Any Beat-dispatched task enters `FAILURE` state |
| `daily_leakage_report` missing | No execution of the task between 00:00–00:10 UTC (dead man's switch) |
| `cleanup_stale_jobs` missing | No execution between 01:00–01:10 UTC |

Configure dead man's switch alerts in Sentry under **Alerts → Cron Monitors**
using the Sentry Celery integration. Associate each scheduled task with a monitor
slug that matches the `beat_schedule` key name.

## 7. SOPs

### SOP-BEAT-1: Add `omnidrop-beat` to `render.yaml` (First-Time Setup)

**When:** Initial deployment — Beat service must be defined before scheduled tasks
will run.
**Time:** ~10 minutes
**Prerequisite:** `omnidrop-secrets` is populated and `omnidrop-redis` is running
(see SOP-RENDER-1).

Step 1. Open `render.yaml` at the repo root.

Step 2. Add the Beat worker service block. Place it after `omnidrop-worker` so the
deploy order is logical:

```yaml
- type: worker
  name: omnidrop-beat
  env: python
  region: oregon
  branch: main
  autoDeploy: true
  buildCommand: pip install ./shared && pip install -r backend/requirements.txt
  startCommand: celery -A backend.workers.celery_app beat --loglevel=info
  envVars:
    - key: APP_ENV
      value: dev
    - key: PYTHON_VERSION
      value: 3.11.0
    - key: CELERY_BROKER_URL
      fromService:
        name: omnidrop-redis
        type: redis
        property: connectionString
    - key: CELERY_RESULT_BACKEND
      fromService:
        name: omnidrop-redis
        type: redis
        property: connectionString
    - fromGroup: omnidrop-secrets
```

Step 3. Commit and push to `main`. Render auto-deploys and provisions `omnidrop-beat`.

Step 4. Confirm Beat is running:
- Render Dashboard → **Services → `omnidrop-beat` → Logs**
- Look for: `beat: Starting...` and `Scheduler: Sending due task ...`

Step 5. Verify a task was picked up by the worker:
- Open Flower: `https://omnidrop-flower.onrender.com`
- Check the **Tasks** tab for recent Beat-dispatched tasks

Step 6. Tell Lead: `"SOP-BEAT-1 complete. omnidrop-beat deployed and dispatching tasks. Resume [current task name]."`

Done when: Beat logs show `Scheduler: Sending due task` at the expected schedule time
and Flower shows the task executed successfully.

---

### SOP-BEAT-2: Debug a Missed or Stuck Scheduled Task

**When:** A scheduled task did not run at the expected time, or is showing as
`PENDING`/`STARTED` in Flower for an unusually long time.
**Time:** ~10–20 minutes

Step 1. Confirm Beat is running.

```
Render Dashboard → Services → omnidrop-beat → check status is "Live"
```

If Beat is not live: check the deploy logs for startup errors. Most common cause is
a missing env var — confirm `CELERY_BROKER_URL` is resolved in the service's
Environment tab.

Step 2. Check Beat logs for dispatch evidence.

```
Render Dashboard → Services → omnidrop-beat → Logs
```

Search for `Sending due task [task-name]`. If the line is present, Beat dispatched
the task. If absent, the schedule may be misconfigured — verify the `crontab`
definition and confirm the Beat process restarted after the last code deploy.

Step 3. Check the worker for execution.

```
https://omnidrop-flower.onrender.com → Tasks → filter by task name
```

If the task is in `PENDING` state for more than a few seconds, the worker is not
processing it. Check `omnidrop-worker` status in Render.

If the task is in `FAILURE` state: click the task UUID in Flower to see the
exception traceback. Also check Sentry for the same event.

Step 4. Manually trigger the task to unblock.

```bash
celery -A backend.workers.celery_app call backend.workers.scheduled_tasks.<task_name>
```

This dispatches a one-off execution immediately, bypassing Beat.

Step 5. If the task succeeds manually but fails on schedule: the issue is likely in
the Beat process (schedule misconfiguration, stale `celerybeat-schedule` file). Restart
`omnidrop-beat` from the Render dashboard — the file-based schedule store resets on
restart.

Step 6. Tell Lead: `"SOP-BEAT-2 complete. [task_name] issue resolved: [brief description]. Resume [current task name]."`

---

### SOP-BEAT-3: Deploy a Schedule Change

**When:** Changing the cron schedule of an existing task (e.g., moving
`cleanup_stale_jobs` from 01:00 to 02:00 UTC).
**Time:** ~5 minutes

Step 1. Edit the `crontab(...)` for the target task in
`backend/workers/celery_app.py` `beat_schedule`.

Step 2. Commit and push to `main`. `omnidrop-beat` auto-deploys.

Step 3. Confirm the new schedule is active:

```
Render Dashboard → Services → omnidrop-beat → Logs
```

After Beat restarts, it logs its loaded schedule. Confirm the task shows the updated
time.

Step 4. If the change is time-sensitive, manually restart `omnidrop-beat`:
- Render Dashboard → **Services → `omnidrop-beat` → Manual Deploy → Deploy latest commit**

Step 5. Tell Lead: `"SOP-BEAT-3 complete. [task_name] schedule updated to [new crontab]. Beat redeployed. Resume [current task name]."`

---

### SOP-BEAT-4: Remove a Scheduled Task

**When:** A scheduled task is being retired or temporarily suspended.
**Time:** ~5 minutes

Step 1. Open `backend/workers/celery_app.py`.

Step 2. Remove (or comment out) the task's entry from `beat_schedule`. Do NOT delete
the task function from `scheduled_tasks.py` — keep the function in place in case the
schedule needs to be restored.

Step 3. Commit and push to `main`. `omnidrop-beat` auto-deploys and will no longer
dispatch that task.

Step 4. Confirm in Beat logs that no `Sending due task [task-name]` lines appear
at the previously scheduled time.

Step 5. Tell Lead: `"SOP-BEAT-4 complete. [task_name] removed from beat_schedule. Beat redeployed. Resume [current task name]."`
