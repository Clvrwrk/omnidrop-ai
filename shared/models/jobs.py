"""
Job and document processing models.
Shared between FastAPI backend (task dispatcher) and Celery workers (task executor).
"""

from datetime import datetime
from enum import StrEnum
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class JobStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETE = "complete"
    FAILED = "failed"


class DocumentType(StrEnum):
    INVOICE = "invoice"
    PROPOSAL = "proposal"
    PO = "po"
    MSDS = "msds"
    MANUAL = "manual"
    WARRANTY = "warranty"
    UNKNOWN = "unknown"


class TriageCategory(StrEnum):
    STRUCTURED = "structured"
    UNSTRUCTURED = "unstructured"
    UNKNOWN = "unknown"


class TriageStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class CeleryJobPayload(BaseModel):
    """Payload dispatched from the webhook endpoint to the Celery process_document task."""

    job_id: str = Field(..., description="AccuLynx job ID")
    organization_id: str = Field(..., description="Organization ID — new tenant root")
    location_id: str | None = Field(default=None, description="Location ID — used to fetch API key from Supabase")
    event_type: str = Field(..., description="The triggering event type")
    document_id: str | None = Field(default=None, description="AccuLynx document ID")
    document_url: str | None = Field(default=None, description="Direct URL to fetch document bytes")
    raw_payload: str = Field(..., description="JSON-serialized raw webhook payload")
    received_at: datetime = Field(..., description="When the webhook was received")


class ProcessedDocumentResult(BaseModel):
    """Output of process_document task — input to triage_document."""

    job_id: str
    organization_id: str
    location_id: str | None = None
    document_id: str | None = None
    elements: list[dict[str, Any]] = Field(default_factory=list, description="Unstructured.io typed elements")
    raw_text: str = Field(default="", description="Plain text extracted from elements")
    file_name: str | None = None
    raw_path: str | None = None


class TriagedDocumentResult(BaseModel):
    """Output of triage_document task — input to extract_struct or chunk_and_embed."""

    job_id: str
    organization_id: str
    location_id: str | None = None
    document_id: str | None = None
    triage_category: TriageCategory
    document_type: DocumentType = DocumentType.UNKNOWN
    raw_text: str
    file_name: str | None = None
    raw_path: str | None = None


class ConfidenceField(BaseModel, Generic[T]):
    """A single extracted value with its confidence score."""

    value: T | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class LineItemConfidence(BaseModel):
    """Line item with per-field confidence scores — matches API contract."""

    description: ConfidenceField[str] = Field(default_factory=ConfidenceField)
    quantity: ConfidenceField[float] = Field(default_factory=ConfidenceField)
    unit_price: ConfidenceField[float] = Field(default_factory=ConfidenceField)
    amount: ConfidenceField[float] = Field(default_factory=ConfidenceField)


class InvoiceLineItem(BaseModel):
    """Single line item from a structured invoice extraction (flat, no confidence)."""

    description: str
    quantity: float
    unit_price: float
    amount: float


class InvoiceExtraction(BaseModel):
    """Structured extraction output — flat values, no confidence scores."""

    vendor_name: str | None = None
    invoice_number: str | None = None
    invoice_date: str | None = None
    due_date: str | None = None
    subtotal: float | None = None
    tax: float | None = None
    total: float | None = None
    line_items: list[InvoiceLineItem] = Field(default_factory=list)
    notes: str | None = None


class ExtractionWithConfidence(BaseModel):
    """
    Invoice extraction with per-field confidence — matches API contract shape.
    Each field is {"value": ..., "confidence": float}.
    This is the shape returned by ClaudeService and stored in invoices.extraction_meta.
    """

    vendor_name: ConfidenceField[str] = Field(default_factory=ConfidenceField)
    invoice_number: ConfidenceField[str] = Field(default_factory=ConfidenceField)
    invoice_date: ConfidenceField[str] = Field(default_factory=ConfidenceField)
    due_date: ConfidenceField[str] = Field(default_factory=ConfidenceField)
    subtotal: ConfidenceField[float] = Field(default_factory=ConfidenceField)
    tax: ConfidenceField[float] = Field(default_factory=ConfidenceField)
    total: ConfidenceField[float] = Field(default_factory=ConfidenceField)
    notes: ConfidenceField[str] = Field(default_factory=ConfidenceField)
    line_items: list[LineItemConfidence] = Field(default_factory=list)
