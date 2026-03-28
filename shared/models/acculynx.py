"""
AccuLynx webhook payload models.
Used by the FastAPI webhook endpoint and Celery task inputs.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AccuLynxJobEvent(BaseModel):
    """Represents a single event within an AccuLynx webhook payload."""

    event_type: str = Field(..., description="e.g. 'job.created', 'document.uploaded'")
    job_id: str = Field(..., description="AccuLynx job ID")
    location_id: str = Field(..., description="AccuLynx location ID — maps to Supabase locations table")
    timestamp: datetime = Field(..., description="When the event occurred")
    document_id: str | None = Field(default=None, description="AccuLynx document ID, if applicable")
    document_url: str | None = Field(default=None, description="Direct URL to fetch document bytes")
    data: dict[str, Any] = Field(default_factory=dict, description="Event-specific payload")


class AccuLynxWebhookPayload(BaseModel):
    """
    Top-level AccuLynx webhook payload as delivered by Hookdeck.
    Hookdeck re-signs and forwards the original AccuLynx event.
    """

    event: AccuLynxJobEvent
    version: str = Field(default="1.0", description="Webhook schema version")
