# OmniDrop AI — Omni-Intake Agent

High-volume AI document ingestion and analytics platform for roofing accounting teams,
integrating with the AccuLynx API.

## Architecture Overview

```
AccuLynx Webhook → FastAPI (validate + ack 204) → Temporal Workflow → AI Extraction → Supabase
AccuLynx REST API → dlt Pipeline → Supabase (historical sync)
Supabase → Next.js Frontend (dashboard, analytics, settings)
```

**Environments:**
| Environment | URL | Purpose |
|-------------|-----|---------|
| Local | localhost | Active development |
| Dev | omnidrop.dev | Integration testing |
| Sandbox | sandbox.omnidrop.dev | AI agent experimentation |
| Production | omnidrop.ai | Live |

Each environment has its own Supabase project and Temporal namespace.

---

## Prerequisites

- Python 3.11+
- Node.js 20+
- Docker Desktop
- [Supabase CLI](https://supabase.com/docs/guides/cli) (`brew install supabase/tap/supabase`)
- [Temporal CLI](https://docs.temporal.io/cli) (`brew install temporal`)

---

## First-Time Setup

```bash
# 1. Clone and enter repo
git clone <repo-url> omnidrop-ai && cd omnidrop-ai

# 2. Copy env template and fill in your values
cp .env.example .env
# Edit .env with real Supabase, Anthropic, and AccuLynx credentials

# 3. Install all dependencies
make install

# 4. Initialize the Next.js frontend (run once — skips if already initialized)
cd frontend
npx create-next-app@latest . --typescript --tailwind --eslint --app --import-alias "@/*"

# 5. Install Shadcn UI (run once)
npx shadcn@latest init
cd ..

# 6. Initialize dlt rest-api pipeline toolkit
cd data_pipelines
pip install "dlt[rest_api]"
# Copy the secrets template — fill in AccuLynx Bearer token
cp .dlt/secrets.toml.example .dlt/secrets.toml
cd ..

# 7. Apply database migrations
make migrate
```

---

## Running the Development Environment

```bash
make dev
```

This starts:
- **Temporal dev server** (Docker) — UI at http://localhost:8233
- **FastAPI backend** — Docs at http://localhost:8000/docs
- **Temporal workers** — Connects to local Temporal
- **Next.js frontend** — http://localhost:3000

---

## Key Commands

| Command | Description |
|---------|-------------|
| `make install` | Install all dependencies |
| `make dev` | Start full local dev environment |
| `make lint` | Run ruff + mypy + eslint + tsc |
| `make test` | Run pytest (backend + workers) + vitest (frontend) |
| `make migrate` | Apply Supabase migrations |
| `make build` | Build Docker images |
| `make clean` | Stop containers + clean build artifacts |

---

## Project Structure

```
omnidrop-ai/
├── frontend/          # Next.js 15 (App Router) — dashboard, analytics, settings
├── backend/           # FastAPI — webhook receiver, API routes
├── workers/           # Temporal workers — AI processing, AccuLynx sync
├── shared/            # Shared Python package — Pydantic models, constants
├── data_pipelines/    # dlt pipelines — AccuLynx historical data sync
├── supabase/          # Database migrations and seed data
└── .github/           # CI/CD workflows
```

---

## AccuLynx Integration Notes

- **Rate limits:** 30 req/sec per IP, 10 req/sec per API key
- **Webhook timeout:** AccuLynx expects a 200–299 response within **10 seconds**
- The `/api/v1/webhooks/acculynx` endpoint ONLY validates + acks — all processing
  happens inside a Temporal workflow
- Webhook payloads are verified via HMAC-SHA256 signature (`X-AccuLynx-Signature` header)
- **Never hardcode** the AccuLynx API key or Bearer token — use `.env` or `.dlt/secrets.toml`

---

## Secrets Management

| Secret | Location |
|--------|----------|
| All app secrets | `.env` (gitignored) |
| dlt AccuLynx token | `data_pipelines/.dlt/secrets.toml` (gitignored) |
| CI/CD secrets | GitHub Actions repository secrets |

Templates for all env files: `.env.example`, `.env.dev.example`, `.env.sandbox.example`
