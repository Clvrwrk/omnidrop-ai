---
name: omnidrop-ai-pipeline
description: Patterns for implementing OmniDrop AI's document processing pipeline. Use when writing Unstructured.io parsing, Claude triage/extraction/RAG services, pgvector embeddings, confidence scoring, or any pytest tests for the OmniDrop AI backend services.
---

# OmniDrop AI — AI Pipeline & Testing Skill

## Critical Output Format: Unstructured.io Is NOT Markdown

Unstructured.io does NOT return Markdown. It returns a typed element list:

```python
# WRONG assumption
text = unstructured_result  # NOT a markdown string

# CORRECT — Unstructured.io output structure
elements = [
    {"type": "Title", "text": "INVOICE", "metadata": {"page_number": 1}},
    {"type": "Table", "text": "Item | Qty | Price\n...", "metadata": {}},
    {"type": "NarrativeText", "text": "Terms: Net 30", "metadata": {}},
    {"type": "ListItem", "text": "Material: GAF Timberline HDZ", "metadata": {}},
]
# Types: Title, NarrativeText, ListItem, Table, Header, Footer, Image, Address
```

Extract plain text for Claude by joining element text:
```python
plain_text = "\n".join(el["text"] for el in elements if el.get("text"))
```

---

## UnstructuredService (`backend/services/unstructured_service.py`)

```python
from unstructured_client import UnstructuredClient
from unstructured_client.models import shared, operations
from backend.core.config import settings

class UnstructuredService:
    def __init__(self):
        self.client = UnstructuredClient(api_key_auth=settings.UNSTRUCTURED_API_KEY)

    def partition_document(
        self,
        file_bytes: bytes,
        filename: str,
        document_type_hint: str = "unknown",
    ) -> list[dict]:
        """Parse document bytes into typed elements. Returns element list — NOT Markdown."""
        strategy = self._select_strategy(filename, document_type_hint)

        response = self.client.general.partition(
            request=operations.PartitionRequest(
                partition_parameters=shared.PartitionParameters(
                    files=shared.Files(content=file_bytes, file_name=filename),
                    strategy=strategy,
                    languages=["eng"],
                    extract_image_block_types=["Image", "Table"],
                )
            )
        )
        return [el.to_dict() for el in response.elements]

    def _select_strategy(self, filename: str, type_hint: str) -> str:
        """Select Unstructured.io parsing strategy based on document type."""
        # hi_res: scanned/image PDFs requiring OCR — invoices, MSDS sheets
        # fast:   digital text PDFs — proposals, manuals
        # auto:   unknown — Unstructured picks best strategy
        if type_hint in ("invoice", "msds"):
            return "hi_res"
        if type_hint in ("proposal", "manual", "warranty"):
            return "fast"
        return "auto"
```

### Strategy Reference
| Document Type | Strategy | Reason |
|---|---|---|
| Roofing invoice (scanned PDF) | `hi_res` | OCR + layout analysis required |
| MSDS sheet | `hi_res` | Complex layout, safety tables |
| Sales proposal (digital PDF) | `fast` | Clean text, no OCR needed |
| Field manual (digital) | `fast` | Usually clean text |
| Unknown | `auto` | Unstructured picks best |

---

## ClaudeService (`backend/services/claude_service.py`)

```python
import anthropic
import json
from backend.core.config import settings

class ClaudeService:
    MODEL = "claude-opus-4-6"

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
```

### Triage Agent — classify_document()
```python
    def classify_document(self, text_content: str) -> str:
        """Classify document as structured, unstructured, or unknown."""
        message = self.client.messages.create(
            model=self.MODEL,
            max_tokens=10,
            messages=[{
                "role": "user",
                "content": f"""Classify this document. Reply with ONLY one word:
- "structured" if it contains invoices, purchase orders, or financial line items
- "unstructured" if it is a manual, MSDS, warranty, or reference document
- "unknown" if there is insufficient content to classify

Document text:
{text_content[:3000]}"""
            }]
        )
        result = message.content[0].text.strip().lower()
        if result not in ("structured", "unstructured", "unknown"):
            return "unknown"
        return result
```

### Structured Extraction — extract_invoice_schema()
```python
    def extract_invoice_schema(self, text_content: str) -> dict:
        """Extract invoice fields from document text. Includes per-field confidence scores."""
        message = self.client.messages.create(
            model=self.MODEL,
            max_tokens=2048,
            messages=[{
                "role": "user",
                "content": f"""Extract invoice data from this document. Return ONLY valid JSON matching this schema exactly.
Include a "confidence" field (0.0–1.0) for each extracted value.
If a field cannot be found, set the value to null and confidence to 0.0.

Schema:
{{
  "vendor_name": {{"value": "string", "confidence": 0.0}},
  "invoice_number": {{"value": "string", "confidence": 0.0}},
  "invoice_date": {{"value": "ISO 8601 date string", "confidence": 0.0}},
  "due_date": {{"value": "ISO 8601 date string or null", "confidence": 0.0}},
  "subtotal": {{"value": 0.0, "confidence": 0.0}},
  "tax": {{"value": 0.0, "confidence": 0.0}},
  "total": {{"value": 0.0, "confidence": 0.0}},
  "line_items": [
    {{"description": "string", "quantity": 0.0, "unit_price": 0.0, "amount": 0.0, "confidence": 0.0}}
  ],
  "notes": {{"value": "string or null", "confidence": 0.0}}
}}

Document text:
{text_content[:8000]}"""
            }]
        )
        raw = message.content[0].text.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())
```

### RAG Chunking — chunk_for_rag()
```python
    def chunk_for_rag(self, text_content: str, document_id: str) -> list[dict]:
        """Chunk text into semantic segments with embeddings for pgvector storage."""
        message = self.client.messages.create(
            model=self.MODEL,
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": f"""Split this document into semantic chunks for a RAG knowledge base.
Each chunk should be self-contained and 150–300 words.
Return a JSON array of objects: [{{"chunk_text": "...", "topic": "..."}}]

Document:
{text_content}"""
            }]
        )
        raw = message.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        chunks = json.loads(raw.strip())

        # Generate embeddings for each chunk
        results = []
        for chunk in chunks:
            embedding_response = self.client.embeddings.create(
                model="voyage-3",  # Anthropic's embedding model
                input=[chunk["chunk_text"]],
            )
            results.append({
                "document_id": document_id,
                "chunk_text": chunk["chunk_text"],
                "embedding": embedding_response.embeddings[0],
                "metadata": {"topic": chunk.get("topic", "")},
            })
        return results
```

---

## pgvector Upsert Pattern

```python
# In chunk_and_embed Celery task
async def save_embeddings(chunks: list[dict]):
    supabase = get_supabase_client()
    await supabase.table("document_embeddings").insert(chunks).execute()

# Semantic search query
async def search_documents(query_embedding: list[float], limit: int = 10):
    supabase = get_supabase_client()
    result = await supabase.rpc(
        "match_documents",
        {
            "query_embedding": query_embedding,
            "match_threshold": 0.7,
            "match_count": limit,
        }
    ).execute()
    return result.data
```

```sql
-- Supabase RPC function for vector similarity search
CREATE OR REPLACE FUNCTION match_documents(
    query_embedding vector(1536),
    match_threshold float,
    match_count int
)
RETURNS TABLE (
    id uuid,
    document_id uuid,
    chunk_text text,
    metadata jsonb,
    similarity float
)
LANGUAGE sql STABLE
AS $$
    SELECT id, document_id, chunk_text, metadata,
           1 - (embedding <=> query_embedding) AS similarity
    FROM document_embeddings
    WHERE 1 - (embedding <=> query_embedding) > match_threshold
    ORDER BY embedding <=> query_embedding
    LIMIT match_count;
$$;
```

---

## Confidence Scoring Rules

- `≥ 0.9` — High confidence. Display with green badge. Auto-approve.
- `0.7–0.89` — Medium confidence. Display with yellow badge. Queue for HITL review.
- `< 0.7` — Low confidence. Display with red badge. Require human confirmation.
- `0.0` — Field not found. Display as empty with red badge.

The HITL `/triage` page surfaces all fields with confidence `< 0.8` for accountant review.

---

## Test Patterns (`tests/`)

### Pytest fixtures (`tests/conftest.py`)
```python
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from backend.api.main import app

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def valid_hookdeck_signature(monkeypatch):
    """Fixture that patches HMAC verification to always pass."""
    with patch("backend.core.security.verify_hookdeck_signature"):
        yield

@pytest.fixture
def sample_acculynx_payload():
    return {
        "event_type": "document.created",
        "job_id": "job-123",
        "location_id": "loc-456",
        "document_id": "doc-789",
        "document_url": "https://acculynx.com/docs/789",
        "timestamp": "2026-03-28T12:00:00Z",
    }
```

### Webhook integration tests (`tests/test_webhook.py`)
```python
import hmac, hashlib
from tests.conftest import *

def make_hookdeck_signature(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

def test_webhook_returns_200_with_valid_signature(client, sample_acculynx_payload):
    body = json.dumps(sample_acculynx_payload).encode()
    sig = make_hookdeck_signature(body, "test-secret")

    with patch("backend.workers.intake_tasks.process_document.delay") as mock_delay:
        response = client.post(
            "/api/v1/webhooks/acculynx",
            content=body,
            headers={"x-hookdeck-signature": sig, "content-type": "application/json"},
        )
    assert response.status_code == 200
    mock_delay.assert_called_once()

def test_webhook_returns_401_with_invalid_signature(client, sample_acculynx_payload):
    response = client.post(
        "/api/v1/webhooks/acculynx",
        json=sample_acculynx_payload,
        headers={"x-hookdeck-signature": "sha256=invalidsig"},
    )
    assert response.status_code == 401

def test_webhook_returns_422_with_invalid_payload(client, valid_hookdeck_signature):
    response = client.post("/api/v1/webhooks/acculynx", json={"bad": "data"})
    assert response.status_code == 422

def test_webhook_does_not_call_supabase_or_ai(client, sample_acculynx_payload):
    """Ensure the webhook endpoint has zero DB or AI calls."""
    body = json.dumps(sample_acculynx_payload).encode()
    sig = make_hookdeck_signature(body, "test-secret")

    with patch("backend.workers.intake_tasks.process_document.delay"):
        with patch("backend.services.supabase_client.get_supabase_client") as mock_sb:
            client.post("/api/v1/webhooks/acculynx", content=body,
                       headers={"x-hookdeck-signature": sig})
    mock_sb.assert_not_called()  # Webhook must not touch DB
```

### Service unit tests (`tests/test_services.py`)
```python
def test_classify_document_structured(mock_claude_response):
    mock_claude_response.return_value = "structured"
    service = ClaudeService()
    result = service.classify_document("INVOICE #1234\nVendor: ABC\nTotal: $500")
    assert result == "structured"

def test_classify_document_unknown_on_bad_response(mock_claude_response):
    mock_claude_response.return_value = "something-unexpected"
    service = ClaudeService()
    result = service.classify_document("gibberish content")
    assert result == "unknown"  # Must default to unknown, never crash

def test_extract_invoice_includes_confidence_scores(mock_claude_response):
    mock_claude_response.return_value = json.dumps({
        "vendor_name": {"value": "ABC Roofing", "confidence": 0.95},
        "total": {"value": 1500.00, "confidence": 0.98},
        ...
    })
    service = ClaudeService()
    result = service.extract_invoice_schema("sample invoice text")
    assert "confidence" in result["vendor_name"]
    assert result["vendor_name"]["confidence"] >= 0.0
```

---

## Anti-Patterns

- Never treat Unstructured.io output as Markdown — it is a typed element list
- Never import from `backend/services/temporal_client.py` — it is superseded
- Never skip confidence scores in `extract_invoice_schema` — HITL requires them
- Never use a Claude model other than `claude-opus-4-6` for AI reasoning
- Never write to `document_embeddings` without the embedding vector — pgvector requires it
- Never mock Supabase in integration tests that test database behavior — use test fixtures
