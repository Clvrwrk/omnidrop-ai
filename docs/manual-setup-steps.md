# Manual Setup Steps
# Things Claude cannot do — complete these before spawning the agent team

**Last updated:** 2026-03-28
**Estimated total time:** ~25 minutes

---

## Status: What's Already Done

| Task | Status |
|---|---|
| Git repo initialized + first commit | ✅ Done |
| Python 3.11 installed | ✅ Done |
| tmux installed | ✅ Done |
| gh CLI installed | ✅ Done |
| npm dependencies installed (`frontend/`) | ✅ Done |
| Python venv created + backend deps installed (`.venv/`) | ✅ Done |
| 3 Supabase projects provisioned (dev/sandbox/prod) | ✅ Done |
| All env files populated (except service role keys) | ✅ Done |
| Agent team skills configured | ✅ Done |

---

## Step 1 — Supabase Service Role Keys (~5 min)

Three keys, one per project. Claude cannot retrieve these — they're only available in the dashboard.

For each project, go to: **app.supabase.com → [project] → Project Settings → API → `service_role` secret → Reveal**

| Project | Dashboard URL | Paste into |
|---|---|---|
| omnidrop-dev | app.supabase.com → omnidrop-dev | `.env` and `.env.dev` — `SUPABASE_SERVICE_ROLE_KEY=` |
| omnidrop-sandbox | app.supabase.com → omnidrop-sandbox | `.env.sandbox` — `SUPABASE_SERVICE_ROLE_KEY=` |
| omnidrop-prod | app.supabase.com → omnidrop-prod | Render env group (Step 5) |

---

## Step 2 — GitHub Repository + Push (~5 min)

```bash
# 1. Create the repo on GitHub (go to github.com/new, name it omnidrop-ai, private)

# 2. Authenticate gh CLI (opens browser)
gh auth login

# 3. Add remote and push
cd "/Users/chussey/Library/CloudStorage/Dropbox-AIA4/AIA4/OmniDrop AI"
git remote add origin https://github.com/YOUR_ORG/omnidrop-ai.git
git push -u origin main
```

Once pushed, go to **render.yaml → Connect repo** in Render dashboard to enable auto-deploy.

---

## Step 3 — Start Docker Desktop (~1 min)

Open **Docker Desktop** from Applications. Wait for the whale icon to stop animating.

Verify: `docker ps` should return without errors.

Local dev won't start without this — Redis runs in Docker.

---

## Step 4 — WorkOS Redirect URIs (~3 min)

Go to: **dashboard.workos.com → Your App → Redirects**

Add all four:
```
http://localhost:3000/callback
https://omnidrop.dev/callback
https://sandbox.omnidrop.dev/callback
https://omnidrop.ai/callback
```

Without these, WorkOS will reject the auth callback with a `redirect_uri_mismatch` error.

---

## Step 5 — Render Environment Group (~5 min)

Go to: **dashboard.render.com → Environment Groups → New Group**

Name it exactly: `omnidrop-secrets`

Add every secret from `.env` (the production values). The Redis URL is injected automatically from the `omnidrop-redis` service — do NOT add it here.

| Key | Value |
|---|---|
| `APP_SECRET_KEY` | (from .env) |
| `SUPABASE_URL` | https://zxxyscxoyqqvmlarpwdh.supabase.co |
| `SUPABASE_KEY` | (prod anon key from Supabase dashboard) |
| `SUPABASE_SERVICE_ROLE_KEY` | (prod service role key from Step 1) |
| `ANTHROPIC_API_KEY` | (from .env) |
| `HOOKDECK_SIGNING_SECRET` | (from .env) |
| `WORKOS_API_KEY` | (from .env) |
| `WORKOS_CLIENT_ID` | (from .env) |
| `WORKOS_COOKIE_PASSWORD` | (from .env) |
| `UNSTRUCTURED_API_KEY` | (from .env) |
| `SENTRY_PYTHON_DSN` | (from .env) |

---

## Step 6 — Hookdeck Workspace Config (~5 min)

Go to: **dashboard.hookdeck.com**

### Create a Source
1. New Source → name it `acculynx-webhooks`
2. Copy the **Source URL** (e.g. `https://events.hookdeck.com/e/src_xxx`)
3. Set this URL as the webhook endpoint in your **AccuLynx account settings**

### Create a Destination
1. New Destination → name it `omnidrop-api-local` (for local dev)
2. URL: `https://YOUR_NGROK_URL/api/v1/webhooks/acculynx` (use ngrok for local tunneling)
3. For dev: URL = `https://api.omnidrop.dev/api/v1/webhooks/acculynx`

### Create a Connection
Connect the `acculynx-webhooks` source → `omnidrop-api-local` destination.

The **Signing Secret** is already in your `.env` as `HOOKDECK_SIGNING_SECRET`.

---

## Step 7 — Supabase CLI (requires Xcode update) (~5 min)

The Supabase CLI install failed because Xcode Command Line Tools are outdated.

```bash
# Option A: Update via System Settings → General → Software Update
# Then: brew install supabase/tap/supabase

# Option B: Force reinstall Xcode tools
sudo rm -rf /Library/Developer/CommandLineTools
sudo xcode-select --install
# Then: brew install supabase/tap/supabase
```

Once installed, run migrations:
```bash
cd "/Users/chussey/Library/CloudStorage/Dropbox-AIA4/AIA4/OmniDrop AI"
supabase link --project-ref njlbjdlicbmqvvegrics  # omnidrop-dev
supabase db push
```

---

## Step 8 — Activate Python venv in every terminal

The venv is at `.venv/`. Activate it before running any Python commands:

```bash
cd "/Users/chussey/Library/CloudStorage/Dropbox-AIA4/AIA4/OmniDrop AI"
source .venv/bin/activate
```

Add this to your shell profile to auto-activate when entering the directory, or just run it each session.

---

## Launch Local Dev (after all steps above)

```bash
# Terminal 1 — Redis (requires Docker running)
docker compose up -d redis

# Terminal 2 — FastAPI backend
source .venv/bin/activate
uvicorn backend.api.main:app --reload --port 8000

# Terminal 3 — Celery worker
source .venv/bin/activate
celery -A backend.workers.celery_app worker --loglevel=info --concurrency=2

# Terminal 4 — Next.js frontend
cd frontend && npm run dev
```

URLs:
- Frontend: http://localhost:3000
- API docs: http://localhost:8000/docs
- Flower (task monitor): run `celery -A backend.workers.celery_app flower` → http://localhost:5555

---

## Spawn the Agent Team (final step)

```bash
# From project root, inside tmux
tmux -CC  # iTerm2 split-pane mode

# Then open Claude Code and paste the spawn prompt from:
# docs/agent-team-spawn-prompt.md
```

Pre-flight checklist before spawning:
- [ ] Docker Desktop running (`docker ps` works)
- [ ] Service role keys filled in all `.env` files
- [ ] GitHub repo created and pushed
- [ ] WorkOS redirect URIs registered
- [ ] Inside tmux session
