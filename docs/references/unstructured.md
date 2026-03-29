# Unstructured.io — OmniDrop Reference

## 1. What It Does Here

Unstructured.io is OmniDrop's document parsing layer — the "Omni-Parser." It converts
raw PDF bytes (scanned invoices, MSDS sheets, field manuals, proposals) into a typed
list of text elements before Claude ever sees the content. The `process_document`
Celery task fetches document bytes from AccuLynx, passes them to
`UnstructuredService.partition_document()`, then calls `elements_to_text()` to
produce a plain-text string that flows into `score_context` and all downstream Claude
calls. Unstructured.io is never called from the FastAPI webhook endpoint — only from
within Celery tasks. The service wrapper lives at
`backend/services/unstructured_service.py` and is instantiated as a singleton
client keyed to `UNSTRUCTURED_API_KEY`.

## 2. Credentials & Environment Variables

| Variable | Where to Find It | Used By |
|---|---|---|
| `UNSTRUCTURED_API_KEY` | https://app.unstructured.io/api-keys — log in, click **"API Keys"** in the left nav, copy the key | Backend workers only — never expose to frontend |

**Actual key value:** [ASK USER] — retrieve via SOP-UNSTRUCTURED-1 below.

## 3. CLI

Unstructured.io has no dedicated project CLI. All interaction is via the Python SDK
or HTTP API. The local `unstructured` open-source library also exists but is not used
here — OmniDrop uses the hosted API exclusively via `unstructured-client`.

```bash
# Install the SDK (pinned to ^0.25 per requirements.txt)
pip install "unstructured-client>=0.25,<0.26"

# Verify installation
python -c "import unstructured_client; print(unstructured_client.__version__)"

# Check pinned version in project requirements
grep unstructured requirements.txt

# Smoke test — partition a local PDF against the hosted API
python - <<'EOF'
import os
from unstructured_client import UnstructuredClient
from unstructured_client.models import operations, shared

client = UnstructuredClient(api_key_auth=os.environ["UNSTRUCTURED_API_KEY"])
with open("sample.pdf", "rb") as f:
    file_bytes = f.read()

response = client.general.partition(
    request=operations.PartitionRequest(
        partition_parameters=shared.PartitionParameters(
            files=shared.Files(content=file_bytes, file_name="sample.pdf"),
            strategy="auto",
            languages=["eng"],
        )
    )
)
elements = [el.to_dict() for el in response.elements]
print(f"Element count: {len(elements)}")
print(f"First element type: {elements[0]['type']}")
print(f"First element text: {elements[0]['text'][:100]}")
EOF

# Check API quota and usage: https://app.unstructured.io/usage (no CLI)
```

## 4. MCP (Claude Code)

Unstructured.io has no MCP server. Use the Python SDK directly. For documentation
lookups, use Context7:

| Operation | Preferred Tool | Example |
|---|---|---|
| Look up SDK method signatures | `mcp__plugin_context7_context7__resolve-library-id` then `mcp__plugin_context7_context7__query-docs` | `{ "query": "unstructured-client PartitionParameters strategy" }` |
| Test partition call in isolation | Python REPL via Bash tool | `python -c "from unstructured_client import ..."` |

## 5. Direct API

The Unstructured.io hosted API is available at `https://api.unstructured.io/general/v0/general`.
The SDK wraps this endpoint — use curl only for debugging or verifying API key validity.

```bash
# Partition a file via direct HTTP (multipart/form-data)
curl -X POST "https://api.unstructured.io/general/v0/general" \
  -H "unstructured-api-key: $UNSTRUCTURED_API_KEY" \
  -F "files=@sample.pdf" \
  -F "strategy=auto" \
  -F "languages=eng"

# Response: JSON array of element objects
# [
#   {
#     "type": "Title",
#     "text": "INVOICE",
#     "metadata": { "page_number": 1, "filename": "sample.pdf" }
#   },
#   {
#     "type": "Table",
#     "text": "Item | Qty | Unit Price\nGAF Timberline HDZ | 10 | 89.50",
#     "metadata": { "page_number": 1 }
#   },
#   ...
# ]

# Check API key is valid (should return 422 with a schema error, not 401)
curl -X POST "https://api.unstructured.io/general/v0/general" \
  -H "unstructured-api-key: $UNSTRUCTURED_API_KEY"
# 401 = invalid key. 422 = valid key, missing required file field.
```

## 6. OmniDrop-Specific Patterns

### Client instantiation

```python
# backend/services/unstructured_service.py — singleton pattern
from unstructured_client import UnstructuredClient
from backend.core.config import settings

_client: UnstructuredClient | None = None

def _get_client() -> UnstructuredClient:
    """Returns a singleton UnstructuredClient. Never instantiate outside this function."""
    global _client
    if _client is None:
        _client = UnstructuredClient(api_key_auth=settings.unstructured_api_key)
    return _client
```

### Calling partition_document

```python
# The only call site is process_document in backend/workers/intake_tasks.py
from backend.services.unstructured_service import UnstructuredService

elements = UnstructuredService.partition_document(
    file_bytes=file_bytes,           # bytes — fetched from AccuLynx or Supabase Storage
    filename=file_name,              # str — used for file type inference by the API
    document_type_hint="unknown",    # str — drives strategy selection (see table below)
)
raw_text = UnstructuredService.elements_to_text(elements)
# raw_text is now a plain string ready for Claude
```

### Strategy selection

```python
# backend/services/unstructured_service.py — _select_strategy()
def _select_strategy(filename: str, type_hint: str) -> str:
    if type_hint in ("invoice", "msds"):
        return "hi_res"
    if type_hint in ("proposal", "manual", "warranty"):
        return "fast"
    return "auto"
```

| `document_type_hint` | Strategy | Why |
|---|---|---|
| `"invoice"` | `hi_res` | Scanned PDFs — OCR + layout analysis required |
| `"msds"` | `hi_res` | Complex safety table layouts, often scanned |
| `"proposal"` | `fast` | Digital text PDFs — no OCR needed |
| `"manual"` | `fast` | Clean text, large volume |
| `"warranty"` | `fast` | Clean text |
| `"unknown"` (default) | `auto` | Unstructured picks best strategy for the file |

`"ocr_only"` is supported by the API but not wired into `_select_strategy()`.
Do not add it without Lead approval — it skips layout analysis entirely, which
produces poor results on table-heavy roofing invoices.

### Output element types

Unstructured.io returns a **typed element list — not Markdown**. Do not treat the
output as a string until `elements_to_text()` has been called.

```python
# Each element dict looks like:
{
    "type": "Table",           # See type list below
    "text": "Item | Qty | ...",
    "metadata": {
        "page_number": 1,
        "filename": "invoice-001.pdf",
        # Additional keys vary by element type and strategy
    }
}

# Convert to plain text for Claude:
raw_text = UnstructuredService.elements_to_text(elements)
# Joins all non-empty element["text"] values with double newlines
```

Element types returned for roofing documents:

| Type | When It Appears |
|---|---|
| `Title` | Document headings, section titles |
| `NarrativeText` | Paragraphs, terms and conditions |
| `Table` | Line-item tables (critical for invoice extraction) |
| `ListItem` | Bullet or numbered list entries |
| `Header` | Page headers |
| `Footer` | Page footers, often contain payment terms |
| `Image` | Placeholder when `extract_image_block_types=["Image"]` — text is empty |
| `Address` | Street addresses detected by the layout model |

### extract_image_block_types

The production call passes `extract_image_block_types=["Image", "Table"]`. This
tells Unstructured to extract tables and images as discrete elements rather than
embedding them inline in narrative text. For roofing invoices this is important —
line-item tables are the primary source of leakage data and must be preserved as
separate `Table` elements, not merged into surrounding text.

### elements_to_text

```python
@staticmethod
def elements_to_text(elements: list[dict]) -> str:
    """Joins all non-empty element text with double newlines for Claude."""
    lines = [el.get("text", "").strip() for el in elements if el.get("text", "").strip()]
    return "\n\n".join(lines)
```

This is the only correct way to produce a Claude-ready string from partition output.
Never join with single newlines — double newlines preserve paragraph structure that
Claude uses to identify document sections.

### Known gotchas

- **`hi_res` is slow.** A single scanned invoice page can take 15–30 seconds. The
  `process_document` Celery task has a 60-second HTTP timeout on the AccuLynx fetch
  step — the Unstructured call has no explicit timeout. If `hi_res` jobs are timing
  out, increase the Celery task soft time limit in `celery_app.py`.
- **`response.elements` is a list of SDK model objects, not plain dicts.** Always
  call `.to_dict()` on each element before storing or passing downstream:
  `elements = [el.to_dict() for el in response.elements]`
- **The `filename` argument drives MIME type detection.** If `filename` is `None`
  or `"document"` (the fallback), the API may misidentify the file type. Always pass
  the actual filename from the AccuLynx payload when available.
- **Empty response is valid.** A document with no extractable text returns an empty
  `response.elements` list. `elements_to_text([])` returns `""`. The `score_context`
  task will score this near zero and route it to `bounce_back` — correct behaviour.
- **`languages=["eng"]` is hardcoded.** If OmniDrop expands to non-English markets,
  update the `partition_document` call — the API supports ISO 639-1 language codes.
- **SDK version is pinned to `^0.25`.** The `operations.PartitionRequest` /
  `shared.PartitionParameters` import paths changed between 0.22 and 0.25. Do not
  upgrade without testing.

## 7. Human SOPs

### SOP-UNSTRUCTURED-1: Retrieve and Set the Unstructured.io API Key

**When:** First-time environment setup, or when rotating the key after a security event.
**Time:** ~3 minutes
**Prerequisite:** You have an Unstructured.io account and the relevant `.env` file
is open in your editor.

Step 1. Go to https://app.unstructured.io/api-keys

Step 2. Log in if prompted.

Step 3. Click **"Create API Key"** (or copy an existing key by clicking the copy icon).

Step 4. Paste the key into your `.env` file as:
`UNSTRUCTURED_API_KEY=YOUR_KEY_HERE`

Step 5. Confirm `.env` is in `.gitignore`. Never commit this key.

Step 6. Run the smoke test to verify the key is valid:
```bash
python - <<'EOF'
import os
from unstructured_client import UnstructuredClient
from unstructured_client.models import operations, shared

client = UnstructuredClient(api_key_auth=os.environ["UNSTRUCTURED_API_KEY"])
try:
    client.general.partition(
        request=operations.PartitionRequest(
            partition_parameters=shared.PartitionParameters(
                files=shared.Files(content=b"%PDF-1.4", file_name="test.pdf"),
                strategy="fast",
                languages=["eng"],
            )
        )
    )
    print("OK — API key accepted")
except Exception as e:
    if "401" in str(e) or "unauthorized" in str(e).lower():
        print("FAIL — API key rejected (401)")
    else:
        print(f"OK — API key accepted (non-auth error expected for dummy file: {e})")
EOF
```

Step 7. Tell Claude: `"Unstructured SOP-1 complete. UNSTRUCTURED_API_KEY is set. Resume [current task name]."`

✅ Done when: the smoke test prints `OK`.

⚠️ If you see `SDKError: 401`: key was copied incorrectly or revoked — generate a
new one and repeat from Step 3.

---

### SOP-UNSTRUCTURED-2: Diagnose a Partition Failure on a Specific Document

**When:** A `process_document` Celery task fails with an Unstructured.io error for
a specific job.
**Time:** ~10 minutes
**Prerequisite:** `UNSTRUCTURED_API_KEY` is set; you have the raw document file or its URL.

Step 1. Retrieve the raw document bytes. If from AccuLynx:
```bash
curl -o /tmp/problem-doc.pdf \
  -H "Authorization: Bearer YOUR_LOCATION_API_KEY" \
  "https://acculynx.com/your/document/url"
```

Step 2. Run a direct partition call with all three strategies:
```bash
python - <<'EOF'
import os
from unstructured_client import UnstructuredClient
from unstructured_client.models import operations, shared

client = UnstructuredClient(api_key_auth=os.environ["UNSTRUCTURED_API_KEY"])
with open("/tmp/problem-doc.pdf", "rb") as f:
    file_bytes = f.read()

for strategy in ("auto", "fast", "hi_res"):
    try:
        response = client.general.partition(
            request=operations.PartitionRequest(
                partition_parameters=shared.PartitionParameters(
                    files=shared.Files(content=file_bytes, file_name="problem-doc.pdf"),
                    strategy=strategy,
                    languages=["eng"],
                    extract_image_block_types=["Image", "Table"],
                )
            )
        )
        elements = [el.to_dict() for el in response.elements]
        print(f"{strategy}: {len(elements)} elements, types: {set(e['type'] for e in elements)}")
    except Exception as e:
        print(f"{strategy}: FAILED — {e}")
EOF
```

Step 3. If `hi_res` succeeds but `fast` returns zero elements: document is scanned.
Update the `document_type_hint` for this class to `"invoice"` or `"msds"` to force
`hi_res` in production.

Step 4. If all strategies fail: document may be password-protected, corrupt, or
unsupported. Check supported formats at
https://docs.unstructured.io/api-reference/api-services/supported-file-types

Step 5. Tell Claude: `"Unstructured SOP-2 complete. Root cause: [description]. Resume [current task name]."`

✅ Done when: at least one strategy produces a non-empty element list, or root cause
is identified.

⚠️ If `hi_res` times out locally: try adding `split_pdf_page=True` to
`PartitionParameters` to process pages in parallel — safe for local diagnosis,
not currently enabled in production.
