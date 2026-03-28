"""
OmniDrop AI — Unit tests for backend services.

Tests:
  - UnstructuredService: partition_document, elements_to_text, strategy selection
  - ClaudeService: classify_document, extract_invoice_schema, chunk_for_rag
  - Confidence scoring: should_auto_confirm threshold logic
"""

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from backend.services.claude_service import ClaudeService, CONFIDENCE_AUTO_CONFIRM_THRESHOLD
from backend.services.unstructured_service import UnstructuredService


# ─── UnstructuredService ──────────────────────────────────────────────────────


class TestUnstructuredServiceStrategy:
    """Strategy selection logic — no API calls needed."""

    def test_invoice_uses_hi_res(self):
        assert UnstructuredService._select_strategy("invoice.pdf", "invoice") == "hi_res"

    def test_msds_uses_hi_res(self):
        assert UnstructuredService._select_strategy("msds.pdf", "msds") == "hi_res"

    def test_proposal_uses_fast(self):
        assert UnstructuredService._select_strategy("proposal.pdf", "proposal") == "fast"

    def test_manual_uses_fast(self):
        assert UnstructuredService._select_strategy("manual.pdf", "manual") == "fast"

    def test_warranty_uses_fast(self):
        assert UnstructuredService._select_strategy("warranty.pdf", "warranty") == "fast"

    def test_unknown_uses_auto(self):
        assert UnstructuredService._select_strategy("mystery.pdf", "unknown") == "auto"

    def test_no_hint_defaults_auto(self):
        assert UnstructuredService._select_strategy("file.pdf", "") == "auto"


class TestElementsToText:
    """Plain text extraction from Unstructured elements."""

    def test_joins_element_text(self, sample_unstructured_elements: list[dict]):
        text = UnstructuredService.elements_to_text(sample_unstructured_elements)
        assert "INVOICE" in text
        assert "ABC Roofing Supply Co." in text
        assert "Total: $2025.00" in text

    def test_skips_empty_elements(self):
        elements = [
            {"type": "Title", "text": "Hello"},
            {"type": "NarrativeText", "text": ""},
            {"type": "NarrativeText", "text": "   "},
            {"type": "NarrativeText", "text": "World"},
        ]
        text = UnstructuredService.elements_to_text(elements)
        assert text == "Hello\n\nWorld"

    def test_empty_list_returns_empty(self):
        assert UnstructuredService.elements_to_text([]) == ""


class TestPartitionDocument:
    """partition_document calls the Unstructured SDK correctly."""

    def test_calls_api_with_correct_params(self, mock_unstructured_client: MagicMock):
        mock_el = MagicMock()
        mock_el.to_dict.return_value = {"type": "Title", "text": "INVOICE", "metadata": {}}
        mock_unstructured_client.general.partition.return_value = MagicMock(elements=[mock_el])

        result = UnstructuredService.partition_document(
            file_bytes=b"%PDF-fake",
            filename="invoice.pdf",
            document_type_hint="invoice",
        )

        mock_unstructured_client.general.partition.assert_called_once()
        call_args = mock_unstructured_client.general.partition.call_args
        req = call_args.kwargs.get("request") or call_args[1].get("request") or call_args[0][0]
        params = req.partition_parameters
        assert params.strategy == "hi_res"
        assert params.languages == ["eng"]
        assert len(result) == 1
        assert result[0]["type"] == "Title"

    def test_returns_empty_list_for_empty_doc(self, mock_unstructured_client: MagicMock):
        mock_unstructured_client.general.partition.return_value = MagicMock(elements=[])
        result = UnstructuredService.partition_document(b"", "empty.pdf")
        assert result == []


# ─── ClaudeService — classify_document ────────────────────────────────────────


class TestClassifyDocument:
    def _mock_classify_response(self, mock_client: MagicMock, text: str):
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text=text)]
        mock_client.messages.create.return_value = mock_msg

    def test_returns_structured(self, mock_anthropic_client: MagicMock):
        self._mock_classify_response(mock_anthropic_client, "structured")
        result = ClaudeService.classify_document("INVOICE #1234\nVendor: ABC\nTotal: $500")
        assert result == "structured"

    def test_returns_unstructured(self, mock_anthropic_client: MagicMock):
        self._mock_classify_response(mock_anthropic_client, "unstructured")
        result = ClaudeService.classify_document("MATERIAL SAFETY DATA SHEET")
        assert result == "unstructured"

    def test_returns_unknown_for_bad_response(self, mock_anthropic_client: MagicMock):
        self._mock_classify_response(mock_anthropic_client, "maybe-invoice")
        result = ClaudeService.classify_document("gibberish")
        assert result == "unknown"

    def test_handles_whitespace_in_response(self, mock_anthropic_client: MagicMock):
        self._mock_classify_response(mock_anthropic_client, "  Structured  \n")
        result = ClaudeService.classify_document("INVOICE")
        assert result == "structured"

    def test_uses_correct_model(self, mock_anthropic_client: MagicMock):
        self._mock_classify_response(mock_anthropic_client, "structured")
        ClaudeService.classify_document("test text")
        call_kwargs = mock_anthropic_client.messages.create.call_args.kwargs
        assert call_kwargs["model"] == "claude-opus-4-6"

    def test_truncates_long_input(self, mock_anthropic_client: MagicMock):
        self._mock_classify_response(mock_anthropic_client, "structured")
        long_text = "x" * 10000
        ClaudeService.classify_document(long_text)
        call_kwargs = mock_anthropic_client.messages.create.call_args.kwargs
        prompt_content = call_kwargs["messages"][0]["content"]
        # The document text portion should be truncated to 3000 chars
        assert len(prompt_content) < 10000


# ─── ClaudeService — extract_invoice_schema ───────────────────────────────────


class TestExtractInvoiceSchema:
    def _mock_extraction_response(self, mock_client: MagicMock, data: dict):
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text=json.dumps(data))]
        mock_client.messages.create.return_value = mock_msg

    def test_returns_parsed_json(
        self,
        mock_anthropic_client: MagicMock,
        sample_extraction_high_confidence: dict,
    ):
        self._mock_extraction_response(mock_anthropic_client, sample_extraction_high_confidence)
        result = ClaudeService.extract_invoice_schema("sample invoice text")
        assert result["vendor_name"]["value"] == "ABC Roofing Supply Co."
        assert result["vendor_name"]["confidence"] >= 0.0

    def test_includes_confidence_on_all_fields(
        self,
        mock_anthropic_client: MagicMock,
        sample_extraction_high_confidence: dict,
    ):
        self._mock_extraction_response(mock_anthropic_client, sample_extraction_high_confidence)
        result = ClaudeService.extract_invoice_schema("sample invoice text")

        for field in ["vendor_name", "invoice_number", "invoice_date", "due_date",
                      "subtotal", "tax", "total", "notes"]:
            assert "confidence" in result[field], f"Missing confidence on {field}"

        for item in result["line_items"]:
            for key in ["description", "quantity", "unit_price", "amount"]:
                assert "confidence" in item[key], f"Missing confidence on line_item.{key}"

    def test_strips_markdown_code_fences(self, mock_anthropic_client: MagicMock):
        data = {"vendor_name": {"value": "Test", "confidence": 0.9}}
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text=f"```json\n{json.dumps(data)}\n```")]
        mock_anthropic_client.messages.create.return_value = mock_msg

        result = ClaudeService.extract_invoice_schema("test")
        assert result["vendor_name"]["value"] == "Test"

    def test_uses_correct_model(self, mock_anthropic_client: MagicMock):
        self._mock_extraction_response(mock_anthropic_client, {"vendor_name": {"value": "X", "confidence": 0.9}})
        ClaudeService.extract_invoice_schema("test")
        call_kwargs = mock_anthropic_client.messages.create.call_args.kwargs
        assert call_kwargs["model"] == "claude-opus-4-6"


# ─── ClaudeService — should_auto_confirm ──────────────────────────────────────


class TestShouldAutoConfirm:
    def test_all_high_confidence_returns_true(self, sample_extraction_high_confidence: dict):
        assert ClaudeService.should_auto_confirm(sample_extraction_high_confidence) is True

    def test_low_confidence_field_returns_false(self, sample_extraction_low_confidence: dict):
        assert ClaudeService.should_auto_confirm(sample_extraction_low_confidence) is False

    def test_low_confidence_line_item_returns_false(self):
        extraction = {
            "vendor_name": {"value": "Test", "confidence": 0.99},
            "invoice_number": {"value": "123", "confidence": 0.99},
            "invoice_date": {"value": "2026-01-01", "confidence": 0.99},
            "due_date": {"value": None, "confidence": 0.95},
            "subtotal": {"value": 100.0, "confidence": 0.99},
            "tax": {"value": 10.0, "confidence": 0.99},
            "total": {"value": 110.0, "confidence": 0.99},
            "notes": {"value": None, "confidence": 0.95},
            "line_items": [
                {
                    "description": {"value": "Item", "confidence": 0.99},
                    "quantity": {"value": 1.0, "confidence": 0.50},  # Low confidence
                    "unit_price": {"value": 100.0, "confidence": 0.99},
                    "amount": {"value": 100.0, "confidence": 0.99},
                }
            ],
        }
        assert ClaudeService.should_auto_confirm(extraction) is False

    def test_threshold_boundary_exactly_095(self):
        """Confidence == 0.95 should pass (>= threshold)."""
        extraction = {
            "vendor_name": {"value": "Test", "confidence": 0.95},
            "invoice_number": {"value": "123", "confidence": 0.95},
            "invoice_date": {"value": "2026-01-01", "confidence": 0.95},
            "due_date": {"value": None, "confidence": 0.95},
            "subtotal": {"value": 100.0, "confidence": 0.95},
            "tax": {"value": 10.0, "confidence": 0.95},
            "total": {"value": 110.0, "confidence": 0.95},
            "notes": {"value": None, "confidence": 0.95},
            "line_items": [],
        }
        assert ClaudeService.should_auto_confirm(extraction) is True

    def test_empty_extraction_returns_false(self):
        """Empty extraction has 0.0 confidence on all fields → should not auto-confirm."""
        assert ClaudeService.should_auto_confirm({}) is False


# ─── ClaudeService — chunk_for_rag ────────────────────────────────────────────


class TestChunkForRag:
    def test_returns_chunks_with_embeddings(self, mock_anthropic_client: MagicMock, mock_voyage_client: MagicMock):
        # Mock Claude chunking response
        chunks_json = json.dumps([
            {"chunk_text": "Chapter 1 content about roofing materials.", "topic": "materials"},
            {"chunk_text": "Chapter 2 content about installation.", "topic": "installation"},
        ])
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text=chunks_json)]
        mock_anthropic_client.messages.create.return_value = mock_msg

        # Mock Voyage AI embeddings response (voyage-3 → 1024-dim)
        mock_embedding = MagicMock()
        mock_embedding.embeddings = [[0.1] * 1024, [0.2] * 1024]
        mock_voyage_client.embed.return_value = mock_embedding

        result = ClaudeService.chunk_for_rag("long document text", "doc-123")

        assert len(result) == 2
        assert result[0]["document_id"] == "doc-123"
        assert result[0]["chunk_text"] == "Chapter 1 content about roofing materials."
        assert len(result[0]["embedding"]) == 1024
        assert result[0]["metadata"]["topic"] == "materials"
        assert result[0]["metadata"]["chunk_index"] == 0
        assert result[1]["metadata"]["chunk_index"] == 1

    def test_uses_correct_models(self, mock_anthropic_client: MagicMock, mock_voyage_client: MagicMock):
        chunks_json = json.dumps([{"chunk_text": "test", "topic": "test"}])
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text=chunks_json)]
        mock_anthropic_client.messages.create.return_value = mock_msg

        mock_embedding = MagicMock()
        mock_embedding.embeddings = [[0.1] * 1024]
        mock_voyage_client.embed.return_value = mock_embedding

        ClaudeService.chunk_for_rag("text", "doc-1")

        # Claude reasoning call must use claude-opus-4-6
        msg_call = mock_anthropic_client.messages.create.call_args.kwargs
        assert msg_call["model"] == "claude-opus-4-6"

        # Voyage AI embed call must use voyage-3
        voyage_call = mock_voyage_client.embed.call_args
        assert voyage_call[1]["model"] == "voyage-3"

    def test_batches_embeddings_in_single_call(self, mock_anthropic_client: MagicMock, mock_voyage_client: MagicMock):
        """Voyage AI embed() should be called once with all chunks, not once per chunk."""
        chunks_json = json.dumps([
            {"chunk_text": "Chunk A", "topic": "a"},
            {"chunk_text": "Chunk B", "topic": "b"},
            {"chunk_text": "Chunk C", "topic": "c"},
        ])
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text=chunks_json)]
        mock_anthropic_client.messages.create.return_value = mock_msg

        mock_embedding = MagicMock()
        mock_embedding.embeddings = [[0.1] * 1024, [0.2] * 1024, [0.3] * 1024]
        mock_voyage_client.embed.return_value = mock_embedding

        result = ClaudeService.chunk_for_rag("text", "doc-1")

        assert len(result) == 3
        # Single batched call, not 3 individual calls
        mock_voyage_client.embed.assert_called_once()


# ─── QA: Superseded component check ──────────────────────────────────────────


class TestSupersededComponents:
    """Ensure no imports from superseded modules."""

    def test_no_temporal_client_import_in_services(self):
        """temporal_client.py is superseded — must not be imported anywhere in services."""
        import importlib
        import inspect

        from backend.services import claude_service, unstructured_service

        for mod in [claude_service, unstructured_service]:
            source = inspect.getsource(mod)
            assert "temporal_client" not in source, (
                f"{mod.__name__} imports temporal_client — this is superseded per CLAUDE.md"
            )
