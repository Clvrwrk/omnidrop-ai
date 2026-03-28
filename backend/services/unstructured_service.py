"""
OmniDrop AI — Unstructured.io Service

The Omni-Parser layer. Transforms messy PDFs, MSDS sheets, Field Manuals,
and Invoices into clean structured elements before passing to Claude.

SDK: unstructured-client  (pip install unstructured-client)
Docs: https://docs.unstructured.io/api-reference/api-services/sdk-python

Supported strategies:
  - "hi_res"   → Best quality, uses vision model (use for invoices/MSDS)
  - "fast"     → Speed-optimized for clean digital PDFs
  - "ocr_only" → Pure OCR, no layout analysis
  - "auto"     → Unstructured picks the best strategy (recommended for mixed docs)

Output element types relevant to roofing docs:
  - Title, NarrativeText, Table, ListItem, Header, Footer
  - Each element: {"type": str, "text": str, "metadata": {...}}
"""

import logging
from typing import Any

from unstructured_client import UnstructuredClient
from unstructured_client.models import operations, shared

from backend.core.config import settings

logger = logging.getLogger(__name__)

_client: UnstructuredClient | None = None


def _get_client() -> UnstructuredClient:
    """Returns a singleton UnstructuredClient using UNSTRUCTURED_API_KEY."""
    global _client
    if _client is None:
        _client = UnstructuredClient(api_key_auth=settings.unstructured_api_key)
    return _client


class UnstructuredService:
    """
    Wrapper around the Unstructured.io API SDK.
    All methods are synchronous — called from Celery tasks (not async context).
    """

    @staticmethod
    def partition_document(
        file_bytes: bytes,
        filename: str,
        document_type_hint: str = "unknown",
    ) -> list[dict[str, Any]]:
        """
        Partition a document into structured elements using Unstructured.io.

        Args:
            file_bytes:         Raw bytes of the document (PDF, DOCX, XLSX, etc.)
            filename:           Original filename — used to infer file type.
            document_type_hint: Hint for strategy selection:
                                "invoice", "msds" → hi_res
                                "proposal", "manual", "warranty" → fast
                                "unknown" → auto

        Returns:
            List of element dicts, each containing:
            {
                "type": "NarrativeText" | "Table" | "Title" | ...,
                "text": "...",
                "metadata": {"page_number": int, "filename": str, ...}
            }
        """
        strategy = UnstructuredService._select_strategy(filename, document_type_hint)
        logger.info(
            "partition_document called",
            extra={"filename": filename, "strategy": strategy, "size_bytes": len(file_bytes)},
        )

        client = _get_client()
        response = client.general.partition(
            request=operations.PartitionRequest(
                partition_parameters=shared.PartitionParameters(
                    files=shared.Files(content=file_bytes, file_name=filename),
                    strategy=strategy,
                    languages=["eng"],
                    extract_image_block_types=["Image", "Table"],
                )
            )
        )

        elements = [el.to_dict() for el in response.elements]
        logger.info(
            "partition_document complete",
            extra={"filename": filename, "element_count": len(elements)},
        )
        return elements

    @staticmethod
    def _select_strategy(filename: str, type_hint: str) -> str:
        """
        Select Unstructured.io parsing strategy based on document type hint.

        hi_res: scanned/image PDFs requiring OCR — invoices, MSDS sheets
        fast:   digital text PDFs — proposals, manuals, warranties
        auto:   unknown — Unstructured picks best strategy
        """
        if type_hint in ("invoice", "msds"):
            return "hi_res"
        if type_hint in ("proposal", "manual", "warranty"):
            return "fast"
        return "auto"

    @staticmethod
    def elements_to_text(elements: list[dict[str, Any]]) -> str:
        """
        Concatenates element text into a single string for Claude consumption.
        Filters out empty elements.
        """
        lines = []
        for el in elements:
            text = el.get("text", "").strip()
            if text:
                lines.append(text)
        return "\n\n".join(lines)
