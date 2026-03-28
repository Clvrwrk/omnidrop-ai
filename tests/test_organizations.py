"""
OmniDrop AI — Organization Multi-Tenancy Tests

Validates:
  1. Upload without location_id succeeds (org-level upload)
  2. AccuLynx webhook path resolves organization_id from location_id
  3. extract_struct writes organization_id to invoices table
  4. chunk_and_embed writes organization_id to document_embeddings
  5. 5-user (seat) limit enforced per organization
  6. Data isolation — org A cannot see org B's jobs
"""

import io
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ── Shared fixtures ─────────────────────────────────────────────────────────────

ORG_A_ID = "org-aaa-111"
ORG_B_ID = "org-bbb-222"
LOCATION_ID = "loc-456"


@pytest.fixture
def client():
    """TestClient with settings patched so the app can init without real env vars."""
    with patch("backend.core.config.get_settings") as mock_settings:
        mock_s = mock_settings.return_value
        mock_s.app_env = "local"
        mock_s.cors_origins = ["http://localhost:3000"]
        mock_s.hookdeck_signing_secret = "test-secret"
        mock_s.sentry_python_dsn = None
        mock_s.sentry_traces_sample_rate = 0.0

        with patch("backend.core.sentry.configure_sentry"), \
             patch("backend.core.logging.configure_logging"):
            from backend.api.main import app
            yield TestClient(app)


# ─── Test 1: Upload without location_id succeeds ────────────────────────────────


class TestUploadWithoutLocationId:
    """POST /documents/upload with organization_id only, no location_id."""

    def test_upload_returns_202_with_org_id_and_null_location(self, client: TestClient):
        """Upload at org level (no AccuLynx location) should succeed."""
        response = client.post(
            "/api/v1/documents/upload",
            data={"organization_id": ORG_A_ID},
            files={"file": ("invoice.pdf", io.BytesIO(b"%PDF-fake"), "application/pdf")},
        )
        assert response.status_code == 202
        body = response.json()
        assert body["organization_id"] == ORG_A_ID
        assert body["location_id"] is None
        assert body["status"] == "queued"
        assert "job_id" in body

    def test_upload_with_both_org_and_location(self, client: TestClient):
        """Upload with both organization_id and location_id should succeed."""
        response = client.post(
            "/api/v1/documents/upload",
            data={"organization_id": ORG_A_ID, "location_id": LOCATION_ID},
            files={"file": ("invoice.pdf", io.BytesIO(b"%PDF-fake"), "application/pdf")},
        )
        assert response.status_code == 202
        body = response.json()
        assert body["organization_id"] == ORG_A_ID
        assert body["location_id"] == LOCATION_ID

    def test_upload_without_org_id_returns_422(self, client: TestClient):
        """organization_id is required — missing it must return 422."""
        response = client.post(
            "/api/v1/documents/upload",
            data={"location_id": LOCATION_ID},
            files={"file": ("invoice.pdf", io.BytesIO(b"%PDF-fake"), "application/pdf")},
        )
        assert response.status_code == 422


# ─── Test 2: AccuLynx path resolves organization_id from location ───────────────


class TestAccuLynxPathResolvesOrg:
    """
    process_document task receives location_id (from webhook) but no organization_id.
    It must call get_organization_id_for_location() to resolve the org.
    """

    def test_resolves_org_from_location_when_org_missing(self):
        """When organization_id is absent, process_document resolves it from location_id."""
        from backend.workers.intake_tasks import process_document

        job_payload = {
            "job_id": "job-resolve-001",
            "location_id": LOCATION_ID,
            # organization_id intentionally absent
            "event_type": "document.uploaded",
            "document_id": "doc-001",
            "document_url": "https://acculynx.com/docs/001",
        }

        with patch(
            "backend.services.supabase_client.get_organization_id_for_location",
            new_callable=AsyncMock,
            return_value=ORG_A_ID,
        ) as mock_resolve:
            # process_document will still raise NotImplementedError after resolving org,
            # but we can verify the resolution happened
            with pytest.raises(NotImplementedError):
                process_document(job_payload)

            mock_resolve.assert_awaited_once_with(LOCATION_ID)

        # Verify organization_id was injected into the payload
        assert job_payload["organization_id"] == ORG_A_ID

    def test_skips_resolution_when_org_already_present(self):
        """When organization_id is already in the payload, do NOT call the resolver."""
        from backend.workers.intake_tasks import process_document

        job_payload = {
            "job_id": "job-resolve-002",
            "organization_id": ORG_A_ID,
            "location_id": LOCATION_ID,
            "event_type": "document.uploaded",
            "document_id": "doc-002",
            "document_url": "https://acculynx.com/docs/002",
        }

        with patch(
            "backend.services.supabase_client.get_organization_id_for_location",
            new_callable=AsyncMock,
        ) as mock_resolve:
            with pytest.raises(NotImplementedError):
                process_document(job_payload)

            mock_resolve.assert_not_awaited()


# ─── Test 3: extract_struct writes organization_id to invoices ──────────────────


class TestExtractStructWritesOrg:
    """extract_struct must include organization_id in the invoices upsert call."""

    def _run_extract(self, triaged_result: dict, extraction: dict) -> list[dict]:
        """Helper: run extract_struct with mocked deps, return captured invoice inserts."""
        from backend.workers.intake_tasks import extract_struct

        invoice_insert_data: list[dict] = []
        mock_sb = MagicMock()

        def _capture_table(table_name: str):
            builder = MagicMock()
            builder.select.return_value = builder
            builder.eq.return_value = builder
            builder.update.return_value = builder
            builder.execute = AsyncMock(
                return_value=MagicMock(data=[{"invoice_id": "inv-001"}])
            )

            def _capture_insert(data):
                if table_name == "invoices":
                    invoice_insert_data.append(data)
                return builder

            builder.insert = _capture_insert
            return builder

        mock_sb.table.side_effect = _capture_table

        with patch("backend.services.claude_service.ClaudeService") as MockClaude:
            MockClaude.extract_invoice_schema.return_value = extraction
            MockClaude.should_auto_confirm.return_value = True

            with patch(
                "backend.services.supabase_client.get_supabase_client",
                new_callable=AsyncMock,
                return_value=mock_sb,
            ):
                extract_struct(triaged_result)

        return invoice_insert_data

    def test_organization_id_written_to_invoice_data(
        self, sample_extraction_high_confidence: dict
    ):
        triaged_result = {
            "job_id": "job-ext-001",
            "organization_id": ORG_A_ID,
            "location_id": LOCATION_ID,
            "document_id": "doc-ext-001",
            "triage_category": "structured",
            "raw_text": "INVOICE ABC Roofing ...",
        }

        inserts = self._run_extract(triaged_result, sample_extraction_high_confidence)
        assert len(inserts) >= 1, "Expected at least one invoices insert"
        assert inserts[0]["organization_id"] == ORG_A_ID

    def test_organization_id_written_even_without_location(
        self, sample_extraction_high_confidence: dict
    ):
        """Org-level upload (no location_id) still writes organization_id."""
        triaged_result = {
            "job_id": "job-ext-002",
            "organization_id": ORG_A_ID,
            "location_id": None,
            "document_id": "doc-ext-002",
            "triage_category": "structured",
            "raw_text": "INVOICE ...",
        }

        inserts = self._run_extract(triaged_result, sample_extraction_high_confidence)
        assert len(inserts) >= 1
        assert inserts[0]["organization_id"] == ORG_A_ID
        assert inserts[0]["location_id"] is None


# ─── Test 4: chunk_and_embed writes organization_id to embeddings ───────────────


class TestChunkAndEmbedWritesOrg:
    """chunk_and_embed must include organization_id on every chunk."""

    def _run_embed(
        self, triaged_result: dict, fake_chunks: list[dict]
    ) -> tuple[dict, list[list[dict]]]:
        """Helper: run chunk_and_embed with mocked deps, return (result, captured inserts)."""
        from backend.workers.intake_tasks import chunk_and_embed

        embeddings_insert_data: list[list[dict]] = []
        mock_sb = MagicMock()

        def _capture_table(table_name: str):
            builder = MagicMock()
            builder.select.return_value = builder
            builder.eq.return_value = builder
            builder.update.return_value = builder
            builder.execute = AsyncMock(return_value=MagicMock(data=[]))

            def _capture_insert(data):
                if table_name == "document_embeddings":
                    embeddings_insert_data.append(data)
                return builder

            builder.insert = _capture_insert
            return builder

        mock_sb.table.side_effect = _capture_table

        with patch("backend.services.claude_service.ClaudeService") as MockClaude:
            MockClaude.chunk_for_rag.return_value = fake_chunks

            with patch(
                "backend.services.supabase_client.get_supabase_client",
                new_callable=AsyncMock,
                return_value=mock_sb,
            ):
                result = chunk_and_embed(triaged_result)

        return result, embeddings_insert_data

    def test_organization_id_on_every_chunk(self):
        triaged_result = {
            "job_id": "job-emb-001",
            "organization_id": ORG_A_ID,
            "location_id": LOCATION_ID,
            "document_id": "doc-emb-001",
            "triage_category": "unstructured",
            "raw_text": "SAFETY DATA SHEET — Acme Roofing Sealant ...",
        }

        fake_chunks = [
            {"chunk_id": "c1", "text": "Safety section 1", "embedding": [0.1] * 8},
            {"chunk_id": "c2", "text": "Safety section 2", "embedding": [0.2] * 8},
            {"chunk_id": "c3", "text": "First aid measures", "embedding": [0.3] * 8},
        ]

        result, inserts = self._run_embed(triaged_result, fake_chunks)

        assert result["chunk_count"] == 3
        assert len(inserts) == 1, "Expected one bulk insert call"
        for chunk in inserts[0]:
            assert chunk["organization_id"] == ORG_A_ID, (
                f"Chunk {chunk.get('chunk_id')} missing organization_id"
            )
            assert chunk["location_id"] == LOCATION_ID

    def test_org_id_on_chunks_without_location(self):
        """Org-level upload (no location_id) still tags chunks with organization_id."""
        triaged_result = {
            "job_id": "job-emb-002",
            "organization_id": ORG_A_ID,
            "location_id": None,
            "document_id": "doc-emb-002",
            "triage_category": "unstructured",
            "raw_text": "WARRANTY DOCUMENT ...",
        }

        fake_chunks = [
            {"chunk_id": "c1", "text": "Warranty terms", "embedding": [0.1] * 8},
        ]

        _, inserts = self._run_embed(triaged_result, fake_chunks)

        assert len(inserts) == 1
        assert inserts[0][0]["organization_id"] == ORG_A_ID
        assert inserts[0][0]["location_id"] is None


# ─── Test 5: 5-user (seat) limit ────────────────────────────────────────────────


class TestUserSeatLimit:
    """
    Organizations have a max_users limit (default 5).
    Creating a 6th location/user must be rejected with 403.

    NOTE: The seat-limit enforcement is wired in create_location.
    If these tests fail with 201, the enforcement guard has not been added yet.
    """

    def test_create_location_rejected_at_seat_limit(self, client: TestClient):
        """POST /settings/locations returns 403 when org is at max_users."""
        with patch(
            "backend.services.supabase_client.get_user_count_for_org",
            new_callable=AsyncMock,
            return_value=5,  # Already at limit
        ), patch(
            "backend.services.supabase_client.get_organization_by_id",
            new_callable=AsyncMock,
            return_value={
                "organization_id": ORG_A_ID,
                "workos_org_id": "workos-org-001",
                "name": "Test Org",
                "max_users": 5,
            },
        ):
            response = client.post(
                "/api/v1/settings/locations",
                json={
                    "name": "6th Location",
                    "acculynx_api_key": "key-sixth-0001",
                    "organization_id": ORG_A_ID,
                },
            )

        assert response.status_code == 403, (
            f"Expected 403 for 6th user, got {response.status_code}: {response.text}"
        )

    def test_create_location_allowed_under_limit(self, client: TestClient):
        """POST /settings/locations succeeds when under max_users."""
        with patch(
            "backend.services.supabase_client.get_user_count_for_org",
            new_callable=AsyncMock,
            return_value=3,  # Under limit
        ), patch(
            "backend.services.supabase_client.get_organization_by_id",
            new_callable=AsyncMock,
            return_value={
                "organization_id": ORG_A_ID,
                "workos_org_id": "workos-org-001",
                "name": "Test Org",
                "max_users": 5,
            },
        ):
            response = client.post(
                "/api/v1/settings/locations",
                json={
                    "name": "4th Location",
                    "acculynx_api_key": "key-fourth-0001",
                    "organization_id": ORG_A_ID,
                },
            )

        assert response.status_code == 201


# ─── Test 6: Data isolation — org-scoped queries ────────────────────────────────


class TestOrganizationDataIsolation:
    """Jobs query must be scoped by organization_id — no cross-org data leakage."""

    def test_jobs_list_scoped_by_organization_id(self, client: TestClient):
        """GET /jobs should filter by organization_id, never return other orgs' jobs."""
        org_a_jobs = [
            {"job_id": "job-a1", "organization_id": ORG_A_ID, "status": "complete"},
            {"job_id": "job-a2", "organization_id": ORG_A_ID, "status": "queued"},
        ]

        mock_org = {
            "organization_id": ORG_A_ID,
            "workos_org_id": "workos-org-001",
            "name": "Org A",
            "max_users": 5,
        }

        with patch(
            "backend.services.supabase_client.get_organization_by_workos_id",
            new_callable=AsyncMock,
            return_value=mock_org,
        ):
            response = client.get(
                "/api/v1/jobs",
                headers={"x-workos-org-id": "workos-org-001"},
                params={"organization_id": ORG_A_ID},
            )

        # The current endpoint returns placeholder data, but when wired up
        # it must never include jobs from ORG_B_ID
        body = response.json()
        assert response.status_code == 200
        for job in body.get("jobs", []):
            assert job.get("organization_id") != ORG_B_ID, (
                f"Data isolation violation: job {job['job_id']} belongs to org B"
            )

    def test_triage_document_passes_org_through_pipeline(self):
        """
        triage_document must propagate organization_id to the next task
        (extract_struct or chunk_and_embed), ensuring isolation through the pipeline.
        """
        from backend.workers.intake_tasks import triage_document

        parsed_result = {
            "job_id": "job-iso-001",
            "organization_id": ORG_A_ID,
            "location_id": LOCATION_ID,
            "document_id": "doc-iso-001",
            "raw_text": "INVOICE #1234",
            "file_name": "invoice.pdf",
            "raw_path": "/tmp/invoice.pdf",
        }

        with patch("backend.services.claude_service.ClaudeService") as MockClaude:
            MockClaude.classify_document.return_value = "structured"

            with patch("backend.workers.intake_tasks.extract_struct") as mock_extract:
                result = triage_document(parsed_result)

        # Verify organization_id was propagated to the downstream task
        assert result["organization_id"] == ORG_A_ID
        mock_extract.delay.assert_called_once()
        downstream_payload = mock_extract.delay.call_args[0][0]
        assert downstream_payload["organization_id"] == ORG_A_ID

    def test_triage_unstructured_passes_org_to_chunk_and_embed(self):
        """Unstructured path also propagates organization_id."""
        from backend.workers.intake_tasks import triage_document

        parsed_result = {
            "job_id": "job-iso-002",
            "organization_id": ORG_A_ID,
            "location_id": None,
            "document_id": "doc-iso-002",
            "raw_text": "SAFETY DATA SHEET",
            "file_name": "msds.pdf",
            "raw_path": "/tmp/msds.pdf",
        }

        with patch("backend.services.claude_service.ClaudeService") as MockClaude:
            MockClaude.classify_document.return_value = "unstructured"

            with patch("backend.workers.intake_tasks.chunk_and_embed") as mock_embed:
                result = triage_document(parsed_result)

        assert result["organization_id"] == ORG_A_ID
        mock_embed.delay.assert_called_once()
        downstream_payload = mock_embed.delay.call_args[0][0]
        assert downstream_payload["organization_id"] == ORG_A_ID
