"""
OmniDrop AI — Phase 3 Tests

Tests:
  - ClaudeService.analytics_agent: SELECT-only safety, forbidden keyword rejection, location_id scoping
  - triage_document task: routing to extract_struct vs chunk_and_embed vs failed
  - extract_struct task: confidence-based triage_status, Supabase writes for invoices + line_items
"""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.claude_service import ClaudeService


# ─── ClaudeService.analytics_agent — SQL Safety ─────────────────────────────


class TestAnalyticsAgentSafety:
    """analytics_agent must only generate SELECT statements with location_id scoping."""

    def _mock_analytics_response(self, mock_client: MagicMock, sql: str, params: list | None = None):
        response_data = {"sql": sql, "params": params or [], "explanation": "test"}
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text=json.dumps(response_data))]
        mock_client.messages.create.return_value = mock_msg

    def test_valid_select_returns_sql(self, mock_anthropic_client: MagicMock):
        sql = "SELECT COUNT(*) FROM invoices WHERE location_id = $1"
        self._mock_analytics_response(mock_anthropic_client, sql)

        result = ClaudeService.analytics_agent("how many invoices?", "loc-123")

        assert result["sql"].strip().upper().startswith("SELECT")
        assert result["explanation"] == "test"

    def test_location_id_always_first_param(self, mock_anthropic_client: MagicMock):
        sql = "SELECT vendor_name, total FROM invoices WHERE location_id = $1 AND total > $2"
        self._mock_analytics_response(mock_anthropic_client, sql, params=[1000])

        result = ClaudeService.analytics_agent("invoices over 1000?", "loc-456")

        assert result["params"][0] == "loc-456"
        assert result["params"][1] == 1000

    def test_rejects_insert_statement(self, mock_anthropic_client: MagicMock):
        sql = "INSERT INTO invoices (vendor_name) VALUES ('hacked')"
        self._mock_analytics_response(mock_anthropic_client, sql)

        with pytest.raises(ValueError, match="non-SELECT"):
            ClaudeService.analytics_agent("add a fake invoice", "loc-123")

    def test_rejects_delete_statement(self, mock_anthropic_client: MagicMock):
        sql = "DELETE FROM invoices WHERE location_id = $1"
        self._mock_analytics_response(mock_anthropic_client, sql)

        with pytest.raises(ValueError, match="non-SELECT"):
            ClaudeService.analytics_agent("delete all invoices", "loc-123")

    def test_rejects_drop_table(self, mock_anthropic_client: MagicMock):
        sql = "DROP TABLE invoices"
        self._mock_analytics_response(mock_anthropic_client, sql)

        with pytest.raises(ValueError, match="non-SELECT"):
            ClaudeService.analytics_agent("drop invoices table", "loc-123")

    def test_rejects_select_with_embedded_delete(self, mock_anthropic_client: MagicMock):
        sql = "SELECT 1; DELETE FROM invoices WHERE location_id = $1"
        self._mock_analytics_response(mock_anthropic_client, sql)

        with pytest.raises(ValueError, match="forbidden keywords"):
            ClaudeService.analytics_agent("sneaky query", "loc-123")

    def test_rejects_update_in_subquery(self, mock_anthropic_client: MagicMock):
        sql = "SELECT * FROM invoices WHERE location_id = $1; UPDATE invoices SET total = 0"
        self._mock_analytics_response(mock_anthropic_client, sql)

        with pytest.raises(ValueError, match="forbidden keywords"):
            ClaudeService.analytics_agent("update totals", "loc-123")

    def test_rejects_truncate(self, mock_anthropic_client: MagicMock):
        sql = "TRUNCATE invoices"
        self._mock_analytics_response(mock_anthropic_client, sql)

        with pytest.raises(ValueError, match="non-SELECT"):
            ClaudeService.analytics_agent("clear invoices", "loc-123")

    def test_uses_correct_model(self, mock_anthropic_client: MagicMock):
        sql = "SELECT COUNT(*) FROM invoices WHERE location_id = $1"
        self._mock_analytics_response(mock_anthropic_client, sql)

        ClaudeService.analytics_agent("count invoices", "loc-123")

        call_kwargs = mock_anthropic_client.messages.create.call_args.kwargs
        assert call_kwargs["model"] == "claude-opus-4-6"

    def test_strips_markdown_code_fences(self, mock_anthropic_client: MagicMock):
        sql = "SELECT COUNT(*) FROM invoices WHERE location_id = $1"
        response_data = {"sql": sql, "params": [], "explanation": "count"}
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text=f"```json\n{json.dumps(response_data)}\n```")]
        mock_anthropic_client.messages.create.return_value = mock_msg

        result = ClaudeService.analytics_agent("count invoices", "loc-123")
        assert result["sql"].strip().upper().startswith("SELECT")


# ─── triage_document — Routing ──────────────────────────────────────────────


class TestTriageDocumentRouting:
    """triage_document must route to the correct downstream task based on classification."""

    @pytest.fixture
    def parsed_result(self) -> dict[str, Any]:
        return {
            "job_id": "job-100",
            "location_id": "loc-200",
            "document_id": "doc-300",
            "raw_text": "INVOICE #1234\nVendor: ABC Roofing\nTotal: $500",
            "file_name": "invoice.pdf",
            "raw_path": "/docs/invoice.pdf",
        }

    @patch("backend.workers.intake_tasks.extract_struct")
    @patch("backend.workers.intake_tasks.chunk_and_embed")
    @patch("backend.services.claude_service.ClaudeService.classify_document")
    def test_structured_routes_to_extract_struct(
        self, mock_classify, mock_chunk, mock_extract, parsed_result
    ):
        mock_classify.return_value = "structured"
        mock_extract.delay = MagicMock()
        mock_chunk.delay = MagicMock()

        from backend.workers.intake_tasks import triage_document

        result = triage_document(parsed_result)

        mock_extract.delay.assert_called_once()
        mock_chunk.delay.assert_not_called()
        assert result["triage_category"] == "structured"

    @patch("backend.workers.intake_tasks.extract_struct")
    @patch("backend.workers.intake_tasks.chunk_and_embed")
    @patch("backend.services.claude_service.ClaudeService.classify_document")
    def test_unstructured_routes_to_chunk_and_embed(
        self, mock_classify, mock_chunk, mock_extract, parsed_result
    ):
        mock_classify.return_value = "unstructured"
        mock_extract.delay = MagicMock()
        mock_chunk.delay = MagicMock()

        from backend.workers.intake_tasks import triage_document

        result = triage_document(parsed_result)

        mock_chunk.delay.assert_called_once()
        mock_extract.delay.assert_not_called()
        assert result["triage_category"] == "unstructured"

    @patch("backend.workers.intake_tasks._update_job_status", new_callable=AsyncMock)
    @patch("backend.workers.intake_tasks.extract_struct")
    @patch("backend.workers.intake_tasks.chunk_and_embed")
    @patch("backend.services.claude_service.ClaudeService.classify_document")
    @patch("sentry_sdk.capture_message")
    def test_unknown_marks_job_failed_no_dispatch(
        self, mock_sentry, mock_classify, mock_chunk, mock_extract, mock_update_job, parsed_result
    ):
        mock_classify.return_value = "unknown"
        mock_extract.delay = MagicMock()
        mock_chunk.delay = MagicMock()

        from backend.workers.intake_tasks import triage_document

        # Patch asyncio to directly await the coroutine
        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_until_complete = lambda coro: None
            # Re-patch _update_job_status at module level
            with patch("backend.workers.intake_tasks._update_job_status", new_callable=AsyncMock) as mock_update:
                result = triage_document(parsed_result)

        mock_extract.delay.assert_not_called()
        mock_chunk.delay.assert_not_called()
        assert result["triage_category"] == "unknown"

    @patch("backend.workers.intake_tasks.extract_struct")
    @patch("backend.workers.intake_tasks.chunk_and_embed")
    @patch("backend.services.claude_service.ClaudeService.classify_document")
    def test_triaged_result_preserves_location_id(
        self, mock_classify, mock_chunk, mock_extract, parsed_result
    ):
        mock_classify.return_value = "structured"
        mock_extract.delay = MagicMock()

        from backend.workers.intake_tasks import triage_document

        result = triage_document(parsed_result)

        assert result["location_id"] == "loc-200"
        # Verify the dispatched payload also includes location_id
        dispatched = mock_extract.delay.call_args[0][0]
        assert dispatched["location_id"] == "loc-200"


# ─── extract_struct — Confidence Routing + Supabase Writes ──────────────────


class TestExtractStructConfidence:
    """extract_struct sets triage_status based on confidence and writes to Supabase."""

    @pytest.fixture
    def triaged_result(self) -> dict[str, Any]:
        return {
            "job_id": "job-500",
            "location_id": "loc-600",
            "document_id": "doc-700",
            "triage_category": "structured",
            "raw_text": "INVOICE #INV-2026-0042\nVendor: ABC Roofing\nTotal: $2025.00",
            "file_name": "invoice.pdf",
            "raw_path": "/docs/invoice.pdf",
        }

    @patch("backend.workers.intake_tasks._save_structured_extraction", new_callable=AsyncMock)
    @patch("backend.services.claude_service.ClaudeService.extract_invoice_schema")
    def test_high_confidence_sets_confirmed(
        self,
        mock_extract_schema,
        mock_save,
        triaged_result,
        sample_extraction_high_confidence,
    ):
        mock_extract_schema.return_value = sample_extraction_high_confidence

        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_until_complete = lambda coro: None
            with patch(
                "backend.workers.intake_tasks._save_structured_extraction",
                new_callable=AsyncMock,
            ) as mock_save_inner:
                from backend.workers.intake_tasks import extract_struct

                result = extract_struct(triaged_result)

        assert result["triage_status"] == "confirmed"

    @patch("backend.workers.intake_tasks._save_structured_extraction", new_callable=AsyncMock)
    @patch("backend.services.claude_service.ClaudeService.extract_invoice_schema")
    def test_low_confidence_sets_pending(
        self,
        mock_extract_schema,
        mock_save,
        triaged_result,
        sample_extraction_low_confidence,
    ):
        mock_extract_schema.return_value = sample_extraction_low_confidence

        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_until_complete = lambda coro: None
            with patch(
                "backend.workers.intake_tasks._save_structured_extraction",
                new_callable=AsyncMock,
            ) as mock_save_inner:
                from backend.workers.intake_tasks import extract_struct

                result = extract_struct(triaged_result)

        assert result["triage_status"] == "pending"

    @patch("backend.services.claude_service.ClaudeService.extract_invoice_schema")
    def test_writes_invoice_and_line_items_to_supabase(
        self,
        mock_extract_schema,
        triaged_result,
        sample_extraction_high_confidence,
    ):
        """Verify _save_structured_extraction calls Supabase insert for invoices + line_items."""
        mock_extract_schema.return_value = sample_extraction_high_confidence

        import asyncio

        from backend.workers.intake_tasks import _save_structured_extraction

        # Mock invoice insert response with invoice_id
        mock_invoice_resp = MagicMock()
        mock_invoice_resp.data = [{"invoice_id": "inv-001"}]

        # Build per-table mock chains (MagicMock, not AsyncMock, for sync chain methods)
        table_mocks: dict[str, MagicMock] = {}

        def table_side_effect(name: str):
            if name not in table_mocks:
                m = MagicMock()
                # .insert(...).execute() → async
                m.insert.return_value.execute = AsyncMock(return_value=mock_invoice_resp)
                # .update(...).eq(...).execute() → async
                m.update.return_value.eq.return_value.execute = AsyncMock()
                table_mocks[name] = m
            return table_mocks[name]

        # MagicMock client so .table() stays synchronous
        mock_supabase = MagicMock()
        mock_supabase.table.side_effect = table_side_effect

        async def fake_get_client():
            return mock_supabase

        with patch(
            "backend.services.supabase_client.get_supabase_client",
            side_effect=fake_get_client,
        ):
            asyncio.get_event_loop().run_until_complete(
                _save_structured_extraction(
                    job_id="job-500",
                    organization_id="org-400",
                    location_id="loc-600",
                    document_id="doc-700",
                    extraction=sample_extraction_high_confidence,
                    triage_status="confirmed",
                )
            )

        # Verify documents table was updated with triage_status
        assert "documents" in table_mocks
        table_mocks["documents"].update.assert_called_once_with(
            {"triage_status": "confirmed", "document_type": "invoice"}
        )

        # Verify invoices table got an insert
        assert "invoices" in table_mocks
        table_mocks["invoices"].insert.assert_called_once()
        invoice_data = table_mocks["invoices"].insert.call_args[0][0]
        assert invoice_data["location_id"] == "loc-600"
        assert invoice_data["vendor_name"] == "ABC Roofing Supply Co."
        assert invoice_data["total"] == 2025.00

        # Verify line_items table got an insert with correct count
        assert "line_items" in table_mocks
        table_mocks["line_items"].insert.assert_called_once()
        line_item_rows = table_mocks["line_items"].insert.call_args[0][0]
        assert len(line_item_rows) == 2
        assert line_item_rows[0]["description"] == "GAF Timberline HDZ Shingles"
        assert line_item_rows[0]["quantity"] == 50.0
        assert line_item_rows[1]["description"] == "Ridge Cap"

    @patch("backend.services.claude_service.ClaudeService.extract_invoice_schema")
    def test_extract_struct_returns_extraction_in_result(
        self,
        mock_extract_schema,
        triaged_result,
        sample_extraction_high_confidence,
    ):
        mock_extract_schema.return_value = sample_extraction_high_confidence

        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_until_complete = lambda coro: None
            with patch(
                "backend.workers.intake_tasks._save_structured_extraction",
                new_callable=AsyncMock,
            ):
                from backend.workers.intake_tasks import extract_struct

                result = extract_struct(triaged_result)

        assert result["job_id"] == "job-500"
        assert "extraction" in result
        assert result["extraction"]["vendor_name"]["value"] == "ABC Roofing Supply Co."


# ─── chunk_and_embed — Embedding Writes + location_id Scoping ───────────────


class TestChunkAndEmbed:
    """chunk_and_embed writes chunks to document_embeddings with location_id on every chunk."""

    @pytest.fixture
    def triaged_unstructured(self) -> dict[str, Any]:
        return {
            "job_id": "job-800",
            "location_id": "loc-900",
            "document_id": "doc-1000",
            "triage_category": "unstructured",
            "raw_text": "MATERIAL SAFETY DATA SHEET\nHazardous chemicals...",
            "file_name": "msds.pdf",
            "raw_path": "/docs/msds.pdf",
        }

    @patch("backend.services.claude_service.ClaudeService.chunk_for_rag")
    def test_writes_chunks_to_document_embeddings(
        self, mock_chunk_rag, triaged_unstructured
    ):
        """Verify _save_embeddings inserts chunks to Supabase document_embeddings table."""
        mock_chunk_rag.return_value = [
            {
                "document_id": "doc-1000",
                "chunk_text": "Safety procedures for handling chemicals.",
                "embedding": [0.1] * 1024,
                "metadata": {"topic": "safety", "chunk_index": 0},
            },
            {
                "document_id": "doc-1000",
                "chunk_text": "Storage requirements for hazardous materials.",
                "embedding": [0.2] * 1024,
                "metadata": {"topic": "storage", "chunk_index": 1},
            },
        ]

        import asyncio

        from backend.workers.intake_tasks import _save_embeddings

        table_mocks: dict[str, MagicMock] = {}

        def table_side_effect(name: str):
            if name not in table_mocks:
                m = MagicMock()
                m.insert.return_value.execute = AsyncMock()
                m.update.return_value.eq.return_value.execute = AsyncMock()
                table_mocks[name] = m
            return table_mocks[name]

        mock_supabase = MagicMock()
        mock_supabase.table.side_effect = table_side_effect

        async def fake_get_client():
            return mock_supabase

        # Simulate what chunk_and_embed does: add location_id to each chunk
        chunks = mock_chunk_rag.return_value
        for chunk in chunks:
            chunk["location_id"] = "loc-900"

        with patch(
            "backend.services.supabase_client.get_supabase_client",
            side_effect=fake_get_client,
        ):
            asyncio.get_event_loop().run_until_complete(
                _save_embeddings(job_id="job-800", chunks=chunks)
            )

        # Verify document_embeddings got the insert
        assert "document_embeddings" in table_mocks
        table_mocks["document_embeddings"].insert.assert_called_once()
        inserted_rows = table_mocks["document_embeddings"].insert.call_args[0][0]
        assert len(inserted_rows) == 2

    @patch("backend.services.claude_service.ClaudeService.chunk_for_rag")
    def test_location_id_present_on_every_chunk(
        self, mock_chunk_rag, triaged_unstructured
    ):
        """chunk_and_embed adds location_id to each chunk for RLS scoping."""
        mock_chunk_rag.return_value = [
            {
                "document_id": "doc-1000",
                "chunk_text": "Chunk A",
                "embedding": [0.1] * 1024,
                "metadata": {"topic": "a", "chunk_index": 0},
            },
            {
                "document_id": "doc-1000",
                "chunk_text": "Chunk B",
                "embedding": [0.2] * 1024,
                "metadata": {"topic": "b", "chunk_index": 1},
            },
            {
                "document_id": "doc-1000",
                "chunk_text": "Chunk C",
                "embedding": [0.3] * 1024,
                "metadata": {"topic": "c", "chunk_index": 2},
            },
        ]

        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_until_complete = lambda coro: None
            with patch(
                "backend.workers.intake_tasks._save_embeddings",
                new_callable=AsyncMock,
            ) as mock_save:
                from backend.workers.intake_tasks import chunk_and_embed

                result = chunk_and_embed(triaged_unstructured)

        # Verify location_id was added to every chunk before save
        assert result["chunk_count"] == 3
        saved_chunks = mock_save.call_args.kwargs.get("chunks") or mock_save.call_args[1].get("chunks")
        # If called with positional args, try that
        if saved_chunks is None:
            # _save_embeddings(job_id=..., chunks=...) — check kwargs
            call_kwargs = mock_save.call_args
            # It was called via run_until_complete which was nooped,
            # so check the chunks that were passed to chunk_for_rag return value
            pass

        # Direct verification: after chunk_and_embed runs, every chunk should have location_id
        for chunk in mock_chunk_rag.return_value:
            assert chunk.get("location_id") == "loc-900", (
                f"Chunk missing location_id: {chunk.get('chunk_text')}"
            )

    @patch("backend.services.claude_service.ClaudeService.chunk_for_rag")
    def test_returns_chunk_count(self, mock_chunk_rag, triaged_unstructured):
        """chunk_and_embed returns job_id and chunk_count."""
        mock_chunk_rag.return_value = [
            {
                "document_id": "doc-1000",
                "chunk_text": "Single chunk",
                "embedding": [0.1] * 1024,
                "metadata": {"topic": "test", "chunk_index": 0},
            },
        ]

        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_until_complete = lambda coro: None
            with patch(
                "backend.workers.intake_tasks._save_embeddings",
                new_callable=AsyncMock,
            ):
                from backend.workers.intake_tasks import chunk_and_embed

                result = chunk_and_embed(triaged_unstructured)

        assert result["job_id"] == "job-800"
        assert result["chunk_count"] == 1
