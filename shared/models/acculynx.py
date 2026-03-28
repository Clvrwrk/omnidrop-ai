"""
AccuLynx webhook payload models.
These are used by the FastAPI webhook endpoint AND Temporal workflow inputs.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AccuLynxJobEvent(BaseModel):
    """Represents a single event within an AccuLynx webhook payload."""

    event_type: str = Field(..., description="e.g. 'job.created', 'document.uploaded'")
    job_id: str = Field(..., description="AccuLynx job ID")
    timestamp: datetime = Field(..., description="When the event occurred")
    data: dict[str, Any] = Field(default_factory=dict, description="Event-specific payload")


class AccuLynxWebhookPayload(BaseModel):
    """
    Top-level AccuLynx webhook payload.
    TODO: Expand fields once AccuLynx webhook documentation is confirmed.
    """

    event: AccuLynxJobEvent
    version: str = Field(default="1.0", description="Webhook schema version")
