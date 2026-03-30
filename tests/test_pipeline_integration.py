"""
OmniDrop AI — Pipeline Integration Tests
T1-13: Full document processing pipeline integration tests.

Tests the orchestration logic of the intake pipeline without calling real external
services (Unstructured.io, Claude API, Voyage AI, AccuLynx API).

Mocking strategy:
  - Patch at the import location: @patch("backend.workers.intake_tasks.<symbol>")
  - No real DB calls — tests that require DB state are marked with pytest.mark.skip
    and a comment explaining the Supabase MCP approach (mcp__plugin_supabase_supabase__execute_sql).
  - No real Celery broker — tasks are called directly with mocked .delay() chaining.

CLAUDE.md webhook contract (4 steps):
  1. Verify Hookdeck HMAC-SHA256 signature → 401 if invalid
  2. Validate payload shape with Pydantic → 422 if malformed
  3. Call process_document.delay(job_payload)
  4. Return 200 OK immediately
"""

import hashlib
import hmac
import io
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from fastapi.testclient import TestClient


# ── Helpers ──────────────────────────────────────────────────────────────────

TEST_SIGNING_SECRET = "test-hookdeck-integration-secret"


def _make_hookdeck_signature(body: bytes, secret: str = TEST_SIGNING_SECRET) -> str:
    """Produce a valid Hookdeck HMAC-SHA256 signature header value."""
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _post_webhook(
    client: TestClient,
    payload: dict[str, Any],
    secret: str = TEST_SIGNING_SECRET,
    sig_override: str | None = None,
    extra_headers: dict[str, str] | None = None,
) -> Any:
    """POST to the webhook endpoint with a valid (or overridden) HMAC signature."""
    body = json.dumps(payload).encode()
    sig = sig_override or _make_hookdeck_signature(body, secret)
    headers = {
        "x-hookdeck-signature": sig,
        "content-type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)
    return client.post("/api/v1/webhooks/acculynx", content=body, headers=headers)


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def app_client():
    """
    TestClient with Sentry, logging, and settings patched so the app initialises
    without real environment variables. Module-scoped to avoid re-importing the
    FastAPI app on every test (import has Sentry side-effects).
    """
    with patch("backend.core.config.get_settings") as mock_get_settings:
        mock_s = mock_get_settings.return_value
        mock_s.app_env = "local"
        mock_s.cors_origins = ["http://localhost:3000"]
        mock_s.hookdeck_signing_secret = TEST_SIGNING_SECRET
        mock_s.sentry_python_dsn = None
        mock_s.sentry_traces_sample_rate = 0.0
        mock_s.app_base_url = "https://app.omnidrop.dev"

        with (
            patch("backend.core.sentry.configure_sentry"),
            patch("backend.core.logging.configure_logging"),
        ):
            from backend.api.main import app
            yield TestClient(app)


@pytest.fixture
def valid_webhook_payload() -> dict[str, Any]:
    return {
        "event": {
            "event_type": "document.uploaded",
            "job_id": "job-integration-001",
            "location_id": "loc-integration-001",
            "timestamp": "2026-03-29T10:00:00Z",
            "document_id": "doc-integration-001",
            "document_url": "https://api.acculynx.com/docs/integration-001",
            "data": {},
        },
        "version": "1.0",
    }


@pytest.fixture
def scored_result_high() -> dict[str, Any]:
    """Mocked score_context output for a HIGH-context document (score 85)."""
    return {
        "job_id": "job-high-001",
        "organization_id": "org-test-001",
        "location_id": "loc-test-001",
        "document_id": "doc-high-001",
        "raw_text": "Invoice #INV-001 from ABC Roofing Supply. Total: $5000.00",
        "file_name": "invoice_high.pdf",
        "raw_path": None,
        "score": 85,
        "routing": "high",
        "context_routing": "high",
        "breakdown": {},
        "document_summary": "Structured invoice from ABC Roofing Supply.",
        "clarification_question": None,
        "acculynx_job_id": "job-high-001",
    }


@pytest.fixture
def scored_result_medium() -> dict[str, Any]:
    """Mocked score_context output for a MEDIUM-context document (score 60)."""
    return {
        "job_id": "job-medium-001",
        "organization_id": "org-test-001",
        "location_id": "loc-test-001",
        "document_id": "doc-medium-001",
        "raw_text": "Some roofing proposal with missing vendor details.",
        "file_name": "proposal_medium.pdf",
        "raw_path": None,
        "score": 60,
        "routing": "medium",
        "context_routing": "medium",
        "breakdown": {},
        "document_summary": "Proposal with unclear vendor information.",
        "clarification_question": "Can you confirm the vendor name?",
        "acculynx_job_id": "job-medium-001",
    }


@pytest.fixture
def scored_result_low() -> dict[str, Any]:
    """Mocked score_context output for a LOW-context document (score 25)."""
    return {
        "job_id": "job-low-001",
        "organization_id": "org-test-001",
        "location_id": "loc-test-001",
        "document_id": "doc-low-001",
        "raw_text": "Fax cover sheet. No invoice content.",
        "file_name": "fax_low.pdf",
        "raw_path": None,
        "score": 25,
        "routing": "low",
        "context_routing": "low",
        "breakdown": {},
        "document_summary": "Fax cover sheet — insufficient content.",
        "clarification_question": "Please resubmit the actual invoice.",
        "acculynx_job_id": "job-low-001",
    }


# ══════════════════════════════════════════════════════════════════════════════
# Class 1 — TestWebhookEndpoint
# ══════════════════════════════════════════════════════════════════════════════


class TestWebhookEndpoint:
    """
    Integration tests for the POST /api/v1/webhooks/acculynx endpoint.

    CLAUDE.md contract: verify HMAC → validate Pydantic → dispatch Celery → 200 OK.
    The endpoint must NEVER call Unstructured.io, Claude, or Supabase.
    """

    def test_valid_signature_dispatches_task(
        self, app_client: TestClient, valid_webhook_payload: dict[str, Any]
    ) -> None:
        """
        A POST with a valid Hookdeck HMAC-SHA256 signature and well-formed payload:
          - Returns HTTP 200
          - Calls process_document.delay() exactly once
        """
        with patch("backend.api.v1.webhooks.process_document") as mock_task:
            response = _post_webhook(app_client, valid_webhook_payload)

        assert response.status_code == 200
        mock_task.delay.assert_called_once()

        # Verify the job payload passed to Celery has expected keys
        call_args = mock_task.delay.call_args[0][0]
        assert call_args["job_id"] == "job-integration-001"
        assert call_args["location_id"] == "loc-integration-001"
        assert call_args["event_type"] == "document.uploaded"
        assert call_args["document_id"] == "doc-integration-001"
        assert "received_at" in call_args

    def test_invalid_signature_returns_401(
        self, app_client: TestClient, valid_webhook_payload: dict[str, Any]
    ) -> None:
        """
        A tampered payload (signature does not match body) must be rejected with 401.
        process_document.delay() must NOT be called.
        """
        with patch("backend.api.v1.webhooks.process_document") as mock_task:
            response = _post_webhook(
                app_client,
                valid_webhook_payload,
                sig_override="sha256=0000000000000000000000000000000000000000000000000000000000000000",
            )

        assert response.status_code == 401
        mock_task.delay.assert_not_called()

    def test_malformed_payload_returns_422(self, app_client: TestClient) -> None:
        """
        A payload missing required fields (job_id, location_id, timestamp) must
        be rejected with 422 Unprocessable Entity after HMAC verification passes.
        """
        bad_payload = {
            "event": {
                "event_type": "document.uploaded",
                # Missing: job_id, location_id, timestamp — all required by AccuLynxJobEvent
            }
        }
        body = json.dumps(bad_payload).encode()
        sig = _make_hookdeck_signature(body)

        with patch("backend.api.v1.webhooks.process_document") as mock_task:
            response = app_client.post(
                "/api/v1/webhooks/acculynx",
                content=body,
                headers={"x-hookdeck-signature": sig, "content-type": "application/json"},
            )

        assert response.status_code == 422
        mock_task.delay.assert_not_called()

    def test_webhook_does_not_call_external_services(
        self, app_client: TestClient, valid_webhook_payload: dict[str, Any]
    ) -> None:
        """
        CLAUDE.md: 'This endpoint NEVER calls Unstructured.io, Claude, or Supabase.'

        Confirms that none of the external service singletons are touched during
        a valid webhook request when no WorkOS org header is present (Hookdeck path).
        """
        with (
            patch("backend.api.v1.webhooks.process_document"),
            patch("backend.services.supabase_client.get_supabase_client") as mock_sb,
            patch("backend.services.claude_service._get_client") as mock_claude,
            patch("backend.services.unstructured_service._get_client") as mock_unst,
        ):
            response = _post_webhook(app_client, valid_webhook_payload)

        assert response.status_code == 200
        mock_sb.assert_not_called()
        mock_claude.assert_not_called()
        mock_unst.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════════
# Class 2 — TestPipelineRouting
# ══════════════════════════════════════════════════════════════════════════════


class TestPipelineRouting:
    """
    Integration tests for score_context routing logic.

    score_context reads the Claude scoring result and dispatches:
      - HIGH  (80–100): triage_document.delay()
      - MEDIUM (40–79): triage_document.delay() with needs_clarity flag propagated
      - LOW    (0–39):  bounce_back.delay() — triage_document must NOT be called
    """

    def test_high_context_routes_to_full_pipeline(
        self, scored_result_high: dict[str, Any]
    ) -> None:
        """
        score 85 → routing='high' → triage_document dispatched.
        bounce_back must NOT be called.
        """
        with (
            patch("backend.services.claude_service.ClaudeService") as mock_claude,
            patch("backend.workers.intake_tasks.triage_document") as mock_triage,
            patch("backend.workers.intake_tasks.bounce_back") as mock_bounce,
            patch("backend.workers.intake_tasks._update_job_context_score", new_callable=AsyncMock),
        ):
            mock_claude.score_context = AsyncMock(
                return_value={
                    "score": 85,
                    "routing": "high",
                    "breakdown": {},
                    "document_summary": "High-context invoice.",
                    "clarification_question": None,
                }
            )

            # Call score_context directly (bypassing Celery broker)
            from backend.workers.intake_tasks import score_context

            # Build a minimal processed_result (output of process_document)
            processed_result = {
                "job_id": "job-high-001",
                "organization_id": "org-test-001",
                "location_id": "loc-test-001",
                "document_id": "doc-high-001",
                "raw_text": "Full invoice text with all fields present.",
                "file_name": "invoice_high.pdf",
                "raw_path": None,
                "acculynx_job_id": "job-high-001",
            }

            score_context(processed_result)

        mock_triage.delay.assert_called_once()
        mock_bounce.delay.assert_not_called()

        # Verify context_routing is propagated to triage
        triage_call_payload = mock_triage.delay.call_args[0][0]
        assert triage_call_payload["context_routing"] == "high"

    def test_medium_context_routes_to_triage_with_flag(
        self, scored_result_medium: dict[str, Any]
    ) -> None:
        """
        score 60 → routing='medium' → triage_document dispatched.
        The scored result must carry routing='medium' (needs_clarity downstream).
        bounce_back must NOT be called.
        """
        with (
            patch("backend.services.claude_service.ClaudeService") as mock_claude,
            patch("backend.workers.intake_tasks.triage_document") as mock_triage,
            patch("backend.workers.intake_tasks.bounce_back") as mock_bounce,
            patch("backend.workers.intake_tasks._update_job_context_score", new_callable=AsyncMock),
        ):
            mock_claude.score_context = AsyncMock(
                return_value={
                    "score": 60,
                    "routing": "medium",
                    "breakdown": {},
                    "document_summary": "Proposal with missing vendor details.",
                    "clarification_question": "Can you confirm the vendor name?",
                }
            )

            from backend.workers.intake_tasks import score_context

            processed_result = {
                "job_id": "job-medium-001",
                "organization_id": "org-test-001",
                "location_id": "loc-test-001",
                "document_id": "doc-medium-001",
                "raw_text": "Partial roofing proposal.",
                "file_name": "proposal_medium.pdf",
                "raw_path": None,
                "acculynx_job_id": "job-medium-001",
            }

            score_context(processed_result)

        mock_triage.delay.assert_called_once()
        mock_bounce.delay.assert_not_called()

        triage_call_payload = mock_triage.delay.call_args[0][0]
        assert triage_call_payload["routing"] == "medium"
        assert triage_call_payload["context_routing"] == "medium"

    def test_low_context_routes_to_bounce_back(
        self, scored_result_low: dict[str, Any]
    ) -> None:
        """
        score 25 → routing='low' → bounce_back dispatched.
        triage_document must NOT be called.
        """
        with (
            patch("backend.services.claude_service.ClaudeService") as mock_claude,
            patch("backend.workers.intake_tasks.triage_document") as mock_triage,
            patch("backend.workers.intake_tasks.bounce_back") as mock_bounce,
            patch("backend.workers.intake_tasks._update_job_context_score", new_callable=AsyncMock),
        ):
            mock_claude.score_context = AsyncMock(
                return_value={
                    "score": 25,
                    "routing": "low",
                    "breakdown": {},
                    "document_summary": "Fax cover sheet with no invoice content.",
                    "clarification_question": "Please resubmit the actual invoice.",
                }
            )

            from backend.workers.intake_tasks import score_context

            processed_result = {
                "job_id": "job-low-001",
                "organization_id": "org-test-001",
                "location_id": "loc-test-001",
                "document_id": "doc-low-001",
                "raw_text": "Fax cover sheet.",
                "file_name": "fax_low.pdf",
                "raw_path": None,
                "acculynx_job_id": "job-low-001",
            }

            score_context(processed_result)

        mock_bounce.delay.assert_called_once()
        mock_triage.delay.assert_not_called()

        bounce_call_payload = mock_bounce.delay.call_args[0][0]
        assert bounce_call_payload["routing"] == "low"
        assert bounce_call_payload["score"] == 25


# ══════════════════════════════════════════════════════════════════════════════
# Class 3 — TestFreemiumGate
# ══════════════════════════════════════════════════════════════════════════════


class TestFreemiumGate:
    """
    Integration tests for the freemium document quota check.

    CLAUDE.md: 'Before calling process_document.delay(), check document quota.
    If org["documents_processed"] >= org["max_documents"] → 402.'

    This check lives in both:
      - POST /api/v1/webhooks/acculynx (when x-workos-org-id header is present)
      - POST /api/v1/documents/upload (always — resolves org from WorkOS headers)
    """

    # ── Upload endpoint tests ─────────────────────────────────────────────────

    def test_upload_blocked_when_quota_reached(self, app_client: TestClient) -> None:
        """
        An org at its document quota (documents_processed >= max_documents) must
        receive HTTP 402 when POSTing to the manual upload endpoint.
        process_document.delay() must NOT be called.
        """
        quota_exhausted_org = {
            "organization_id": "org-quota-full",
            "workos_org_id": "wos-quota-full",
            "documents_processed": 500,
            "max_documents": 500,
        }

        with (
            patch(
                "backend.api.v1.documents.get_or_create_organization",
                new_callable=AsyncMock,
                return_value=quota_exhausted_org,
            ),
            patch("backend.api.v1.documents.process_document") as mock_task,
        ):
            fake_file = io.BytesIO(b"%PDF-1.4 fake pdf content")
            response = app_client.post(
                "/api/v1/documents/upload",
                data={"organization_id": "org-quota-full"},
                files={"file": ("invoice.pdf", fake_file, "application/pdf")},
                headers={
                    "x-workos-org-id": "wos-quota-full",
                    "x-workos-org-name": "Test Org",
                },
            )

        assert response.status_code == 402
        assert "quota" in response.json()["detail"].lower()
        mock_task.delay.assert_not_called()

    def test_upload_allowed_when_under_quota(self, app_client: TestClient) -> None:
        """
        An org under its document quota must receive HTTP 202 and have
        process_document.delay() called exactly once.
        """
        under_quota_org = {
            "organization_id": "org-under-quota",
            "workos_org_id": "wos-under-quota",
            "documents_processed": 42,
            "max_documents": 500,
        }

        mock_storage = MagicMock()
        mock_storage.upload = AsyncMock(return_value=MagicMock())
        mock_storage.remove = AsyncMock(return_value=None)

        mock_table = MagicMock()
        mock_table.insert.return_value.execute = AsyncMock(
            return_value=MagicMock(data=[{"job_id": "job-under-quota-001"}])
        )

        mock_supabase = MagicMock()
        mock_supabase.storage.from_.return_value = mock_storage
        mock_supabase.table.return_value = mock_table

        with (
            patch(
                "backend.api.v1.documents.get_or_create_organization",
                new_callable=AsyncMock,
                return_value=under_quota_org,
            ),
            patch(
                "backend.api.v1.documents.get_supabase_client",
                new_callable=AsyncMock,
                return_value=mock_supabase,
            ),
            patch("backend.api.v1.documents.process_document") as mock_task,
        ):
            fake_file = io.BytesIO(b"%PDF-1.4 fake pdf content for under quota test")
            response = app_client.post(
                "/api/v1/documents/upload",
                data={"organization_id": "org-under-quota"},
                files={"file": ("invoice.pdf", fake_file, "application/pdf")},
                headers={
                    "x-workos-org-id": "wos-under-quota",
                    "x-workos-org-name": "Test Org Under Quota",
                },
            )

        assert response.status_code == 202
        mock_task.delay.assert_called_once()
        task_payload = mock_task.delay.call_args[0][0]
        assert task_payload["organization_id"] == "org-under-quota"

    # ── Webhook endpoint freemium gate (WorkOS org header path) ──────────────

    def test_webhook_blocked_when_quota_reached_with_workos_header(
        self, app_client: TestClient, valid_webhook_payload: dict[str, Any]
    ) -> None:
        """
        When the webhook is called with an x-workos-org-id header (user session path),
        the freemium gate must fire and return 402 if the org is at quota.
        """
        quota_exhausted_org = {
            "organization_id": "org-wh-quota-full",
            "workos_org_id": "wos-wh-quota-full",
            "documents_processed": 500,
            "max_documents": 500,
        }

        with (
            patch(
                "backend.api.v1.webhooks.get_or_create_organization",
                new_callable=AsyncMock,
                return_value=quota_exhausted_org,
            ),
            patch("backend.api.v1.webhooks.process_document") as mock_task,
        ):
            response = _post_webhook(
                app_client,
                valid_webhook_payload,
                extra_headers={
                    "x-workos-org-id": "wos-wh-quota-full",
                    "x-workos-org-name": "Test Org",
                },
            )

        assert response.status_code == 402
        mock_task.delay.assert_not_called()

    def test_webhook_skips_quota_check_without_workos_header(
        self, app_client: TestClient, valid_webhook_payload: dict[str, Any]
    ) -> None:
        """
        When Hookdeck POSTs without an x-workos-org-id header (the standard path),
        the quota check is skipped and the task is dispatched unconditionally.
        """
        with (
            patch("backend.api.v1.webhooks.get_or_create_organization") as mock_org,
            patch("backend.api.v1.webhooks.process_document") as mock_task,
        ):
            response = _post_webhook(app_client, valid_webhook_payload)

        assert response.status_code == 200
        # org lookup must not happen when x-workos-org-id is absent
        mock_org.assert_not_called()
        mock_task.delay.assert_called_once()


# ══════════════════════════════════════════════════════════════════════════════
# Class 4 — TestLeakageGating
# ══════════════════════════════════════════════════════════════════════════════


class TestLeakageGating:
    """
    Integration tests for the detect_revenue_leakage task gating logic.

    CLAUDE.md rules:
      1. Query pricing_contracts by organization_id — if rows exist → Contract Mode
      2. Else check vendor_baseline_prices view — if ≥3 samples → Baseline Mode
      3. If neither → log leakage_skipped_reason='no_pricing_reference', skip,
         do NOT write to revenue_findings
    """

    def _make_extraction_result(self, context_routing: str = "high") -> dict[str, Any]:
        """Build a minimal extraction_result dict as produced by extract_struct."""
        return {
            "job_id": "job-leakage-001",
            "organization_id": "org-leakage-001",
            "location_id": "loc-leakage-001",
            "document_id": "doc-leakage-001",
            "triage_status": "confirmed",
            "context_routing": context_routing,
            "acculynx_job_id": "job-leakage-001",
            "extraction": {
                "vendor_name": {"value": "ABC Roofing Supply", "confidence": 0.98},
                "invoice_number": {"value": "INV-001", "confidence": 0.99},
                "invoice_date": {"value": "2026-03-29", "confidence": 0.97},
                "due_date": {"value": "2026-04-28", "confidence": 0.96},
                "subtotal": {"value": 1750.00, "confidence": 0.99},
                "tax": {"value": 140.00, "confidence": 0.98},
                "total": {"value": 1890.00, "confidence": 0.99},
                "invoice_id": "inv-uuid-001",
                "line_items": [
                    {
                        "description": {"value": "GAF Timberline HDZ Shingles", "confidence": 0.97},
                        "quantity": {"value": 50.0, "confidence": 0.99},
                        "unit_price": {"value": 35.00, "confidence": 0.98},
                        "amount": {"value": 1750.00, "confidence": 0.99},
                    }
                ],
            },
        }

    def test_leakage_skipped_with_no_pricing_reference(self) -> None:
        """
        When pricing_contracts is empty AND vendor_baseline_prices has <3 samples,
        detect_revenue_leakage must:
          - NOT call ClaudeService.detect_leakage()
          - NOT write to revenue_findings (i.e. _write_revenue_findings not called)
          - Log leakage_skipped_reason='no_pricing_reference' to the jobs table
            via _update_job_leakage_skipped()
        """
        extraction_result = self._make_extraction_result(context_routing="high")

        with (
            # No contracts, no baseline prices
            patch(
                "backend.workers.intake_tasks._query_pricing_contracts",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "backend.workers.intake_tasks._query_vendor_baseline_prices",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "backend.workers.intake_tasks._update_job_leakage_skipped",
                new_callable=AsyncMock,
            ) as mock_skip,
            patch(
                "backend.workers.intake_tasks._write_revenue_findings",
                new_callable=AsyncMock,
            ) as mock_write_findings,
            patch("backend.services.claude_service.ClaudeService") as mock_claude,
        ):
            from backend.workers.intake_tasks import detect_revenue_leakage

            result = detect_revenue_leakage(extraction_result)

        # Task must log the skip reason
        mock_skip.assert_called_once_with("job-leakage-001", "no_pricing_reference")

        # Task must NOT run leakage detection
        mock_claude.detect_leakage.assert_not_called()

        # Task must NOT write to revenue_findings
        mock_write_findings.assert_not_called()

        # Task returns a safe zero-finding result
        assert result["finding_count"] == 0
        assert result["total_leakage_amount"] == 0.0

    def test_leakage_runs_in_contract_mode(self) -> None:
        """
        When pricing_contracts rows exist for the organization_id,
        detect_revenue_leakage must:
          - Use Contract Mode (reference_mode='contract')
          - Call ClaudeService.detect_leakage() with the contracts as pricing_reference
          - Write findings to revenue_findings via _write_revenue_findings()
        """
        extraction_result = self._make_extraction_result(context_routing="high")

        pricing_contracts = [
            {
                "vendor_name": "ABC Roofing Supply",
                "description": "GAF Timberline HDZ Shingles",
                "contracted_unit_price": 30.00,  # cheaper than invoiced $35 → leakage
            }
        ]

        leakage_findings = {
            "findings": [
                {
                    "vendor_name": "ABC Roofing Supply",
                    "sku": "GAF-HDZ",
                    "invoiced_unit_price": 35.00,
                    "reference_unit_price": 30.00,
                    "quantity": 50.0,
                    "leakage_amount": 250.00,
                    "line_item_id": None,
                    "contract_id": None,
                }
            ]
        }

        with (
            patch(
                "backend.workers.intake_tasks._query_pricing_contracts",
                new_callable=AsyncMock,
                return_value=pricing_contracts,
            ),
            patch(
                "backend.workers.intake_tasks._query_vendor_baseline_prices",
                new_callable=AsyncMock,
                return_value=[],  # should not be reached in contract mode
            ),
            patch(
                "backend.workers.intake_tasks._update_job_leakage_skipped",
                new_callable=AsyncMock,
            ) as mock_skip,
            patch(
                "backend.workers.intake_tasks._write_revenue_findings",
                new_callable=AsyncMock,
            ) as mock_write_findings,
            patch("backend.services.claude_service.ClaudeService") as mock_claude,
        ):
            mock_claude.detect_leakage = AsyncMock(return_value=leakage_findings)

            from backend.workers.intake_tasks import detect_revenue_leakage

            result = detect_revenue_leakage(extraction_result)

        # Leakage must have run — skip log must NOT be called
        mock_skip.assert_not_called()

        # ClaudeService.detect_leakage must have been invoked
        mock_claude.detect_leakage.assert_called_once()
        call_kwargs = mock_claude.detect_leakage.call_args

        # Verify contract mode was passed as reference_mode
        # detect_leakage(line_items, pricing_reference, reference_mode)
        positional = call_kwargs[0]
        assert len(positional) == 3, "detect_leakage must be called with 3 positional args"
        assert positional[2] == "contract"

        # Findings must have been written to revenue_findings
        mock_write_findings.assert_called_once()
        write_call_kwargs = mock_write_findings.call_args[1]
        assert write_call_kwargs["reference_mode"] == "contract"
        assert write_call_kwargs["organization_id"] == "org-leakage-001"
        assert write_call_kwargs["job_id"] == "job-leakage-001"

        # Result totals must reflect the single $250 finding
        assert result["finding_count"] == 1
        assert result["total_leakage_amount"] == 250.00

    def test_leakage_runs_in_baseline_mode_when_no_contracts(self) -> None:
        """
        When pricing_contracts is empty but vendor_baseline_prices has ≥3 samples,
        detect_revenue_leakage must use Baseline Mode (reference_mode='baseline').
        """
        extraction_result = self._make_extraction_result(context_routing="high")

        baseline_rows = [
            {
                "vendor_name": "ABC Roofing Supply",
                "description": "GAF Timberline HDZ Shingles",
                "baseline_unit_price": 32.00,
                "sample_count": 5,
            }
        ]

        leakage_findings: dict[str, Any] = {"findings": []}  # No findings in baseline mode test

        with (
            patch(
                "backend.workers.intake_tasks._query_pricing_contracts",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "backend.workers.intake_tasks._query_vendor_baseline_prices",
                new_callable=AsyncMock,
                return_value=baseline_rows,
            ),
            patch(
                "backend.workers.intake_tasks._update_job_leakage_skipped",
                new_callable=AsyncMock,
            ) as mock_skip,
            patch(
                "backend.workers.intake_tasks._write_revenue_findings",
                new_callable=AsyncMock,
            ) as mock_write_findings,
            patch("backend.services.claude_service.ClaudeService") as mock_claude,
        ):
            mock_claude.detect_leakage = AsyncMock(return_value=leakage_findings)

            from backend.workers.intake_tasks import detect_revenue_leakage

            result = detect_revenue_leakage(extraction_result)

        # Skip must NOT be logged
        mock_skip.assert_not_called()

        # Claude must have been called
        mock_claude.detect_leakage.assert_called_once()
        positional = mock_claude.detect_leakage.call_args[0]
        assert positional[2] == "baseline"

        # Pricing reference must have been rewritten to use contracted_unit_price key
        pricing_ref_passed = positional[1]
        assert pricing_ref_passed[0]["contracted_unit_price"] == 32.00

        # No findings — write must not be called (findings list is empty)
        mock_write_findings.assert_not_called()

        assert result["finding_count"] == 0

    # ── DB-dependent test (skipped — requires live Supabase) ─────────────────

    @pytest.mark.skip(
        reason=(
            "Requires live Supabase with seeded pricing_contracts and "
            "vendor_baseline_prices data. Run via Supabase MCP: "
            "mcp__plugin_supabase_supabase__execute_sql to seed rows, "
            "then invoke detect_revenue_leakage with a real job_id."
        )
    )
    def test_leakage_end_to_end_with_real_db(self) -> None:
        """
        Full leakage detection against real Supabase data.
        Seed test data via mcp__plugin_supabase_supabase__execute_sql before running.
        """
        pass


# ══════════════════════════════════════════════════════════════════════════════
# Additional DB-dependent integration tests (skipped)
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.skip(
    reason=(
        "Requires live Supabase with seeded organizations, locations, and jobs rows. "
        "To run: use mcp__plugin_supabase_supabase__execute_sql to insert test orgs "
        "at quota, then POST to /api/v1/documents/upload. Verify 402 response code."
    )
)
class TestFreemiumGateWithRealDB:
    """
    End-to-end freemium gate tests against real Supabase.
    Skip in CI; run manually using Supabase MCP for integration validation.
    """

    def test_quota_check_reads_from_organizations_table(self) -> None:
        """
        Confirms the quota check reads documents_processed / max_documents from
        the Supabase organizations table — not from an in-memory cache or config.
        Seed: INSERT INTO organizations (organization_id, documents_processed, max_documents)
              VALUES ('org-e2e-test', 500, 500);
        """
        pass

    def test_documents_processed_increments_on_completion(self) -> None:
        """
        Confirms _update_job_status(job_id, 'complete') increments documents_processed.
        Seed: INSERT INTO organizations with documents_processed=0, then complete a job.
        """
        pass
