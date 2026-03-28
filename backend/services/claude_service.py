"""
OmniDrop AI — Claude Service (Anthropic API)

Provides two capabilities:
  1. Triage: Classify document type (structured vs. unstructured)
  2. Extraction: Extract strict JSON schema from structured documents (Invoices/Proposals)
  3. Chunking: Prepare unstructured documents for RAG (MSDS/Manuals)

The input to all methods is plain text produced by UnstructuredService.elements_to_text().

SDK: anthropic  (pip install anthropic)
Default model: claude-opus-4-6
"""

import json
import logging
import os
from typing import Any, Literal

logger = logging.getLogger(__name__)

DocumentType = Literal["structured", "unstructured", "unknown"]


def _get_client() -> Any:
    """Returns an initialized Anthropic client."""
    import anthropic

    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


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

        Structured  → Invoice, Sales Proposal, Purchase Order (→ extract_structured)
        Unstructured → Field Manual, MSDS, Warranty, Product Sheet (→ chunk_and_embed)

        Returns: "structured" | "unstructured" | "unknown"

        TODO: Implement prompt and parse response.
        """
        logger.info("classify_document called")
        raise NotImplementedError("classify_document not yet implemented")

    @staticmethod
    def extract_invoice_schema(raw_text: str) -> dict[str, Any]:
        """
        Extracts a strict JSON schema from a structured document (Invoice/Proposal).

        Returns a dict matching the InvoiceSchema Pydantic model (to be defined in
        shared/models/documents.py):
        {
            "vendor_name": str,
            "invoice_number": str,
            "invoice_date": str,  # ISO 8601
            "due_date": str | None,
            "subtotal": float,
            "tax": float,
            "total": float,
            "line_items": [{"description": str, "quantity": float, "unit_price": float, "amount": float}],
            "notes": str | None,
        }

        TODO: Implement prompt with strict JSON mode / tool use.
        """
        logger.info("extract_invoice_schema called")
        raise NotImplementedError("extract_invoice_schema not yet implemented")

    @staticmethod
    def chunk_for_rag(raw_text: str, job_id: str) -> list[dict[str, Any]]:
        """
        Prepares unstructured document text for RAG storage in Supabase pgvector.

        Splits text into semantically coherent chunks and generates embeddings.

        Returns:
            List of chunk dicts:
            [{"chunk_text": str, "chunk_index": int, "embedding": list[float]}]

        TODO:
            1. Implement semantic chunking (by section/topic, not fixed character count)
            2. Generate embeddings via Anthropic or a dedicated embeddings model
            3. Return chunks ready for Supabase pgvector upsert
        """
        logger.info("chunk_for_rag called", extra={"job_id": job_id})
        raise NotImplementedError("chunk_for_rag not yet implemented")
