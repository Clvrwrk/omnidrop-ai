"""
OmniDrop AI — Claude Service (Anthropic API)

Provides four capabilities:
  1. Triage: Classify document type (structured vs. unstructured)
  2. Extraction: Extract strict JSON schema from structured documents (Invoices/Proposals)
  3. Chunking: Prepare unstructured documents for RAG (MSDS/Manuals)
  4. Analytics: Text-to-SQL agent for C-Suite natural language queries

The input to all methods is plain text produced by UnstructuredService.elements_to_text().

SDK: anthropic  (pip install anthropic)
Model: claude-opus-4-6 — non-negotiable per CLAUDE.md
"""

import json
import logging
import re
from typing import Any, Literal

import anthropic
import voyageai

from backend.core.config import settings

logger = logging.getLogger(__name__)

DocumentType = Literal["structured", "unstructured", "unknown"]

_client: anthropic.Anthropic | None = None
_voyage_client: voyageai.Client | None = None


def _get_client() -> anthropic.Anthropic:
    """Returns a singleton Anthropic client."""
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _client


def _get_voyage_client() -> voyageai.Client:
    """Returns a singleton Voyage AI client for embeddings."""
    global _voyage_client
    if _voyage_client is None:
        _voyage_client = voyageai.Client(api_key=settings.voyage_api_key)
    return _voyage_client


# ── Confidence threshold: >= 0.95 on ALL fields → auto-confirm
# Below that → triage_status = 'pending' (HITL review)
CONFIDENCE_AUTO_CONFIRM_THRESHOLD = 0.95


class ClaudeService:
    """
    Wrapper around the Anthropic API for document triage and extraction.
    All methods are synchronous — called from Celery tasks.
    """

    MODEL = "claude-opus-4-6"

    @staticmethod
    def classify_document(raw_text: str) -> DocumentType:
        """
        Triage Agent: Determines whether a document is structured or unstructured.

        Structured   → Invoice, Sales Proposal, Purchase Order (→ extract_struct)
        Unstructured → Field Manual, MSDS, Warranty, Product Sheet (→ chunk_and_embed)

        Returns: "structured" | "unstructured" | "unknown"
        """
        logger.info("classify_document called")

        client = _get_client()
        message = client.messages.create(
            model=ClaudeService.MODEL,
            max_tokens=10,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Classify this document. Reply with ONLY one word:\n"
                        '- "structured" if it contains invoices, purchase orders, '
                        "or financial line items\n"
                        '- "unstructured" if it is a manual, MSDS, warranty, '
                        "or reference document\n"
                        '- "unknown" if there is insufficient content to classify\n\n'
                        f"Document text:\n{raw_text[:3000]}"
                    ),
                }
            ],
        )

        result = message.content[0].text.strip().lower()
        if result not in ("structured", "unstructured", "unknown"):
            logger.warning("classify_document got unexpected response: %s", result)
            return "unknown"
        return result  # type: ignore[return-value]

    @staticmethod
    def extract_invoice_schema(raw_text: str) -> dict[str, Any]:
        """
        Extracts invoice fields with per-field confidence scores.

        Returns a dict with value/confidence pairs per the API contract:
        {
            "vendor_name": {"value": str | None, "confidence": float},
            "invoice_number": {"value": str | None, "confidence": float},
            ...
            "line_items": [
                {"description": {"value": str, "confidence": float}, ...}
            ],
            "notes": {"value": str | None, "confidence": float}
        }

        Confidence >= 0.95 on ALL fields → auto-confirm.
        Below that → triage_status = 'pending' for HITL review.
        """
        logger.info("extract_invoice_schema called")

        client = _get_client()
        message = client.messages.create(
            model=ClaudeService.MODEL,
            max_tokens=2048,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Extract invoice data from this document. "
                        "Return ONLY valid JSON matching this schema exactly.\n"
                        "Include a \"confidence\" field (0.0–1.0) for each extracted value.\n"
                        "If a field cannot be found, set the value to null and confidence to 0.0.\n\n"
                        "Schema:\n"
                        "{\n"
                        '  "vendor_name": {"value": "string", "confidence": 0.0},\n'
                        '  "invoice_number": {"value": "string", "confidence": 0.0},\n'
                        '  "invoice_date": {"value": "ISO 8601 date string", "confidence": 0.0},\n'
                        '  "due_date": {"value": "ISO 8601 date string or null", "confidence": 0.0},\n'
                        '  "subtotal": {"value": 0.0, "confidence": 0.0},\n'
                        '  "tax": {"value": 0.0, "confidence": 0.0},\n'
                        '  "total": {"value": 0.0, "confidence": 0.0},\n'
                        '  "line_items": [\n'
                        '    {"description": {"value": "string", "confidence": 0.0}, '
                        '"quantity": {"value": 0.0, "confidence": 0.0}, '
                        '"unit_price": {"value": 0.0, "confidence": 0.0}, '
                        '"amount": {"value": 0.0, "confidence": 0.0}}\n'
                        "  ],\n"
                        '  "notes": {"value": "string or null", "confidence": 0.0}\n'
                        "}\n\n"
                        f"Document text:\n{raw_text[:8000]}"
                    ),
                }
            ],
        )

        raw = message.content[0].text.strip()
        # Strip markdown code fences if Claude wraps the response
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())

    @staticmethod
    def should_auto_confirm(extraction: dict[str, Any]) -> bool:
        """
        Returns True if ALL field confidence scores >= 0.95.
        Used to decide triage_status: 'confirmed' vs 'pending'.
        """
        header_fields = [
            "vendor_name", "invoice_number", "invoice_date",
            "due_date", "subtotal", "tax", "total", "notes",
        ]
        for field in header_fields:
            entry = extraction.get(field, {})
            if isinstance(entry, dict) and entry.get("confidence", 0.0) < CONFIDENCE_AUTO_CONFIRM_THRESHOLD:
                return False

        for item in extraction.get("line_items", []):
            for key in ("description", "quantity", "unit_price", "amount"):
                entry = item.get(key, {})
                if isinstance(entry, dict) and entry.get("confidence", 0.0) < CONFIDENCE_AUTO_CONFIRM_THRESHOLD:
                    return False

        return True

    # ── Text-to-SQL Analytics Agent ──────────────────────────────────────────

    # Schema description provided to Claude for SQL generation
    _ANALYTICS_SCHEMA = """
Tables available (PostgreSQL + Supabase):

jobs (job_id UUID PK, location_id UUID FK, status TEXT ['queued','processing','complete','failed'], file_name TEXT, error_message TEXT, created_at TIMESTAMPTZ, completed_at TIMESTAMPTZ)

documents (document_id UUID PK, job_id UUID FK, location_id UUID FK, document_type TEXT ['invoice','proposal','po','msds','manual','warranty','unknown'], raw_path TEXT, triage_status TEXT ['pending','confirmed','rejected'], created_at TIMESTAMPTZ)

invoices (invoice_id UUID PK, document_id UUID FK UNIQUE, location_id UUID FK, vendor_name TEXT, invoice_number TEXT, invoice_date DATE, due_date DATE, subtotal NUMERIC(12,2), tax NUMERIC(12,2), total NUMERIC(12,2), notes TEXT, extraction_meta JSONB, created_at TIMESTAMPTZ)

line_items (line_item_id UUID PK, invoice_id UUID FK, description TEXT, quantity NUMERIC(12,4), unit_price NUMERIC(12,2), amount NUMERIC(12,2), sort_order INTEGER)

locations (location_id UUID PK, user_id TEXT, name TEXT, acculynx_api_key TEXT, connection_status TEXT, created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ)
"""

    @staticmethod
    def analytics_agent(query: str, location_id: str) -> dict[str, Any]:
        """
        Text-to-SQL analytics agent. Accepts a natural language query,
        returns a parameterized SELECT statement scoped to the given location.

        Returns:
            {"sql": str, "params": list, "explanation": str}

        Raises:
            ValueError: If Claude returns a non-SELECT statement.
        """
        logger.info("analytics_agent called", extra={"location_id": location_id})

        client = _get_client()
        message = client.messages.create(
            model=ClaudeService.MODEL,
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "You are a SQL analyst for a roofing document management system.\n"
                        "Generate a PostgreSQL SELECT query to answer the user's question.\n\n"
                        "RULES:\n"
                        "- Return ONLY valid JSON: {\"sql\": \"SELECT ...\", \"params\": [...], \"explanation\": \"...\"}\n"
                        "- ONLY SELECT statements — never INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE, or any DDL/DML\n"
                        "- The query MUST include a WHERE clause filtering by location_id = $1\n"
                        "- Use $1, $2, $3... for parameter placeholders (PostgreSQL style)\n"
                        "- $1 is always the location_id parameter — do not use it for anything else\n"
                        "- Additional user-supplied filter values go in $2, $3, etc.\n"
                        "- Use table and column names exactly as shown in the schema\n"
                        "- Keep queries simple and efficient\n\n"
                        f"SCHEMA:\n{ClaudeService._ANALYTICS_SCHEMA}\n\n"
                        f"USER QUESTION: {query}"
                    ),
                }
            ],
        )

        raw = message.content[0].text.strip()
        # Strip markdown code fences if Claude wraps the response
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw.strip())

        sql = result.get("sql", "").strip()
        params = result.get("params", [])
        explanation = result.get("explanation", "")

        # Strict validation: must be a SELECT statement
        normalized = re.sub(r"\s+", " ", sql).strip().upper()
        if not normalized.startswith("SELECT"):
            raise ValueError(f"Analytics agent returned non-SELECT statement: {sql[:100]}")

        # Reject any dangerous keywords that shouldn't appear in a read-only query
        _FORBIDDEN = {"INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE", "GRANT", "REVOKE"}
        # Check tokens in the normalized SQL (split on whitespace and common delimiters)
        sql_tokens = set(re.findall(r"[A-Z_]+", normalized))
        violations = sql_tokens & _FORBIDDEN
        if violations:
            raise ValueError(f"Analytics agent SQL contains forbidden keywords: {violations}")

        # Ensure location_id is always the first parameter
        params = [location_id] + list(params)

        return {"sql": sql, "params": params, "explanation": explanation}

    # voyage-3 outputs 1024-dimensional vectors
    EMBEDDING_MODEL = "voyage-3"
    EMBEDDING_DIMENSION = 1024

    @staticmethod
    def chunk_for_rag(raw_text: str, document_id: str) -> list[dict[str, Any]]:
        """
        Splits unstructured document text into semantic chunks for RAG storage.
        Generates embeddings via Voyage AI (voyage-3, 1024-dim) for pgvector upsert.

        Returns:
            List of chunk dicts ready for document_embeddings table:
            [{"document_id": str, "chunk_text": str, "embedding": list[float],
              "metadata": {"topic": str, "chunk_index": int}}]
        """
        logger.info("chunk_for_rag called", extra={"document_id": document_id})

        claude_client = _get_client()
        voyage_client = _get_voyage_client()

        # Step 1: Ask Claude to semantically chunk the document
        message = claude_client.messages.create(
            model=ClaudeService.MODEL,
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Split this document into semantic chunks for a RAG knowledge base.\n"
                        "Each chunk should be self-contained and 150–300 words.\n"
                        'Return a JSON array of objects: [{"chunk_text": "...", "topic": "..."}]\n\n'
                        f"Document:\n{raw_text}"
                    ),
                }
            ],
        )

        raw = message.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        chunks = json.loads(raw.strip())

        # Step 2: Generate embeddings via Voyage AI (voyage-3 → 1024-dim vectors)
        chunk_texts = [c["chunk_text"] for c in chunks]
        embedding_result = voyage_client.embed(chunk_texts, model=ClaudeService.EMBEDDING_MODEL)

        results = []
        for i, chunk in enumerate(chunks):
            results.append(
                {
                    "document_id": document_id,
                    "chunk_text": chunk["chunk_text"],
                    "embedding": embedding_result.embeddings[i],
                    "metadata": {
                        "topic": chunk.get("topic", ""),
                        "chunk_index": i,
                    },
                }
            )

        logger.info(
            "chunk_for_rag complete",
            extra={"document_id": document_id, "chunk_count": len(results)},
        )
        return results
