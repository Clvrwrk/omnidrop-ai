---
name: omnidrop-backend
description: Patterns, rules, and constraints for building OmniDrop AI backend features. Use when writing FastAPI endpoints, Celery tasks, Pydantic models, Hookdeck HMAC verification, AccuLynx API integration, Supabase queries, database migrations, or any Python backend code for OmniDrop AI.
---

# OmniDrop AI — Backend Engineering Skill

## The One Rule That Cannot Break

The `POST /api/v1/webhooks/acculynx` endpoint does EXACTLY four things:

```python
@router.post("/api/v1/webhooks/acculynx", status_code=200)
async def receive_acculynx_webhook(
    request: Request,
    payload: AccuLynxWebhookPayload,  # Pydantic validates — raises 422 if invalid
):
    # Step 1: Verify Hookdeck HMAC signature — raises 401 if invalid
    verify_hookdeck_signature(request)
    # Step 2: Pydantic already validated above (FastAPI handles 422)
    # Step 3: Dispatch to Celery — non-blocking
    process_document.delay(payload.model_dump())
    # Step 4: Return 200 immediately
    return {"status": "accepted"}
```

**This endpoint NEVER:**
- Calls Unstructured.io, Claude, or any AI service
- Writes to Supabase
- Fetches from AccuLynx API
- Does any blocking I/O

---

## HMAC Verification (`backend/core/security.py`)

```python
import hashlib
import hmac
from fastapi import Request, HTTPException
from backend.core.config import settings

async def verify_hookdeck_signature(request: Request) -> None:
    """Verify Hookdeck HMAC-SHA256 signature. Raises 401 if invalid."""
    signature = request.headers.get("x-hookdeck-signature")
    if not signature:
        raise HTTPException(status_code=401, detail="Missing signature")

    body = await request.body()
    expected = hmac.new(
        settings.HOOKDECK_SIGNING_SECRET.encode(),
        body,
        hashlib.sha256
    ).hexdigest()

    # Timing-safe comparison prevents timing attacks
    if not hmac.compare_digest(f"sha256={expected}", signature):
        raise HTTPException(status_code=401, detail="Invalid signature")
```

---

## AccuLynx Multi-Tenant Pattern (Critical)

**There is no global AccuLynx API key.** Each roofing location has its own.

```python
# WRONG — never do this in a Celery task
acculynx_key = settings.ACCULYNX_API_KEY  # Does not exist in production

# CORRECT — fetch per-location key from Supabase at task runtime
@celery_app.task(rate_limit="10/s", bind=True)
def fetch_acculynx_document(self, location_id: str, document_id: str):
    supabase = get_supabase_client()
    result = supabase.table("locations").select("acculynx_api_key").eq("id", location_id).single().execute()
    api_key = result.data["acculynx_api_key"]

    headers = {"Authorization": f"Bearer {api_key}"}
    response = httpx.get(
        f"https://api.acculynx.com/api/v2/documents/{document_id}",
        headers=headers,
        timeout=30,
    )
    response.raise_for_status()
    return response.content
```

---

## Celery Task Patterns

### App configuration (`backend/workers/celery_app.py`)
```python
from celery import Celery
from backend.core.config import settings

celery_app = Celery(
    "omnidrop",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    worker_prefetch_multiplier=1,  # Fair distribution for long-running tasks
)
```

### Rate limits (`backend/workers/intake_tasks.py`)
```python
from backend.workers.celery_app import celery_app

# rate_limit="10/s" = 10 per second per worker per key
# Apply to ALL tasks that call the AccuLynx API
@celery_app.task(rate_limit="10/s", bind=True, max_retries=3)
def process_document(self, job_payload: dict):
    """Main intake task — calls UnstructuredService, then dispatches triage."""
    ...

@celery_app.task(rate_limit="10/s", bind=True, max_retries=3)
def fetch_acculynx_document(self, location_id: str, document_id: str):
    ...

@celery_app.task(bind=True)  # No rate limit — calls Claude, not AccuLynx
def triage_document(self, document_id: str, text_content: str):
    ...

@celery_app.task(bind=True)
def extract_struct(self, document_id: str, text_content: str):
    ...

@celery_app.task(bind=True)
def chunk_and_embed(self, document_id: str, text_content: str):
    ...
```

### Retry pattern for 429s
```python
@celery_app.task(bind=True, max_retries=5)
def fetch_acculynx_document(self, location_id: str, document_id: str):
    try:
        ...
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            raise self.retry(countdown=60, exc=e)  # Back off 60s
        raise
```

---

## Pydantic v2 Models

### Config with env vars (`backend/core/config.py`)
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    APP_ENV: str = "local"
    APP_SECRET_KEY: str
    SUPABASE_URL: str
    SUPABASE_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: str
    ANTHROPIC_API_KEY: str
    HOOKDECK_SIGNING_SECRET: str
    CELERY_BROKER_URL: str
    CELERY_RESULT_BACKEND: str
    WORKOS_API_KEY: str
    WORKOS_CLIENT_ID: str
    WORKOS_COOKIE_PASSWORD: str
    UNSTRUCTURED_API_KEY: str
    SENTRY_PYTHON_DSN: str  # NOTE: NOT SENTRY_DSN

    class Config:
        env_file = ".env"

settings = Settings()
```

### Shared models (`shared/models/`)
```python
# shared/models/acculynx.py
from pydantic import BaseModel
from typing import Optional

class AccuLynxWebhookPayload(BaseModel):
    event_type: str
    job_id: str
    location_id: str
    document_id: Optional[str] = None
    document_url: Optional[str] = None
    timestamp: str

# shared/constants.py
ACCULYNX_RATE_LIMIT = "10/s"
ACCULYNX_IP_RATE_LIMIT = 30  # req/sec — enforced by worker concurrency
CELERY_TASK_QUEUE = "omni-intake"
```

---

## Supabase Async Client (`backend/services/supabase_client.py`)

```python
from supabase import acreate_client, AsyncClient
from backend.core.config import settings
import functools

@functools.lru_cache()
def get_supabase_client() -> AsyncClient:
    """Returns a cached async Supabase client using service role key."""
    return acreate_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_SERVICE_ROLE_KEY  # Server/worker side only
    )
```

### Query patterns
```python
# Insert a job record
await supabase.table("jobs").insert({
    "id": job_id,
    "location_id": location_id,
    "status": "pending",
}).execute()

# Update status
await supabase.table("jobs").update({"status": "processing"}).eq("id", job_id).execute()

# Fetch location API key
result = await supabase.table("locations").select("acculynx_api_key").eq("id", location_id).single().execute()
```

---

## Database Migrations (`supabase/migrations/`)

```sql
-- 00001_init.sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE locations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    acculynx_api_key TEXT NOT NULL,
    connection_status TEXT DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    location_id UUID REFERENCES locations(id),
    acculynx_job_id TEXT,
    status TEXT DEFAULT 'pending', -- pending|processing|completed|failed
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID REFERENCES jobs(id),
    type TEXT, -- structured|unstructured|unknown
    raw_url TEXT,
    processed_at TIMESTAMPTZ
);

CREATE TABLE invoices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id),
    vendor_name TEXT,
    invoice_number TEXT,
    invoice_date DATE,
    due_date DATE,
    subtotal NUMERIC,
    tax NUMERIC,
    total NUMERIC,
    notes TEXT
);

CREATE TABLE line_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_id UUID REFERENCES invoices(id),
    description TEXT,
    quantity NUMERIC,
    unit_price NUMERIC,
    amount NUMERIC
);

CREATE TABLE document_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id),
    chunk_text TEXT NOT NULL,
    embedding vector(1536),
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX ON document_embeddings USING ivfflat (embedding vector_cosine_ops);
```

---

## Sentry Initialization (`backend/core/sentry.py`)

```python
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.celery import CeleryIntegration
from backend.core.config import settings

def init_sentry():
    sentry_sdk.init(
        dsn=settings.SENTRY_PYTHON_DSN,  # NOT SENTRY_DSN
        integrations=[FastApiIntegration(), CeleryIntegration()],
        traces_sample_rate=float(settings.SENTRY_TRACES_SAMPLE_RATE),
        failed_request_status_codes={429, 500, 502, 503},  # Capture 429s
    )
```

---

## File Ownership Rules

| Directory | What Lives Here |
|---|---|
| `backend/api/` | FastAPI routes only — no business logic |
| `backend/workers/` | Celery task signatures — call into services, no AI/DB logic inline |
| `backend/core/` | Config, security (HMAC), Sentry init, logging |
| `backend/services/` | AI + Supabase business logic (owned by AI/QA Engineer) |
| `shared/` | Pydantic models and constants only — no service-specific imports |

---

## Anti-Patterns

- Never write to Supabase inside the webhook endpoint
- Never call Unstructured.io or Claude inside the webhook endpoint
- Never reference `settings.ACCULYNX_API_KEY` in a task — use location_id → DB lookup
- Never use `temporal_client.py` — it is superseded by Celery
- Never use `SENTRY_DSN` — the variable is `SENTRY_PYTHON_DSN`
- Never put `SUPABASE_SERVICE_ROLE_KEY` anywhere near frontend code
- Never use `@celery_app.task` without `rate_limit="10/s"` on AccuLynx fetch tasks
