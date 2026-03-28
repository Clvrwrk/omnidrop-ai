"""
Temporal workflow input/output models.
Shared between the FastAPI backend (workflow starter) and Temporal workers (workflow executor).
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class JobStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class IntakeJobInput(BaseModel):
    """Input passed to the IntakeWorkflow when started from the webhook endpoint."""

    job_id: str = Field(..., description="AccuLynx job ID")
    event_type: str = Field(..., description="The triggering event type")
    raw_payload: str = Field(..., description="JSON-serialized raw webhook payload")
    received_at: datetime = Field(..., description="When the webhook was received")


class IntakeJobResult(BaseModel):
    """Output returned by the IntakeWorkflow upon completion."""

    job_id: str
    status: JobStatus
    documents_processed: int = 0
    error_message: str | None = None
    completed_at: datetime | None = None
