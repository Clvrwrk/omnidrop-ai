"""
OmniDrop AI — Unit tests for backend services.

Tests:
  - UnstructuredService: partition_document, elements_to_text, strategy selection
  - ClaudeService: classify_document, extract_invoice_schema, chunk_for_rag,
                   score_context, detect_leakage
  - SlackAdapter: send, error handling, deep link
  - LeakageDetectionGating: detect_revenue_leakage Celery task routing
  - Confidence scoring: should_auto_confirm threshold logic

All external API calls are fully mocked. No real API keys required.
"""

import asyncio
import inspect
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from backend.services.claude_service import ClaudeService, CONFIDENCE_AUTO_CONFIRM_THRESHOLD
from backend.services.notification_service import NotificationMessage, SlackAdapter
from backend.services.unstructured_service import UnstructuredService


# ─── TestUnstructuredService ──────────────────────────────────────────────────


class TestUnstructuredService:
    """
    UnstructuredService.partition_document — strategy selection and SDK wiring.
    Maps document_type_hint → Unstructured.io strategy per CLAUDE.md spec.
    """

    def test_partition_scanned_invoice_uses_hi_res(
        self, mock_unstructured_client: MagicMock
    ):
        """document type 'scanned_invoice' (hint='invoice') → strategy hi_res."""
        mock_el = MagicMock()
        mock_el.to_dict.return_value = {
            "type": "Title",
            "text": "INVOICE",
            "metadata": {},
        }
        mock_unstructured_client.general.partition.return_value = MagicMock(
            elements=[mock_el]
        )

        UnstructuredService.partition_document(
            file_bytes=b"%PDF-fake",
            filename="scanned_invoice.pdf",
            document_type_hint="invoice",
        )

        req = mock_unstructured_client.general.partition.call_args[1]["request"]
        assert req.partition_parameters.strategy == "hi_res"

    def test_partition_digital_pdf_uses_fast(
        self, mock_unstructured_client: MagicMock
    ):
        """document type 'digital_pdf' (hint='proposal') → strategy fast."""
        mock_el = MagicMock()
        mock_el.to_dict.return_value = {
            "type": "NarrativeText",
            "text": "Proposal text",
            "metadata": {},
        }
        mock_unstructured_client.general.partition.return_value = MagicMock(
            elements=[mock_el]
        )

        UnstructuredService.partition_document(
            file_bytes=b"%PDF-digital",
            filename="proposal.pdf",
            document_type_hint="proposal",
        )

        req = mock_unstructured_client.general.partition.call_args[1]["request"]
        assert req.partition_parameters.strategy == "fast"

    def test_partition_unknown_uses_auto(
        self, mock_unstructured_client: MagicMock
    ):
        """Unknown document type → strategy auto (Unstructured picks best)."""
        mock_unstructured_client.general.partition.return_value = MagicMock(
            elements=[]
        )

        UnstructuredService.partition_document(
            file_bytes=b"%PDF-unknown",
            filename="mystery.pdf",
            document_type_hint="unknown",
        )

        req = mock_unstructured_client.general.partition.call_args[1]["request"]
        assert req.partition_parameters.strategy == "auto"

    def test_strategy_selection_msds_uses_hi_res(self):
        """_select_strategy: msds → hi_res (no API call needed)."""
        assert UnstructuredService._select_strategy("msds.pdf", "msds") == "hi_res"

    def test_strategy_selection_manual_uses_fast(self):
        """_select_strategy: manual → fast."""
        assert UnstructuredService._select_strategy("manual.pdf", "manual") == "fast"

    def test_strategy_selection_warranty_uses_fast(self):
        """_select_strategy: warranty → fast."""
        assert UnstructuredService._select_strategy("warranty.pdf", "warranty") == "fast"

    def test_partition_returns_element_list(
        self, mock_unstructured_client: MagicMock
    ):
        """partition_document returns a list of dicts from element.to_dict()."""
        mock_el1 = MagicMock()
        mock_el1.to_dict.return_value = {"type": "Title", "text": "INVOICE", "metadata": {}}
        mock_el2 = MagicMock()
        mock_el2.to_dict.return_value = {"type": "NarrativeText", "text": "Vendor: ABC", "metadata": {}}
        mock_unstructured_client.general.partition.return_value = MagicMock(
            elements=[mock_el1, mock_el2]
        )

        result = UnstructuredService.partition_document(b"%PDF", "test.pdf", "invoice")

        assert len(result) == 2
        assert result[0]["type"] == "Title"
        assert result[1]["text"] == "Vendor: ABC"

    def test_elements_to_text_joins_non_empty(self):
        """elements_to_text skips blank elements and joins the rest."""
        elements = [
            {"type": "Title", "text": "INVOICE"},
            {"type": "NarrativeText", "text": ""},
            {"type": "NarrativeText", "text": "   "},
            {"type": "NarrativeText", "text": "Total: $100"},
        ]
        text = UnstructuredService.elements_to_text(elements)
        assert "INVOICE" in text
        assert "Total: $100" in text

    def test_elements_to_text_empty_list_returns_empty(self):
        assert UnstructuredService.elements_to_text([]) == ""


# ─── TestClaudeServiceScoring ─────────────────────────────────────────────────


class TestClaudeServiceScoring:
    """
    ClaudeService.score_context — context scoring with rubric loaded from
    system_config (never hardcoded).

    Routing thresholds per CLAUDE.md:
      score >= 80  → "high"   (full pipeline + leakage detection)
      score 40-79  → "medium" (full pipeline, flagged for HITL)
      score 0-39   → "low"    (bounce back only, clarification_question set)
    """

    def _mock_score_response(
        self,
        mock_client: MagicMock,
        score: int,
        breakdown: dict | None = None,
        summary: str = "A roofing invoice.",
        clarification: str | None = None,
    ):
        """Build a mock Anthropic response for score_context."""
        payload = {
            "score": score,
            "breakdown": breakdown or {"vendor_name": 15, "amounts": 10},
            "document_summary": summary,
            "clarification_question": clarification,
        }
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text=json.dumps(payload))]
        mock_client.messages.create.return_value = mock_msg

    @pytest.mark.asyncio
    async def test_score_context_returns_valid_schema(
        self, mock_anthropic_client: MagicMock
    ):
        """score_context response dict has all required keys."""
        self._mock_score_response(mock_anthropic_client, score=85)

        with patch(
            "backend.services.claude_service.get_system_config",
            new_callable=AsyncMock,
            return_value={"vendor_name": 15, "amounts": 85},
        ):
            result = await ClaudeService.score_context(
                "INVOICE #1234\nVendor: ABC\nTotal: $1000", "invoice.pdf"
            )

        assert "score" in result
        assert "routing" in result
        assert "breakdown" in result
        assert "document_summary" in result
        assert "clarification_question" in result

    @pytest.mark.asyncio
    async def test_low_score_sets_routing_to_low(
        self, mock_anthropic_client: MagicMock
    ):
        """score < 40 → routing == 'low' (bounce-back path)."""
        self._mock_score_response(mock_anthropic_client, score=25)

        with patch(
            "backend.services.claude_service.get_system_config",
            new_callable=AsyncMock,
            return_value={"vendor_name": 15},
        ):
            result = await ClaudeService.score_context("blurry scan", "bad.pdf")

        assert result["routing"] == "low"

    @pytest.mark.asyncio
    async def test_medium_score_sets_routing_to_medium(
        self, mock_anthropic_client: MagicMock
    ):
        """40 ≤ score ≤ 79 → routing == 'medium' (HITL triage)."""
        self._mock_score_response(mock_anthropic_client, score=60)

        with patch(
            "backend.services.claude_service.get_system_config",
            new_callable=AsyncMock,
            return_value={"vendor_name": 15},
        ):
            result = await ClaudeService.score_context("partial invoice", "partial.pdf")

        assert result["routing"] == "medium"

    @pytest.mark.asyncio
    async def test_high_score_sets_routing_to_high(
        self, mock_anthropic_client: MagicMock
    ):
        """score >= 80 → routing == 'high' (full pipeline + leakage detection)."""
        self._mock_score_response(mock_anthropic_client, score=92)

        with patch(
            "backend.services.claude_service.get_system_config",
            new_callable=AsyncMock,
            return_value={"vendor_name": 15},
        ):
            result = await ClaudeService.score_context(
                "INVOICE #1234\nVendor: ABC\nTotal: $1000", "good_invoice.pdf"
            )

        assert result["routing"] == "high"

    @pytest.mark.asyncio
    async def test_low_score_boundary_39_is_low(
        self, mock_anthropic_client: MagicMock
    ):
        """score == 39 → routing == 'low' (boundary check)."""
        self._mock_score_response(mock_anthropic_client, score=39)

        with patch(
            "backend.services.claude_service.get_system_config",
            new_callable=AsyncMock,
            return_value={},
        ):
            result = await ClaudeService.score_context("x", "x.pdf")

        assert result["routing"] == "low"

    @pytest.mark.asyncio
    async def test_medium_score_boundary_40_is_medium(
        self, mock_anthropic_client: MagicMock
    ):
        """score == 40 → routing == 'medium' (boundary check)."""
        self._mock_score_response(mock_anthropic_client, score=40)

        with patch(
            "backend.services.claude_service.get_system_config",
            new_callable=AsyncMock,
            return_value={},
        ):
            result = await ClaudeService.score_context("x", "x.pdf")

        assert result["routing"] == "medium"

    @pytest.mark.asyncio
    async def test_high_score_boundary_80_is_high(
        self, mock_anthropic_client: MagicMock
    ):
        """score == 80 → routing == 'high' (boundary check)."""
        self._mock_score_response(mock_anthropic_client, score=80)

        with patch(
            "backend.services.claude_service.get_system_config",
            new_callable=AsyncMock,
            return_value={},
        ):
            result = await ClaudeService.score_context("x", "x.pdf")

        assert result["routing"] == "high"

    def test_rubric_loaded_from_system_config_not_hardcoded(self):
        """
        CLAUDE.md rule: rubric weights MUST live in system_config, never hardcoded.

        Assert that score_context() source code:
          - calls get_system_config (rubric loaded at runtime)
          - contains NO hardcoded point assignments like 'Award N points'
        """
        source = inspect.getsource(ClaudeService.score_context)

        # Must reference get_system_config to load rubric at runtime
        assert "get_system_config" in source, (
            "score_context must load rubric from get_system_config('context_score_rubric'), "
            "not hardcode weights in the function body."
        )

        # Must not contain hardcoded point strings that indicate inlined rubric weights
        forbidden_patterns = [
            "Award 15 points",
            "Award 10 points",
            "award_points",
            '"vendor_name": 15',
            '"vendor_name": 20',
        ]
        for pattern in forbidden_patterns:
            assert pattern not in source, (
                f"score_context contains hardcoded rubric weight '{pattern}'. "
                "Move it to the system_config table per CLAUDE.md."
            )

    @pytest.mark.asyncio
    async def test_clarification_question_null_for_non_low_routing(
        self, mock_anthropic_client: MagicMock
    ):
        """clarification_question is forced to None when routing != 'low'."""
        self._mock_score_response(
            mock_anthropic_client,
            score=85,
            clarification="What vendor issued this?",
        )

        with patch(
            "backend.services.claude_service.get_system_config",
            new_callable=AsyncMock,
            return_value={},
        ):
            result = await ClaudeService.score_context("invoice text", "inv.pdf")

        assert result["clarification_question"] is None

    @pytest.mark.asyncio
    async def test_clarification_question_populated_for_low_routing(
        self, mock_anthropic_client: MagicMock
    ):
        """clarification_question is preserved when routing == 'low'."""
        self._mock_score_response(
            mock_anthropic_client,
            score=20,
            clarification="Can you provide the vendor name and invoice date?",
        )

        with patch(
            "backend.services.claude_service.get_system_config",
            new_callable=AsyncMock,
            return_value={},
        ):
            result = await ClaudeService.score_context("blurry doc", "blurry.pdf")

        assert result["clarification_question"] == "Can you provide the vendor name and invoice date?"


# ─── TestClaudeServiceExtraction ─────────────────────────────────────────────


class TestClaudeServiceExtraction:
    """
    ClaudeService.extract_invoice_schema — structured extraction with per-field
    confidence scores. Used by extract_struct Celery task.
    """

    def _mock_extraction_response(self, mock_client: MagicMock, data: dict):
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text=json.dumps(data))]
        mock_client.messages.create.return_value = mock_msg

    def test_extract_invoice_schema_returns_confidence_scores(
        self,
        mock_anthropic_client: MagicMock,
        sample_extraction_high_confidence: dict,
    ):
        """Every field in the extracted schema has both 'value' and 'confidence' keys."""
        self._mock_extraction_response(
            mock_anthropic_client, sample_extraction_high_confidence
        )
        result = ClaudeService.extract_invoice_schema("INVOICE #1234 ...")

        # Header fields
        for field in [
            "vendor_name",
            "invoice_number",
            "invoice_date",
            "due_date",
            "subtotal",
            "tax",
            "total",
            "notes",
        ]:
            assert "value" in result[field], f"Missing 'value' key on field '{field}'"
            assert "confidence" in result[field], (
                f"Missing 'confidence' key on field '{field}'"
            )
            assert isinstance(result[field]["confidence"], (int, float)), (
                f"'confidence' on '{field}' must be numeric"
            )

        # Line items
        for item in result["line_items"]:
            for key in ("description", "quantity", "unit_price", "amount"):
                assert "value" in item[key], f"Missing 'value' on line_item.{key}"
                assert "confidence" in item[key], (
                    f"Missing 'confidence' on line_item.{key}"
                )

    def test_extract_handles_missing_fields_gracefully(
        self, mock_anthropic_client: MagicMock
    ):
        """
        Claude returns partial JSON (missing several fields).
        extract_invoice_schema must NOT raise a KeyError — return what was parsed.
        """
        partial_data = {
            "vendor_name": {"value": "ABC Roofing", "confidence": 0.90},
            # invoice_number, invoice_date, due_date, etc. intentionally absent
            "total": {"value": 500.00, "confidence": 0.85},
            "line_items": [],
        }
        self._mock_extraction_response(mock_anthropic_client, partial_data)

        # Must not raise KeyError
        result = ClaudeService.extract_invoice_schema("Partial invoice text")

        assert result["vendor_name"]["value"] == "ABC Roofing"
        assert result["total"]["value"] == 500.00
        assert result["line_items"] == []

    def test_extract_strips_markdown_code_fences(
        self, mock_anthropic_client: MagicMock
    ):
        """Claude wraps JSON in ```json ... ``` — service must strip fences."""
        data = {
            "vendor_name": {"value": "Fence Corp", "confidence": 0.88},
            "line_items": [],
        }
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text=f"```json\n{json.dumps(data)}\n```")]
        mock_anthropic_client.messages.create.return_value = mock_msg

        result = ClaudeService.extract_invoice_schema("text")
        assert result["vendor_name"]["value"] == "Fence Corp"

    def test_extract_uses_correct_model(self, mock_anthropic_client: MagicMock):
        """extract_invoice_schema must use claude-opus-4-6 (non-negotiable per CLAUDE.md)."""
        self._mock_extraction_response(
            mock_anthropic_client,
            {"vendor_name": {"value": "X", "confidence": 0.9}, "line_items": []},
        )
        ClaudeService.extract_invoice_schema("text")
        kwargs = mock_anthropic_client.messages.create.call_args.kwargs
        assert kwargs["model"] == "claude-opus-4-6"


# ─── TestSlackAdapter ─────────────────────────────────────────────────────────


class TestSlackAdapter:
    """
    SlackAdapter — Slack Incoming Webhook delivery via httpx.
    Alpha notification channel; used by bounce_back Celery task.
    """

    WEBHOOK_URL = "https://hooks.slack.com/services/T00/B00/fake-token"

    def _make_message(self, job_id: str = "job-abc-123") -> NotificationMessage:
        return NotificationMessage(
            location_name="Acme Roofing — Austin",
            acculynx_job_id=job_id,
            file_name="invoice_march.pdf",
            document_summary="A roofing supply invoice from ABC Co.",
            clarification_question="Can you confirm the invoice number?",
            job_deep_link=f"https://app.omnidrop.dev/dashboard/ops/jobs/{job_id}",
        )

    def test_send_posts_to_webhook_url(self):
        """SlackAdapter.send POSTs to the configured webhook URL with JSON payload."""
        adapter = SlackAdapter(webhook_url=self.WEBHOOK_URL)
        message = self._make_message()

        with patch("backend.services.notification_service.httpx.post") as mock_post:
            mock_response = MagicMock()
            mock_response.raise_for_status.return_value = None
            mock_post.return_value = mock_response

            result = adapter.send(message)

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args

        # First positional arg is the URL
        posted_url = call_kwargs[0][0] if call_kwargs[0] else call_kwargs[1].get("url")
        assert posted_url == self.WEBHOOK_URL

        # Payload must be a Block Kit dict with 'blocks'
        payload = call_kwargs[1].get("json") or call_kwargs[0][1]
        assert "blocks" in payload
        assert result["status"] == "sent"
        assert result["channel"] == "slack"

    def test_send_raises_on_non_200(self):
        """
        Slack webhook returns HTTP 500 (or any error) — httpx raises HTTPStatusError.
        SlackAdapter.send must return status='failed' (not propagate the exception
        to the caller — it logs and returns a failure dict so the Celery task can
        record it in bounce_back_log without crashing).
        """
        import httpx

        adapter = SlackAdapter(webhook_url=self.WEBHOOK_URL)
        message = self._make_message()

        with patch("backend.services.notification_service.httpx.post") as mock_post:
            mock_response = MagicMock()
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "500 Server Error",
                request=MagicMock(),
                response=MagicMock(),
            )
            mock_post.return_value = mock_response

            result = adapter.send(message)

        assert result["status"] == "failed"
        assert result["channel"] == "slack"
        assert result["error"] is not None

    def test_message_includes_deep_link(self):
        """
        The Slack Block Kit payload body must contain the deep link to
        /dashboard/ops/jobs/{job_id} so ops staff can open the document directly.
        """
        job_id = "job-deep-link-test"
        adapter = SlackAdapter(webhook_url=self.WEBHOOK_URL)
        message = self._make_message(job_id=job_id)

        captured_payload: dict = {}

        def capture_post(url: str, *, json: dict, timeout: float):
            captured_payload.update(json)
            mock_resp = MagicMock()
            mock_resp.raise_for_status.return_value = None
            return mock_resp

        with patch(
            "backend.services.notification_service.httpx.post",
            side_effect=capture_post,
        ):
            adapter.send(message)

        # Flatten all block text to a single searchable string
        all_text = json.dumps(captured_payload)
        expected_path = f"/dashboard/ops/jobs/{job_id}"
        assert expected_path in all_text, (
            f"Slack payload does not contain deep link path '{expected_path}'. "
            f"Payload: {all_text[:500]}"
        )

    def test_send_handles_none_acculynx_job_id(self):
        """acculynx_job_id=None → rendered as 'N/A' in the payload, no crash."""
        adapter = SlackAdapter(webhook_url=self.WEBHOOK_URL)
        message = NotificationMessage(
            location_name="Test Location",
            acculynx_job_id=None,
            file_name="doc.pdf",
            document_summary="Unknown document.",
            clarification_question="What is this?",
            job_deep_link="https://app.omnidrop.dev/dashboard/ops/jobs/job-xyz",
        )

        with patch("backend.services.notification_service.httpx.post") as mock_post:
            mock_response = MagicMock()
            mock_response.raise_for_status.return_value = None
            mock_post.return_value = mock_response

            result = adapter.send(message)

        assert result["status"] == "sent"
        payload_str = json.dumps(mock_post.call_args[1]["json"])
        assert "N/A" in payload_str


# ─── TestLeakageDetectionGating ───────────────────────────────────────────────


class TestLeakageDetectionGating:
    """
    detect_revenue_leakage Celery task — pricing reference gating logic.

    Per CLAUDE.md:
      1. Query pricing_contracts by organization_id — if rows exist → Contract Mode
      2. Else query vendor_baseline_prices view — if ≥3 samples per vendor → Baseline Mode
      3. Neither available → log leakage_skipped_reason='no_pricing_reference', return early

    Tests use patch on the private async helpers that the task delegates to.
    """

    _EXTRACTION_RESULT = {
        "job_id": "job-leakage-01",
        "organization_id": "org-abc",
        "location_id": "loc-xyz",
        "context_routing": "high",
        "extraction": {
            "invoice_id": "inv-001",
            "line_items": [
                {
                    "description": {"value": "GAF Timberline HDZ Shingles", "confidence": 0.97},
                    "unit_price": {"value": 40.00, "confidence": 0.98},
                    "quantity": {"value": 50.0, "confidence": 0.99},
                    "amount": {"value": 2000.00, "confidence": 0.99},
                }
            ],
        },
    }

    _CONTRACTS = [
        {
            "vendor_name": "",
            "description": "GAF Timberline HDZ Shingles",
            "contracted_unit_price": 35.00,
        }
    ]

    _BASELINE_ROWS = [
        {
            "vendor_name": "",
            "description": "GAF Timberline HDZ Shingles",
            "baseline_unit_price": 36.00,
            "sample_count": 5,
        }
    ]

    def test_contract_mode_used_when_pricing_contracts_exist(self):
        """
        When _query_pricing_contracts returns rows → ClaudeService.detect_leakage
        is called with reference_mode='contract'.
        """
        from backend.workers import intake_tasks

        with (
            patch.object(
                intake_tasks,
                "_query_pricing_contracts",
                new=AsyncMock(return_value=self._CONTRACTS),
            ),
            patch.object(
                intake_tasks,
                "_query_vendor_baseline_prices",
                new=AsyncMock(return_value=[]),
            ),
            patch.object(
                intake_tasks,
                "_update_job_leakage_skipped",
                new=AsyncMock(),
            ),
            patch.object(
                intake_tasks,
                "_write_revenue_findings",
                new=AsyncMock(),
            ),
            patch(
                "backend.services.claude_service.ClaudeService.detect_leakage",
                return_value=[],
            ) as mock_detect,
        ):
            # Invoke the task function directly (bypassing Celery broker)
            self_mock = MagicMock()
            result = intake_tasks.detect_revenue_leakage(
                self_mock, self._EXTRACTION_RESULT
            )

        # detect_leakage must have been called with reference_mode='contract'
        mock_detect.assert_called_once()
        call_kwargs = mock_detect.call_args
        reference_mode = (
            call_kwargs[1].get("reference_mode")
            or call_kwargs[0][2]
        )
        assert reference_mode == "contract", (
            f"Expected reference_mode='contract', got '{reference_mode}'"
        )

    def test_baseline_mode_used_when_sufficient_samples(self):
        """
        No contracts + vendor_baseline_prices has rows → detect_leakage called
        with reference_mode='baseline'.
        """
        from backend.workers import intake_tasks

        with (
            patch.object(
                intake_tasks,
                "_query_pricing_contracts",
                new=AsyncMock(return_value=[]),
            ),
            patch.object(
                intake_tasks,
                "_query_vendor_baseline_prices",
                new=AsyncMock(return_value=self._BASELINE_ROWS),
            ),
            patch.object(
                intake_tasks,
                "_update_job_leakage_skipped",
                new=AsyncMock(),
            ),
            patch.object(
                intake_tasks,
                "_write_revenue_findings",
                new=AsyncMock(),
            ),
            patch(
                "backend.services.claude_service.ClaudeService.detect_leakage",
                return_value=[],
            ) as mock_detect,
        ):
            self_mock = MagicMock()
            result = intake_tasks.detect_revenue_leakage(
                self_mock, self._EXTRACTION_RESULT
            )

        mock_detect.assert_called_once()
        call_kwargs = mock_detect.call_args
        reference_mode = (
            call_kwargs[1].get("reference_mode")
            or call_kwargs[0][2]
        )
        assert reference_mode == "baseline", (
            f"Expected reference_mode='baseline', got '{reference_mode}'"
        )

    def test_skip_when_no_reference(self):
        """
        No contracts AND no baseline samples → task returns early with
        finding_count=0 and logs leakage_skipped_reason='no_pricing_reference'.
        ClaudeService.detect_leakage must NOT be called.
        """
        from backend.workers import intake_tasks

        mock_update_skipped = AsyncMock()

        with (
            patch.object(
                intake_tasks,
                "_query_pricing_contracts",
                new=AsyncMock(return_value=[]),
            ),
            patch.object(
                intake_tasks,
                "_query_vendor_baseline_prices",
                new=AsyncMock(return_value=[]),
            ),
            patch.object(
                intake_tasks,
                "_update_job_leakage_skipped",
                new=mock_update_skipped,
            ),
            patch(
                "backend.services.claude_service.ClaudeService.detect_leakage",
            ) as mock_detect,
        ):
            self_mock = MagicMock()
            result = intake_tasks.detect_revenue_leakage(
                self_mock, self._EXTRACTION_RESULT
            )

        # detect_leakage must NOT run against an empty reference
        mock_detect.assert_not_called()

        # Result signals the skip
        assert result["finding_count"] == 0

        # _update_job_leakage_skipped must be called with 'no_pricing_reference'
        mock_update_skipped.assert_called_once()
        skipped_reason_arg = mock_update_skipped.call_args[0][1]
        assert skipped_reason_arg == "no_pricing_reference", (
            f"Expected leakage_skipped_reason='no_pricing_reference', got '{skipped_reason_arg}'"
        )


# ─── Legacy tests preserved from prior session ────────────────────────────────
# These tests cover strategy selection detail, confidence thresholds, chunk_for_rag,
# classify_document, and superseded-component guards. They do not overlap with
# the required T1-14 classes above.


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
        assert len(prompt_content) < 10000


class TestExtractInvoiceSchemaLegacy:
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
        assert ClaudeService.should_auto_confirm({}) is False


class TestChunkForRag:
    def test_returns_chunks_with_embeddings(
        self, mock_anthropic_client: MagicMock, mock_voyage_client: MagicMock
    ):
        chunks_json = json.dumps([
            {"chunk_text": "Chapter 1 content about roofing materials.", "topic": "materials"},
            {"chunk_text": "Chapter 2 content about installation.", "topic": "installation"},
        ])
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text=chunks_json)]
        mock_anthropic_client.messages.create.return_value = mock_msg

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

    def test_uses_correct_models(
        self, mock_anthropic_client: MagicMock, mock_voyage_client: MagicMock
    ):
        chunks_json = json.dumps([{"chunk_text": "test", "topic": "test"}])
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text=chunks_json)]
        mock_anthropic_client.messages.create.return_value = mock_msg

        mock_embedding = MagicMock()
        mock_embedding.embeddings = [[0.1] * 1024]
        mock_voyage_client.embed.return_value = mock_embedding

        ClaudeService.chunk_for_rag("text", "doc-1")

        msg_call = mock_anthropic_client.messages.create.call_args.kwargs
        assert msg_call["model"] == "claude-opus-4-6"

        voyage_call = mock_voyage_client.embed.call_args
        assert voyage_call[1]["model"] == "voyage-3"

    def test_batches_embeddings_in_single_call(
        self, mock_anthropic_client: MagicMock, mock_voyage_client: MagicMock
    ):
        """Voyage AI embed() must be called once with all chunks, not once per chunk."""
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
        mock_voyage_client.embed.assert_called_once()


class TestSupersededComponents:
    """Ensure no imports from superseded modules."""

    def test_no_temporal_client_import_in_services(self):
        """temporal_client.py is superseded — must not be imported anywhere in services."""
        from backend.services import claude_service, unstructured_service

        for mod in [claude_service, unstructured_service]:
            source = inspect.getsource(mod)
            assert "temporal_client" not in source, (
                f"{mod.__name__} imports temporal_client — this is superseded per CLAUDE.md"
            )
