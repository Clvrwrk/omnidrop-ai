"""
OmniDrop AI — OCR Activities (Azure Document Intelligence)

Runs BEFORE the Claude enrichment activity to pre-extract structured
invoice data. This reduces Claude token consumption and improves accuracy.

Pipeline position: Activity 2 of IntakeWorkflow
  fetch_documents → [ocr_extract] → ai_enrich → sync_to_database → push_to_accounting

SDK: azure-ai-documentintelligence (v4.0 API)
Docs: https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/
"""

import logging
import os
from typing import Any

from temporalio import activity

logger = logging.getLogger(__name__)


def _get_document_intelligence_client() -> Any:
    """
    Returns an initialized Azure Document Intelligence client.
    Credentials read from environment variables.
    """
    from azure.ai.documentintelligence import DocumentIntelligenceClient
    from azure.core.credentials import AzureKeyCredential

    endpoint = os.environ["AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT"]
    key = os.environ["AZURE_DOCUMENT_INTELLIGENCE_KEY"]
    return DocumentIntelligenceClient(
        endpoint=endpoint,
        credential=AzureKeyCredential(key),
    )


@activity.defn
async def ocr_extract_invoice(document_url: str) -> dict[str, Any]:
    """
    Sends a document to Azure Document Intelligence's prebuilt-invoice model
    and returns structured JSON with extracted fields.

    Args:
        document_url: Publicly accessible URL of the document to analyze.
                      TODO: For private documents, use base64 content instead of URL.

    Returns:
        Dict containing extracted invoice fields:
        {
            "vendor_name": str | None,
            "vendor_address": str | None,
            "invoice_id": str | None,
            "invoice_date": str | None,
            "due_date": str | None,
            "invoice_total": float | None,
            "subtotal": float | None,
            "tax": float | None,
            "line_items": [{"description": str, "quantity": float, "amount": float}],
            "confidence_scores": {field: float},
        }

    TODO:
        1. Handle private document storage (read from Supabase Storage, pass as bytes)
        2. Add confidence threshold filtering
        3. Handle multi-page documents
    """
    logger.info("ocr_extract_invoice called", extra={"document_url": document_url})

    # TODO: Implement
    # from azure.ai.documentintelligence.models import AnalyzeDocumentContent
    #
    # client = _get_document_intelligence_client()
    # content = AnalyzeDocumentContent(url_source=document_url)
    # poller = client.begin_analyze_document("prebuilt-invoice", content)
    # result = poller.result()
    #
    # extracted = {}
    # for document in result.documents:
    #     fields = document.fields
    #     extracted["vendor_name"] = fields.get("VendorName", {}).get("valueString")
    #     extracted["invoice_total"] = fields.get("InvoiceTotal", {}).get("valueCurrency", {}).get("amount")
    #     # ... map remaining fields
    # return extracted

    raise NotImplementedError("ocr_extract_invoice not yet implemented")
