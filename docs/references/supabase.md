# Supabase — OmniDrop Reference

## 1. What It Does Here

Supabase is OmniDrop's primary data store: PostgreSQL with pgvector for semantic
search, Row Level Security for multi-tenant data isolation, and Storage for raw
document files. Every layer of the backend touches it — FastAPI endpoints query it
directly, Celery workers write pipeline results to it via the service role key, and
the Next.js frontend reads it through the anon key (via the FastAPI layer, never
directly). The async Python client lives in `backend/services/supabase_client.py`.
Migrations live in `supabase/migrations/` and are applied in numeric order (00001
through 00005 as of Beta V1.0).

## 2. Credentials & Environment Variables

| Variable | Where to Find It | Used By |
|---|---|---|
| `SUPABASE_URL` | Supabase Dashboard → Project Settings → API → Project URL | Backend, Workers |
| `SUPABASE_KEY` | Supabase Dashboard → Project Settings → API → Project API Keys → `anon` `public` | Frontend (anon reads only) |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase Dashboard → Project Settings → API → Project API Keys → `service_role` `secret` | Backend, Workers — **never expose to frontend** |

**Project URLs (derived from project ref):**

| Environment | Project ID | URL |
|---|---|---|
| omnidrop-dev | `njlbjdlicbmqvvegrics` | `https://njlbjdlicbmqvvegrics.supabase.co` |
| omnidrop-sandbox | `rnhmvcpsvtqjlffpsayu` | `https://rnhmvcpsvtqjlffpsayu.supabase.co` |
| omnidrop-prod | `zxxyscxoyqqvmlarpwdh` | `https://zxxyscxoyqqvmlarpwdh.supabase.co` |

**Actual key values:** [ASK USER] — retrieve from Supabase Dashboard per SOP-SUPABASE-1 below.

## 3. CLI

```bash
# Install
npm install -g supabase

# Authenticate (uses your personal access token)
supabase login

# Link to a project (run from repo root)
supabase link --project-ref njlbjdlicbmqvvegrics   # omnidrop-dev
supabase link --project-ref zxxyscxoyqqvmlarpwdh   # omnidrop-prod

# Apply all pending migrations to the linked project
supabase db push

# Pull remote schema into local migration file (inspection only — do not overwrite migrations/)
supabase db pull --schema public

# Check migration status (what's applied vs pending)
supabase migration list

# Run a one-off SQL query against the linked project
supabase db execute --file path/to/query.sql

# Generate TypeScript types from the live schema
supabase gen types typescript --project-id njlbjdlicbmqvvegrics > frontend/types/supabase.ts

# Storage: list buckets
supabase storage ls

# Storage: upload a file
supabase storage cp ./local-file.pdf ss:///documents/local-file.pdf

# Open Supabase Studio for linked project
supabase studio
```

## 4. MCP (Claude Code)

All Supabase operations during agent sessions should use MCP tools first. CLI is
the fallback when MCP is unavailable.

| Operation | Preferred Tool | Example params |
|---|---|---|
| Inspect table schema | `mcp__plugin_supabase_supabase__execute_sql` | `{ "project_id": "njlbjdlicbmqvvegrics", "query": "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'jobs'" }` |
| Apply DDL migration | `mcp__plugin_supabase_supabase__apply_migration` | `{ "project_id": "njlbjdlicbmqvvegrics", "name": "00006_...", "query": "ALTER TABLE ..." }` |
| List applied migrations | `mcp__plugin_supabase_supabase__list_migrations` | `{ "project_id": "njlbjdlicbmqvvegrics" }` |
| List all tables | `mcp__plugin_supabase_supabase__list_tables` | `{ "project_id": "njlbjdlicbmqvvegrics", "schemas": ["public"], "verbose": true }` |
| Check RLS policies | `mcp__plugin_supabase_supabase__execute_sql` | `{ "query": "SELECT tablename, policyname, cmd FROM pg_policies WHERE schemaname = 'public'" }` |
| List projects | `mcp__plugin_supabase_supabase__list_projects` | `{}` |
| Search Supabase docs | `mcp__plugin_supabase_supabase__search_docs` | `{ "query": "row level security" }` |

**Important:** `apply_migration` records the migration in Supabase's internal history
table so it cannot be re-run accidentally. Always use it for DDL. Use `execute_sql`
for read-only inspection only.

**Schema restriction:** Never write functions into the `auth` schema from migrations —
Supabase managed instances deny it. Place all custom functions in `public` schema.
Example: use `public.current_org_id()` not `auth.organization_id()`.

## 5. Direct API

Supabase exposes a PostgREST API at `<SUPABASE_URL>/rest/v1/`. All table operations
are available via HTTP. Prefer the Python SDK in backend code — use curl only for
debugging or one-off admin queries.

```bash
# List rows from a table (anon key — subject to RLS)
curl -X GET "https://njlbjdlicbmqvvegrics.supabase.co/rest/v1/organizations" \
  -H "apikey: $SUPABASE_KEY" \
  -H "Authorization: Bearer $SUPABASE_KEY"

# Insert a row (service role key — bypasses RLS)
curl -X POST "https://njlbjdlicbmqvvegrics.supabase.co/rest/v1/jobs" \
  -H "apikey: $SUPABASE_SERVICE_ROLE_KEY" \
  -H "Authorization: Bearer $SUPABASE_SERVICE_ROLE_KEY" \
  -H "Content-Type: application/json" \
  -H "Prefer: return=representation" \
  -d '{"organization_id": "...", "status": "queued"}'

# Execute a raw SQL query via Supabase Management API
curl -X POST "https://api.supabase.com/v1/projects/njlbjdlicbmqvvegrics/database/query" \
  -H "Authorization: Bearer $SUPABASE_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "SELECT COUNT(*) FROM jobs WHERE status = '\''failed'\''"}'

# Storage: get a signed URL for a document (1-hour expiry)
curl -X POST "https://njlbjdlicbmqvvegrics.supabase.co/storage/v1/object/sign/documents/path/to/file.pdf" \
  -H "apikey: $SUPABASE_SERVICE_ROLE_KEY" \
  -H "Authorization: Bearer $SUPABASE_SERVICE_ROLE_KEY" \
  -H "Content-Type: application/json" \
  -d '{"expiresIn": 3600}'
```

## 6. OmniDrop-Specific Patterns

### Client instantiation

```python
# backend/services/supabase_client.py — singleton async client
# Always use this; never instantiate a new client elsewhere.
from backend.services.supabase_client import get_supabase_client

client = await get_supabase_client()  # Uses SUPABASE_SERVICE_ROLE_KEY
```

Workers and FastAPI endpoints always use the service role key. This bypasses RLS
intentionally — workers must write across tenant boundaries (e.g., system_config
reads). Frontend never calls Supabase directly; it goes through FastAPI endpoints.

### RLS helper function

```sql
-- Defined in migration 00005. Resolves the WorkOS org ID from the JWT
-- to OmniDrop's internal organization_id UUID.
-- Use in all RLS policies that need org-scoping.
SELECT public.current_org_id();
-- Returns: UUID matching organizations.organization_id, or NULL if no JWT
```

### All 13 tables (as of migration 00005)

| Table | Scoped By | RLS |
|---|---|---|
| `organizations` | `workos_org_id = jwt.org_id` | ✅ |
| `locations` | `organization_id = current_org_id()` | ✅ |
| `jobs` | `organization_id = current_org_id()` | ✅ |
| `intake_events` | via `jobs` subquery | ✅ |
| `documents` | `organization_id = current_org_id()` | ✅ |
| `invoices` | via `documents` subquery | ✅ |
| `line_items` | via `invoices → documents` subquery | ✅ |
| `document_embeddings` | via `locations` subquery | ✅ |
| `pricing_contracts` | `organization_id = current_org_id()` | ✅ |
| `revenue_findings` | `organization_id = current_org_id()` | ✅ |
| `bounce_back_log` | `organization_id = current_org_id()` | ✅ |
| `context_reference_examples` | `organization_id = current_org_id()` | ✅ |
| `system_config` | global — read-only for authenticated | ✅ |

### Writing a new migration

1. Name the file `NNNNN_snake_case_description.sql` (next number after 00005).
2. Use `apply_migration` MCP tool — it records history and prevents re-runs.
3. Save the file to `supabase/migrations/` so it's tracked in git.
4. For functions: always use `public` schema. Never `auth` schema.
5. For RLS: always add `ALTER TABLE x ENABLE ROW LEVEL SECURITY` before policies.
6. Use `CREATE POLICY ... IF NOT EXISTS` when re-running is a risk.

### pgvector search function

The `match_documents` RPC function is used by `GET /api/v1/search`. Embeddings are
`VECTOR(1024)` — Voyage AI `voyage-3` dimension. The IVFFlat index on
`document_embeddings.embedding` uses `vector_cosine_ops` with `lists = 100`.

```python
# Semantic search via RPC
result = await client.rpc(
    "match_documents",
    {
        "query_embedding": embedding_vector,   # list[float], len=1024
        "match_threshold": 0.7,
        "match_count": 10,
    }
).execute()
```

### Storage bucket

Raw document files are stored in Supabase Storage. The bucket name is `documents`.
Signed URLs (1-hour expiry) are generated by `GET /api/v1/triage/{document_id}` for
the split-screen HITL review UI. The `raw_path` column on the `documents` table
holds the Storage object path.

```python
# Generate signed URL — backend only, service role key
signed = await client.storage.from_("documents").create_signed_url(raw_path, 3600)
document_url = signed["signedURL"]
```

### Context score rubric — live recalibration

The scoring rubric lives in `system_config`, not in code. To recalibrate weights
without a deploy:

```sql
UPDATE system_config
SET value = '{
  "identifiability": {
    "vendor_name_present": 15,
    "job_or_po_number_present": 10,
    "date_present": 5
  },
  "content_quality": {
    "legible_machine_readable_text": 20,
    "financial_data_present": 15,
    "document_type_unambiguous": 5
  },
  "metadata_and_context": {
    "file_metadata_present": 10,
    "linkable_to_known_vendor_or_job": 10,
    "specific_enough_to_act_on": 10
  }
}'
WHERE key = 'context_score_rubric';
```

### Known gotchas

- **Never put `async` Supabase calls inside a synchronous Celery task directly.**
  Wrap with `asyncio.get_event_loop().run_until_complete(...)`. See `intake_tasks.py`
  for the established pattern.
- **`maybe_single()` returns `None` data, not an error, when no row is found.**
  Always check `result.data` before accessing fields.
- **Service role key bypasses RLS entirely.** A bug in worker code can silently read
  or write data from any tenant. Double-check org scoping in worker queries even
  though RLS won't catch it.
- **Migrations are applied in numeric order.** If you skip a number, Supabase CLI
  will warn but still apply. Keep numbers sequential.
- **The `vendor_baseline_prices` view requires `sample_count >= 3`.** Always filter
  with `.gte("sample_count", 3)` when querying it — the view itself enforces this
  via `HAVING COUNT(*) >= 3` but the filter makes intent explicit in code.

## 7. Human SOPs

### SOP-SUPABASE-1: Retrieve and Set Supabase Credentials for an Environment

**When:** First-time environment setup, or when rotating keys after a security event.
**Time:** ~5 minutes
**Prerequisite:** You have access to the Supabase organisation ([ASK USER] — check Supabase Dashboard → Organisation Settings for the org ID) and the relevant `.env` file is open in your editor.

Step 1. Go to `https://supabase.com/dashboard/project/<PROJECT_REF>/settings/api`
(replace `<PROJECT_REF>` with `njlbjdlicbmqvvegrics` for dev, `rnhmvcpsvtqjlffpsayu`
for sandbox, or `zxxyscxoyqqvmlarpwdh` for prod).

Step 2. Under **"Project URL"**, copy the value — it looks like:
`https://njlbjdlicbmqvvegrics.supabase.co`
Paste into your `.env` as `SUPABASE_URL=https://njlbjdlicbmqvvegrics.supabase.co`

Step 3. Under **"Project API Keys"**, find the row labelled **`anon` `public`**.
Copy the key. Paste into your `.env` as `SUPABASE_KEY=eyJ...`

Step 4. Find the row labelled **`service_role` `secret`**. Click **"Reveal"**.
Copy the key. Paste into your `.env` as `SUPABASE_SERVICE_ROLE_KEY=eyJ...`

Step 5. Confirm the `.env` file is listed in `.gitignore` before saving.
**Never commit either key to git.**

Step 6. Tell Claude: `"Supabase SOP-1 complete. SUPABASE_URL, SUPABASE_KEY, and SUPABASE_SERVICE_ROLE_KEY are set for omnidrop-dev. Resume [current task name]."`

✅ Done when: `python -c "from backend.core.config import get_settings; s = get_settings(); print(s.supabase_url)"` prints the project URL without error.

⚠️ If you see `ValidationError: SUPABASE_URL field required`: the `.env` file is not being loaded — confirm `python-dotenv` is installed and the file is at the repo root.

---

### SOP-SUPABASE-2: Apply a Migration Manually (When MCP apply_migration Is Unavailable)

**When:** MCP tool permission is denied and a DDL migration must be applied to a live project.
**Time:** ~3 minutes
**Prerequisite:** You have the SQL content ready and the Supabase CLI is linked to the target project (`supabase link --project-ref <ref>`).

Step 1. Save the migration SQL to `supabase/migrations/NNNNN_description.sql`.

Step 2. Run: `supabase db push`
This applies all pending migrations in numeric order.

Step 3. Verify the migration landed:
```bash
supabase migration list
```
The new migration should appear with a timestamp in the **"Applied At"** column.

Step 4. Run the verification query in Supabase Studio or via CLI:
```sql
SELECT tablename, COUNT(*) AS policy_count
FROM pg_policies
WHERE schemaname = 'public'
GROUP BY tablename
ORDER BY tablename;
```

Step 5. Tell Claude: `"Supabase SOP-2 complete. Migration NNNNN is applied to [environment]. Resume [current task name]."`

✅ Done when: the migration appears in `supabase migration list` with an applied timestamp.

⚠️ If you see `ERROR: relation already exists`: the migration was already applied manually via SQL editor. Add `IF NOT EXISTS` guards and re-run, or mark it applied with `supabase migration repair`.

---

### SOP-SUPABASE-3: Create and Configure the `documents` Storage Bucket

**When:** First deploy to a new environment — the Storage bucket does not exist yet.
**Time:** ~5 minutes
**Prerequisite:** `SUPABASE_SERVICE_ROLE_KEY` is set for the target environment.

Step 1. Go to `https://supabase.com/dashboard/project/<PROJECT_REF>/storage/buckets`

Step 2. Click **"New bucket"**.

Step 3. In the **"Name"** field, enter: `documents`

Step 4. Leave **"Public bucket"** unchecked — this bucket is private. All access is via signed URLs generated by the backend.

Step 5. Click **"Save"**.

Step 6. Under **"Policies"** for the `documents` bucket, confirm that no public policies exist. The backend accesses Storage using the service role key, which bypasses Storage RLS.

Step 7. Tell Claude: `"Supabase SOP-3 complete. documents bucket is created in [environment]. Resume [current task name]."`

✅ Done when: the `documents` bucket appears in the Storage section and `public` is shown as **false**.

⚠️ If uploads fail with `Bucket not found`: the bucket name in code must match exactly — `documents` (lowercase, no trailing slash).
