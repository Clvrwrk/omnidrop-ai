"""
OmniDrop AI — Intake Workflow

Stateful Temporal workflow that orchestrates AI document extraction
and AccuLynx data synchronization for a single webhook event.

This workflow is started by the FastAPI webhook endpoint after it
acknowledges the webhook with a 204 response.
"""

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from shared.models.jobs import IntakeJobInput, IntakeJobResult, JobStatus
    from workers.activities.document_activities import (
        extract_documents,
        sync_to_database,
    )


@workflow.defn
class IntakeWorkflow:
    """
    Orchestrates the full intake pipeline for a single AccuLynx event.

    Sequence:
      1. extract_documents — fetch and AI-extract documents from AccuLynx
      2. sync_to_database — write extracted data to Supabase

    TODO: Add error handling, compensation logic, and notification activities.
    """

    @workflow.run
    async def run(self, job_input: IntakeJobInput) -> IntakeJobResult:
        retry_policy = RetryPolicy(
            maximum_attempts=3,
            initial_interval=timedelta(seconds=5),
            backoff_coefficient=2.0,
            maximum_interval=timedelta(minutes=2),
        )

        # Step 1: Extract documents
        # TODO: implement extract_documents activity
        # extraction_result = await workflow.execute_activity(
        #     extract_documents,
        #     job_input,
        #     start_to_close_timeout=timedelta(minutes=5),
        #     retry_policy=retry_policy,
        # )

        # Step 2: Sync to database
        # TODO: implement sync_to_database activity
        # await workflow.execute_activity(
        #     sync_to_database,
        #     extraction_result,
        #     start_to_close_timeout=timedelta(minutes=2),
        #     retry_policy=retry_policy,
        # )

        return IntakeJobResult(
            job_id=job_input.job_id,
            status=JobStatus.COMPLETED,
            documents_processed=0,
        )
