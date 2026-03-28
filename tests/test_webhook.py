"""
OmniDrop AI — Integration tests for the webhook endpoint + Celery dispatch.

Validates the 4-step webhook contract (CLAUDE.md):
  1. Verify Hookdeck HMAC-SHA256 signature → 401 if invalid
  2. Validate payload shape with Pydantic → 422 if malformed
  3. Call process_document.delay(job_payload) → dispatch to Celery
  4. Return 200 OK immediately

Also validates that the endpoint does NOT:
  - Call Unstructured.io, Claude, or Supabase
  - Perform any database writes
  - Make outbound HTTP requests
"""

import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


def _make_hookdeck_signature(body: bytes, secret: str) -> str:
    """Produce a valid Hookdeck HMAC-SHA256 signature header value."""
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


TEST_SIGNING_SECRET = "test-hookdeck-secret-key"


@pytest.fixture
def client():
    """TestClient with settings patched so the app can init without real env vars."""
    with patch("backend.core.config.get_settings") as mock_settings:
        mock_s = mock_settings.return_value
        mock_s.app_env = "local"
        mock_s.cors_origins = ["http://localhost:3000"]
        mock_s.hookdeck_signing_secret = TEST_SIGNING_SECRET
        mock_s.sentry_python_dsn = None
        mock_s.sentry_traces_sample_rate = 0.0

        # Patch Sentry and logging config to no-op
        with patch("backend.core.sentry.configure_sentry"), \
             patch("backend.core.logging.configure_logging"):
            from backend.api.main import app
            yield TestClient(app)


@pytest.fixture
def valid_payload() -> dict[str, Any]:
    return {
        "event": {
            "event_type": "document.uploaded",
            "job_id": "job-abc-123",
            "location_id": "loc-def-456",
            "timestamp": "2026-03-28T12:00:00Z",
            "document_id": "doc-ghi-789",
            "document_url": "https://api.acculynx.com/docs/ghi-789",
            "data": {},
        },
        "version": "1.0",
    }


def _post_webhook(client: TestClient, payload: dict, secret: str = TEST_SIGNING_SECRET, sig_override: str | None = None):
    """Helper to POST to the webhook endpoint with proper HMAC signature."""
    body = json.dumps(payload).encode()
    sig = sig_override or _make_hookdeck_signature(body, secret)
    return client.post(
        "/api/v1/webhooks/acculynx",
        content=body,
        headers={
            "x-hookdeck-signature": sig,
            "content-type": "application/json",
        },
    )


# ─── Step 1: HMAC signature verification ─────────────────────────────────────


class TestWebhookSignatureVerification:
    def test_returns_401_when_signature_header_missing(self, client: TestClient, valid_payload: dict):
        response = client.post(
            "/api/v1/webhooks/acculynx",
            json=valid_payload,
            # No x-hookdeck-signature header
        )
        assert response.status_code == 401

    def test_returns_401_with_invalid_signature(self, client: TestClient, valid_payload: dict):
        response = _post_webhook(client, valid_payload, sig_override="sha256=0000invalidhex0000")
        assert response.status_code == 401

    def test_returns_401_with_wrong_secret(self, client: TestClient, valid_payload: dict):
        response = _post_webhook(client, valid_payload, secret="wrong-secret-key")
        assert response.status_code == 401


# ─── Step 2: Pydantic payload validation ─────────────────────────────────────


class TestWebhookPayloadValidation:
    def test_returns_422_with_empty_body(self, client: TestClient):
        body = b"{}"
        sig = _make_hookdeck_signature(body, TEST_SIGNING_SECRET)
        response = client.post(
            "/api/v1/webhooks/acculynx",
            content=body,
            headers={"x-hookdeck-signature": sig, "content-type": "application/json"},
        )
        assert response.status_code == 422

    def test_returns_422_with_missing_required_fields(self, client: TestClient):
        bad_payload = {"event": {"event_type": "test"}}  # Missing job_id, location_id, timestamp
        body = json.dumps(bad_payload).encode()
        sig = _make_hookdeck_signature(body, TEST_SIGNING_SECRET)
        response = client.post(
            "/api/v1/webhooks/acculynx",
            content=body,
            headers={"x-hookdeck-signature": sig, "content-type": "application/json"},
        )
        assert response.status_code == 422

    def test_returns_422_with_invalid_json(self, client: TestClient):
        body = b"not json at all"
        sig = _make_hookdeck_signature(body, TEST_SIGNING_SECRET)
        response = client.post(
            "/api/v1/webhooks/acculynx",
            content=body,
            headers={"x-hookdeck-signature": sig, "content-type": "application/json"},
        )
        assert response.status_code == 422


# ─── Steps 3 & 4: Celery dispatch + 200 OK ───────────────────────────────────


class TestWebhookCeleryDispatch:
    def test_returns_200_and_dispatches_celery_task(self, client: TestClient, valid_payload: dict):
        with patch("backend.api.v1.webhooks.process_document") as mock_task:
            response = _post_webhook(client, valid_payload)

        assert response.status_code == 200
        mock_task.delay.assert_called_once()

        # Verify the payload passed to Celery contains expected fields
        call_args = mock_task.delay.call_args[0][0]
        assert call_args["job_id"] == "job-abc-123"
        assert call_args["location_id"] == "loc-def-456"
        assert call_args["event_type"] == "document.uploaded"
        assert call_args["document_id"] == "doc-ghi-789"

    def test_payload_includes_received_at_timestamp(self, client: TestClient, valid_payload: dict):
        with patch("backend.api.v1.webhooks.process_document") as mock_task:
            _post_webhook(client, valid_payload)

        call_args = mock_task.delay.call_args[0][0]
        assert "received_at" in call_args

    def test_payload_includes_raw_payload(self, client: TestClient, valid_payload: dict):
        with patch("backend.api.v1.webhooks.process_document") as mock_task:
            _post_webhook(client, valid_payload)

        call_args = mock_task.delay.call_args[0][0]
        assert "raw_payload" in call_args
        # raw_payload should be a JSON string
        parsed = json.loads(call_args["raw_payload"])
        assert parsed["event"]["job_id"] == "job-abc-123"


# ─── Negative: endpoint must not touch DB, AI, or Unstructured ────────────────


class TestWebhookIsolation:
    """
    CLAUDE.md: 'This endpoint NEVER calls Unstructured.io, Claude, or Supabase. No exceptions.'
    """

    def test_does_not_call_supabase(self, client: TestClient, valid_payload: dict):
        with patch("backend.api.v1.webhooks.process_document"):
            with patch("backend.services.supabase_client.get_supabase_client") as mock_sb:
                _post_webhook(client, valid_payload)
        mock_sb.assert_not_called()

    def test_does_not_call_claude(self, client: TestClient, valid_payload: dict):
        with patch("backend.api.v1.webhooks.process_document"):
            with patch("backend.services.claude_service._get_client") as mock_claude:
                _post_webhook(client, valid_payload)
        mock_claude.assert_not_called()

    def test_does_not_call_unstructured(self, client: TestClient, valid_payload: dict):
        with patch("backend.api.v1.webhooks.process_document"):
            with patch("backend.services.unstructured_service._get_client") as mock_unst:
                _post_webhook(client, valid_payload)
        mock_unst.assert_not_called()


# ─── Celery task: rate limit compliance ───────────────────────────────────────


class TestCeleryRateLimits:
    """Verify that AccuLynx-calling tasks have proper rate limits."""

    def test_process_document_has_rate_limit(self):
        from backend.workers.intake_tasks import process_document
        assert process_document.rate_limit == "10/s"

    def test_triage_document_no_acculynx_rate_limit(self):
        """Triage only calls Claude, not AccuLynx — should not have a rate limit."""
        from backend.workers.intake_tasks import triage_document
        assert triage_document.rate_limit is None

    def test_extract_struct_no_acculynx_rate_limit(self):
        from backend.workers.intake_tasks import extract_struct
        assert extract_struct.rate_limit is None

    def test_chunk_and_embed_no_acculynx_rate_limit(self):
        from backend.workers.intake_tasks import chunk_and_embed
        assert chunk_and_embed.rate_limit is None


# ─── QA: No superseded imports in webhook path ───────────────────────────────


class TestNoSupersededImports:
    def test_webhook_module_does_not_import_temporal(self):
        import inspect
        from backend.api.v1 import webhooks
        source = inspect.getsource(webhooks)
        assert "temporal" not in source.lower(), (
            "webhooks.py imports temporal — this is superseded per CLAUDE.md"
        )

    def test_intake_tasks_does_not_import_temporal(self):
        import inspect
        from backend.workers import intake_tasks
        source = inspect.getsource(intake_tasks)
        assert "temporal" not in source.lower(), (
            "intake_tasks.py imports temporal — this is superseded per CLAUDE.md"
        )
