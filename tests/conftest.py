"""
OmniDrop AI — Shared test fixtures.
"""

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def sample_acculynx_payload() -> dict[str, Any]:
    return {
        "event_type": "document.created",
        "job_id": "job-123",
        "location_id": "loc-456",
        "document_id": "doc-789",
        "document_url": "https://acculynx.com/docs/789",
        "timestamp": "2026-03-28T12:00:00Z",
    }


@pytest.fixture
def sample_unstructured_elements() -> list[dict[str, Any]]:
    """Typical Unstructured.io output for a roofing invoice."""
    return [
        {"type": "Title", "text": "INVOICE", "metadata": {"page_number": 1, "filename": "invoice.pdf"}},
        {"type": "NarrativeText", "text": "ABC Roofing Supply Co.", "metadata": {"page_number": 1}},
        {"type": "NarrativeText", "text": "Invoice #INV-2026-0042", "metadata": {"page_number": 1}},
        {"type": "NarrativeText", "text": "Date: 2026-03-15", "metadata": {"page_number": 1}},
        {"type": "NarrativeText", "text": "Due Date: 2026-04-14", "metadata": {"page_number": 1}},
        {
            "type": "Table",
            "text": "GAF Timberline HDZ Shingles | 50 | 35.00 | 1750.00\nRidge Cap | 10 | 12.50 | 125.00",
            "metadata": {"page_number": 1},
        },
        {"type": "NarrativeText", "text": "Subtotal: $1875.00", "metadata": {"page_number": 1}},
        {"type": "NarrativeText", "text": "Tax: $150.00", "metadata": {"page_number": 1}},
        {"type": "NarrativeText", "text": "Total: $2025.00", "metadata": {"page_number": 1}},
        {"type": "NarrativeText", "text": "Terms: Net 30", "metadata": {"page_number": 1}},
    ]


@pytest.fixture
def sample_invoice_text(sample_unstructured_elements: list[dict]) -> str:
    """Plain text derived from Unstructured elements — input to ClaudeService."""
    from backend.services.unstructured_service import UnstructuredService

    return UnstructuredService.elements_to_text(sample_unstructured_elements)


@pytest.fixture
def sample_extraction_high_confidence() -> dict[str, Any]:
    """Claude extraction output where all fields are high confidence (>= 0.95)."""
    return {
        "vendor_name": {"value": "ABC Roofing Supply Co.", "confidence": 0.98},
        "invoice_number": {"value": "INV-2026-0042", "confidence": 0.99},
        "invoice_date": {"value": "2026-03-15", "confidence": 0.97},
        "due_date": {"value": "2026-04-14", "confidence": 0.96},
        "subtotal": {"value": 1875.00, "confidence": 0.99},
        "tax": {"value": 150.00, "confidence": 0.98},
        "total": {"value": 2025.00, "confidence": 0.99},
        "line_items": [
            {
                "description": {"value": "GAF Timberline HDZ Shingles", "confidence": 0.97},
                "quantity": {"value": 50.0, "confidence": 0.99},
                "unit_price": {"value": 35.00, "confidence": 0.98},
                "amount": {"value": 1750.00, "confidence": 0.99},
            },
            {
                "description": {"value": "Ridge Cap", "confidence": 0.96},
                "quantity": {"value": 10.0, "confidence": 0.99},
                "unit_price": {"value": 12.50, "confidence": 0.98},
                "amount": {"value": 125.00, "confidence": 0.99},
            },
        ],
        "notes": {"value": "Terms: Net 30", "confidence": 0.95},
    }


@pytest.fixture
def sample_extraction_low_confidence() -> dict[str, Any]:
    """Claude extraction output with some low-confidence fields → needs HITL."""
    return {
        "vendor_name": {"value": "ABC Roofing Supply Co.", "confidence": 0.98},
        "invoice_number": {"value": "INV-2026-0042", "confidence": 0.99},
        "invoice_date": {"value": "2026-03-15", "confidence": 0.70},
        "due_date": {"value": None, "confidence": 0.0},
        "subtotal": {"value": 1875.00, "confidence": 0.85},
        "tax": {"value": 150.00, "confidence": 0.60},
        "total": {"value": 2025.00, "confidence": 0.99},
        "line_items": [
            {
                "description": {"value": "GAF Timberline HDZ Shingles", "confidence": 0.97},
                "quantity": {"value": 50.0, "confidence": 0.99},
                "unit_price": {"value": 35.00, "confidence": 0.80},
                "amount": {"value": 1750.00, "confidence": 0.99},
            },
        ],
        "notes": {"value": None, "confidence": 0.0},
    }


@pytest.fixture
def mock_anthropic_client():
    """Patches the Anthropic client singleton for all Claude service tests."""
    with patch("backend.services.claude_service._get_client") as mock_get:
        mock_client = MagicMock()
        mock_get.return_value = mock_client
        yield mock_client


@pytest.fixture
def mock_voyage_client():
    """Patches the Voyage AI client singleton for embedding tests."""
    with patch("backend.services.claude_service._get_voyage_client") as mock_get:
        mock_client = MagicMock()
        mock_get.return_value = mock_client
        yield mock_client


@pytest.fixture
def mock_unstructured_client():
    """Patches the Unstructured client singleton for partition tests."""
    with patch("backend.services.unstructured_service._get_client") as mock_get:
        mock_client = MagicMock()
        mock_get.return_value = mock_client
        yield mock_client
