# Voyage AI — OmniDrop Reference

## 1. What It Does Here

Voyage AI generates the 1024-dimensional text embeddings that power OmniDrop's
semantic search feature. The `chunk_and_embed` Celery task calls
`ClaudeService.chunk_for_rag()`, which first asks Claude to split an unstructured
document into semantic chunks (150–300 words each), then sends all chunk texts to
Voyage AI in a single batched `embed()` call using the `voyage-3` model. The
resulting 1024-dim float vectors are written to the `document_embeddings` table in
Supabase pgvector and queried at search time via the `match_documents` RPC function
with cosine similarity. Voyage AI is used exclusively for embeddings — all language
reasoning (scoring, extraction, classification) stays with Claude.

Files that touch Voyage AI:
- `backend/services/claude_service.py` — `_get_voyage_client()`, `chunk_for_rag()`
- `backend/workers/intake_tasks.py` — `chunk_and_embed` task calls `chunk_for_rag()`
- `backend/core/config.py` — `VOYAGE_API_KEY` setting

## 2. Credentials & Environment Variables

| Variable | Where to Find It | Used By |
|---|---|---|
| `VOYAGE_API_KEY` | https://dash.voyageai.com/api-keys — log in, click **"API Keys"**, copy the key | Backend workers only — never expose to frontend |

**Actual key value:** [ASK USER] — retrieve via SOP-VOYAGEAI-1 below.

## 3. CLI

Voyage AI has no dedicated CLI tool. All interaction is via the Python SDK or HTTP
API. The SDK is the only interface used in this codebase.

```bash
# Install the SDK
pip install voyageai

# Verify installation and check available models
python -c "import voyageai; print(voyageai.__version__)"

# Quick smoke test (replace with your actual key)
python - <<'EOF'
import voyageai
client = voyageai.Client(api_key="YOUR_KEY")
result = client.embed(["Hello, roofing world"], model="voyage-3")
print(f"Dimension: {len(result.embeddings[0])}")  # Should print: 1024
EOF

# Check the package in the project's requirements
grep voyageai requirements.txt
```

## 4. MCP (Claude Code)

Voyage AI has no MCP server. Use the Python SDK directly when writing or testing
embedding code. For documentation lookups, use the Context7 MCP tool:

| Operation | Preferred Tool | Example |
|---|---|---|
| Look up SDK method signatures | `mcp__plugin_context7_context7__resolve-library-id` then `mcp__plugin_context7_context7__query-docs` | `{ "query": "voyageai embed batch" }` |
| Test embedding call in isolation | Python REPL via Bash tool | `python -c "import voyageai; ..."` |

## 5. Direct API

The Voyage AI REST API is available at `https://api.voyageai.com/v1/`. The SDK
wraps it — use curl only for debugging or one-off manual checks.

```bash
# Embed a single text string
curl -X POST "https://api.voyageai.com/v1/embeddings" \
  -H "Authorization: Bearer $VOYAGE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "voyage-3",
    "input": ["GAF Timberline HDZ 30-year architectural shingle"]
  }'

# Response shape:
# {
#   "object": "list",
#   "data": [
#     { "object": "embedding", "embedding": [0.012, -0.034, ...], "index": 0 }
#   ],
#   "model": "voyage-3",
#   "usage": { "total_tokens": 12 }
# }

# Embed a batch of texts (more efficient — always prefer batching)
curl -X POST "https://api.voyageai.com/v1/embeddings" \
  -H "Authorization: Bearer $VOYAGE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "voyage-3",
    "input": [
      "Line item: GAF Timberline HDZ 30-year shingle",
      "Terms: Net 30. Payment due upon receipt.",
      "Job site: 1234 Oak Street, Denver CO"
    ]
  }'
```

## 6. OmniDrop-Specific Patterns

### Client instantiation

```python
# backend/services/claude_service.py — singleton pattern
import voyageai
from backend.core.config import settings

_voyage_client: voyageai.Client | None = None

def _get_voyage_client() -> voyageai.Client:
    """Returns a singleton Voyage AI client. Called only from chunk_for_rag()."""
    global _voyage_client
    if _voyage_client is None:
        _voyage_client = voyageai.Client(api_key=settings.voyage_api_key)
    return _voyage_client
```

Never instantiate `voyageai.Client` outside this function. The singleton is
intentional — Celery workers are long-lived processes and client creation has
connection overhead.

### Embedding a batch of chunks (the production pattern)

```python
# From ClaudeService.chunk_for_rag() — this is the exact production call
EMBEDDING_MODEL = "voyage-3"
EMBEDDING_DIMENSION = 1024

voyage_client = _get_voyage_client()

# Always embed ALL chunks in one call — one API round-trip per document
chunk_texts = [c["chunk_text"] for c in chunks]
embedding_result = voyage_client.embed(chunk_texts, model=EMBEDDING_MODEL)

# embedding_result.embeddings is a list[list[float]]
# embedding_result.embeddings[i] corresponds to chunk_texts[i]
for i, chunk in enumerate(chunks):
    vector = embedding_result.embeddings[i]   # list[float], len == 1024
    assert len(vector) == EMBEDDING_DIMENSION  # Always verify in tests
```

**Never call `embed()` in a loop per chunk.** The SDK supports batching — one call
for the full document's chunk list. This cuts API latency and token count overhead
by the number of chunks (typically 5–20 per document).

### Writing embeddings to Supabase

```python
# Rows written to document_embeddings by _save_embeddings() in intake_tasks.py
row = {
    "document_id": document_id,      # UUID string
    "location_id": location_id,      # UUID string — required for RLS scoping
    "chunk_text": chunk["chunk_text"],
    "embedding": embedding_result.embeddings[i],  # list[float], len=1024
    "metadata": {
        "topic": chunk.get("topic", ""),
        "chunk_index": i,
    },
}
# Inserted via: await client.table("document_embeddings").insert(rows).execute()
```

The `embedding` column in Supabase is `VECTOR(1024)`. Supabase's Python client
serialises Python `list[float]` to the pgvector wire format automatically — no
manual conversion needed.

**Important:** `location_id` is `NOT NULL` on `document_embeddings`. If a job has
no `location_id` (org-level upload), the `chunk_and_embed` task must resolve a
`location_id` before calling `_save_embeddings()` — or the insert will fail. This
is a known gap; handle it upstream in the task before embedding.

### Semantic search query

```python
# At search time: embed the user's query, then call the match_documents RPC
query_embedding = voyage_client.embed([user_query], model="voyage-3").embeddings[0]

result = await supabase_client.rpc(
    "match_documents",
    {
        "query_embedding": query_embedding,  # list[float], len=1024
        "match_threshold": 0.7,
        "match_count": 10,
    }
).execute()
```

### Model and dimension reference

| Constant | Value | Where defined |
|---|---|---|
| `ClaudeService.EMBEDDING_MODEL` | `"voyage-3"` | `backend/services/claude_service.py` |
| `ClaudeService.EMBEDDING_DIMENSION` | `1024` | `backend/services/claude_service.py` |
| pgvector column type | `VECTOR(1024)` | `supabase/migrations/00002_application_tables.sql` |
| IVFFlat index | `vector_cosine_ops`, `lists=100` | same migration |

**Never change the model or dimension without a migration to recreate the
`document_embeddings.embedding` column and rebuild the IVFFlat index.** Mismatched
dimensions will cause pgvector to reject inserts with a dimension mismatch error.

### Rate limits and token usage

Voyage AI rate limits are per API key. As of the `voyage-3` model release:
- **Tokens per minute:** [ASK USER] — check current limits at https://dash.voyageai.com
- **Requests per minute:** [ASK USER] — same dashboard

For OmniDrop's workload (5–20 chunks per document, ~150–300 words each), a single
`chunk_and_embed` task consumes roughly 1,000–5,000 tokens. No rate-limit handling
is currently implemented in the task — if 429s appear under load, add a
`self.retry(countdown=30)` in the `except Exception` block of `chunk_and_embed`,
matching the pattern already in place for AccuLynx rate limits.

### Known gotchas

- **`voyage-3` is the only approved model for this codebase.** Do not switch to
  `voyage-3-lite` (512-dim) or `voyage-large-2` (1536-dim) without a migration
  — the pgvector column is fixed at `VECTOR(1024)`.
- **`embedding_result.embeddings` is a list, not a numpy array.** Access elements
  with `[i]`, not `.tolist()` or numpy slicing.
- **The `input` argument to `client.embed()` is always a `list[str]`**, even for a
  single text. Passing a bare string raises a type error.
- **Empty chunk list:** If Claude returns zero chunks (rare, but possible on very
  short documents), `chunk_texts` will be an empty list. The Voyage AI SDK returns
  an empty `embeddings` list in this case — safe, but log a warning so it can be
  investigated.
- **`location_id` is required on every `document_embeddings` row.** It is the RLS
  scope key. If `location_id` is `None` (org-level upload), the insert will fail
  the NOT NULL constraint. Handle this before calling `_save_embeddings()`.

## 7. Human SOPs

### SOP-VOYAGEAI-1: Retrieve and Set the Voyage AI API Key

**When:** First-time environment setup, or when rotating the key after a security event.
**Time:** ~3 minutes
**Prerequisite:** You have a Voyage AI account and the relevant `.env` file is open
in your editor.

Step 1. Go to https://dash.voyageai.com/api-keys

Step 2. Log in if prompted.

Step 3. Click **"Create new key"** (or copy an existing key by clicking the copy
icon next to it). The key looks like: `pa-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX`

Step 4. Paste the key into your `.env` file as:
`VOYAGE_API_KEY=pa-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX`

Step 5. Confirm `.env` is in `.gitignore`. Never commit this key.

Step 6. Run the smoke test to verify the key works and the dimension is correct:
```bash
python - <<'EOF'
import voyageai, os
client = voyageai.Client(api_key=os.environ["VOYAGE_API_KEY"])
result = client.embed(["test"], model="voyage-3")
assert len(result.embeddings[0]) == 1024, f"Wrong dimension: {len(result.embeddings[0])}"
print("OK — voyage-3 returning 1024-dim vectors")
EOF
```

Step 7. Tell Claude: `"Voyage AI SOP-1 complete. VOYAGE_API_KEY is set. Resume [current task name]."`

✅ Done when: the smoke test prints `OK — voyage-3 returning 1024-dim vectors`
without error.

⚠️ If you see `AuthenticationError`: the key was copied incorrectly or has been
revoked — return to the dashboard and generate a new key.

⚠️ If the assertion fails with a wrong dimension: the model name in the call does
not match `voyage-3` — verify `EMBEDDING_MODEL = "voyage-3"` in
`backend/services/claude_service.py`.

---

### SOP-VOYAGEAI-2: Rebuild the pgvector Embedding Index After a Model Change

**When:** The embedding model or dimension is changed (requires Lead approval — see
gotchas above). This is a rare, high-impact operation.
**Time:** ~15 minutes (index rebuild time scales with row count)
**Prerequisite:** A new migration file has been written that drops and recreates the
`document_embeddings.embedding` column with the new `VECTOR(N)` dimension.

Step 1. Confirm with the Lead that the dimension change is intentional and the
migration file is staged.

Step 2. Apply the migration via `supabase db push` or the `apply_migration` MCP tool
(see `docs/references/supabase.md` SOP-SUPABASE-2).

Step 3. All existing embeddings are now invalid (wrong dimension). Truncate the table:
```sql
TRUNCATE document_embeddings;
```

Step 4. Re-run `chunk_and_embed` for all completed jobs to regenerate embeddings
with the new model. This is a manual re-processing step — there is no automated
backfill job yet.

Step 5. Monitor the IVFFlat index build. With `lists=100`, Postgres requires at
least 100 rows before the index is useful. Check with:
```sql
SELECT COUNT(*) FROM document_embeddings;
```

Step 6. Tell Claude: `"Voyage AI SOP-2 complete. Embeddings rebuilt with [model name] at [N]-dim. Resume [current task name]."`

✅ Done when: `SELECT COUNT(*) FROM document_embeddings` returns a non-zero row
count and semantic search returns results.

⚠️ If search returns zero results after rebuild: check that `match_threshold` (0.7)
is not too high for the new model's score distribution — lower it to 0.5 temporarily
to confirm the pipeline is working before tuning upward.
