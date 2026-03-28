"""
Tests for the AccuLynx webhook endpoint.

TODO: Implement these tests once the HMAC signature verification is complete.
"""

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app

client = TestClient(app)


def test_webhook_missing_signature_returns_401() -> None:
    """Requests without X-AccuLynx-Signature must be rejected."""
    # TODO: implement
    pytest.skip("Not yet implemented — requires HMAC verification stub completion")


def test_webhook_invalid_signature_returns_401() -> None:
    """Requests with a bad signature must be rejected."""
    # TODO: implement
    pytest.skip("Not yet implemented")


def test_webhook_valid_payload_returns_204() -> None:
    """Valid signed requests must return 204 with no body."""
    # TODO: implement
    pytest.skip("Not yet implemented")


def test_webhook_invalid_payload_returns_422() -> None:
    """Malformed payloads must return 422 before reaching Temporal."""
    # TODO: implement
    pytest.skip("Not yet implemented")
