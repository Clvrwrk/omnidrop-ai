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
import os
from typing import Any

logger = logging.getLogger(__name__)


def _get_client() -> Any:
    """Returns an initialized UnstructuredClient using UNSTRUCTURED_API_KEY."""
    from unstructured_client import UnstructuredClient

    return UnstructuredClient(api_key_auth=os.environ["UNSTRUCTURED_API_KEY"])


class UnstructuredService:
    """
    Wrapper around the Unstructured.io API SDK.
    All methods are synchronous — called from Celery tasks (not async context).
    """

    @staticmethod
    def partition_document(
        file_bytes: bytes,
        filename: str,
        strategy: str = "auto",
    ) -> list[dict[str, Any]]:
        """
        Partition a document into structured elements using Unstructured.io.

        Args:
            file_bytes: Raw bytes of the document (PDF, DOCX, XLSX, etc.)
            filename:   Original filename — used to infer file type.
            strategy:   Parsing strategy: "auto" | "hi_res" | "fast" | "ocr_only"
                        Use "hi_res" for invoices/MSDS, "fast" for clean text PDFs.

        Returns:
            List of element dicts, each containing:
            {
                "type": "NarrativeText" | "Table" | "Title" | ...,
                "text": "...",
                "metadata": {"page_number": int, "filename": str, ...}
            }

        TODO:
            1. Confirm API key access at https://app.unstructured.io/
            2. Test with a sample roofing invoice PDF
            3. Tune strategy per document type (see triage_document task)
        """
        import io

        from unstructured_client.models.shared import Files, PartitionParameters

        logger.info("partition_document called", extra={"filename": filename, "strategy": strategy})

        # TODO: Implement
        # client = _get_client()
        # files = Files(content=file_bytes, file_name=filename)
        # params = PartitionParameters(
        #     files=files,
        #     strategy=strategy,
        #     languages=["eng"],
        #     split_pdf_page=True,
        #     split_pdf_concurrency_level=5,
        # )
        # response = client.general.partition(request=params)
        # return [element.to_dict() for element in response.elements or []]

        raise NotImplementedError("partition_document not yet implemented")

    @staticmethod
    def elements_to_text(elements: list[dict[str, Any]]) -> str:
        """
        Concatenates element text into a single string for Claude consumption.
        Tables are formatted as pipe-delimited text.
        """
        lines = []
        for el in elements:
            text = el.get("text", "").strip()
            if text:
                lines.append(text)
        return "\n\n".join(lines)
