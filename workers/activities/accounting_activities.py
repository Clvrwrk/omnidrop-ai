"""
OmniDrop AI — Accounting Activities (Merge.dev)

Pushes approved invoice data to QuickBooks, Sage, Xero, or any other
accounting platform the user has connected via Merge Link.

Pipeline position: Activity 5 (final) of IntakeWorkflow
  ... → sync_to_database → [push_to_accounting]

SDK: MergePythonClient  (pip install MergePythonClient)
Docs: https://github.com/merge-api/merge-python-client
Merge accounting API: https://docs.merge.dev/accounting/overview/

IMPORTANT: account_token is per-user and must be retrieved from Supabase at
runtime — it must NEVER be stored in environment variables or committed to code.
"""

import logging
import os
from typing import Any

from temporalio import activity

logger = logging.getLogger(__name__)


def _get_merge_client(account_token: str) -> Any:
    """
    Returns a Merge client initialized with the org API key and
    the per-user account token for their connected accounting platform.

    Args:
        account_token: Retrieved from Supabase for the specific user/job.
    """
    from merge import Merge

    return Merge(
        api_key=os.environ["MERGE_API_KEY"],
        account_token=account_token,
    )


@activity.defn
async def push_to_accounting(
    invoice_data: dict[str, Any],
    account_token: str,
) -> dict[str, str]:
    """
    Creates an invoice record in the user's connected accounting platform
    via the Merge.dev unified API.

    Args:
        invoice_data: Structured invoice extracted by ocr_extract_invoice + ai_enrich.
        account_token: Per-user Merge account token retrieved from Supabase.

    Returns:
        {"merge_invoice_id": str, "remote_id": str, "status": "created"}

    TODO:
        1. Map OmniDrop invoice fields to Merge InvoiceRequest schema
        2. Handle idempotency (check if invoice already pushed before creating)
        3. Store merge_invoice_id back in Supabase for reconciliation
        4. Handle Merge API errors (rate limits, validation failures)
    """
    logger.info(
        "push_to_accounting called",
        extra={"invoice_id": invoice_data.get("invoice_id")},
    )

    # TODO: Implement
    # from merge.resources.accounting.types import InvoiceRequest, InvoiceLineItemRequest
    #
    # client = _get_merge_client(account_token)
    #
    # invoice_request = InvoiceRequest(
    #     type="ACCOUNTS_PAYABLE",
    #     contact=invoice_data.get("vendor_id"),   # Merge contact ID
    #     due_date=invoice_data.get("due_date"),
    #     total_amount=invoice_data.get("invoice_total"),
    #     line_items=[
    #         InvoiceLineItemRequest(
    #             description=item["description"],
    #             total_amount=item["amount"],
    #         )
    #         for item in invoice_data.get("line_items", [])
    #     ],
    # )
    #
    # response = client.accounting.invoices.create(
    #     model=invoice_request,
    #     remote_user_id=invoice_data["user_id"],
    # )
    # return {"merge_invoice_id": response.model.id, "status": "created"}

    raise NotImplementedError("push_to_accounting not yet implemented")
