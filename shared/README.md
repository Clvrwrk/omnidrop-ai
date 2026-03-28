# omnidrop-shared

Shared Python package containing Pydantic models and constants used by both
the `backend/` and `workers/` services.

## Install

```bash
# From backend/ or workers/ directory:
pip install -e ../../shared

# Or via requirements.txt entry:
-e ../../shared
```

## Contents

| Module | Description |
|--------|-------------|
| `shared/models/acculynx.py` | AccuLynx webhook payload models |
| `shared/models/jobs.py` | Temporal workflow input/output models |
| `shared/constants.py` | Rate limits, API URLs, queue names |

## Rules

- No service-specific imports (no FastAPI, no Temporal SDK, no Supabase)
- Only `pydantic` as a runtime dependency
- All models must be strictly typed
