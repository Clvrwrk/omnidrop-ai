// ─── Jobs ─────────────────────────────────────────────────────────────────────

export type JobStatus = "queued" | "processing" | "complete" | "failed";

export type DocumentType =
  | "invoice"
  | "proposal"
  | "po"
  | "msds"
  | "manual"
  | "warranty"
  | "unknown"
  | null;

export interface Job {
  job_id: string;
  location_id: string;
  location_name: string;
  status: JobStatus;
  document_type: DocumentType;
  file_name: string | null;
  created_at: string;
  completed_at: string | null;
  error_message: string | null;
}

export interface JobDetail extends Job {
  raw_path: string | null;
  document_id: string | null;
}

export interface JobListResponse {
  jobs: Job[];
  total: number;
  offset: number;
  limit: number;
}

export interface UploadResponse {
  job_id: string;
  status: "queued";
  created_at: string;
}

// ─── Events ───────────────────────────────────────────────────────────────────

export type EventStatus = "accepted" | "rejected" | "pending";

export interface IntakeEvent {
  event_id: string;
  job_id: string | null;
  source: "acculynx";
  event_type: string;
  received_at: string;
  status: EventStatus;
}

export interface EventListResponse {
  events: IntakeEvent[];
  total: number;
}

// ─── Analytics ────────────────────────────────────────────────────────────────

export type AnalyticsPeriod = "7d" | "30d" | "90d" | "ytd";

export interface KpiMetric {
  value: number;
  delta_pct: number;
}

export interface KpiResponse {
  period: AnalyticsPeriod;
  volume_processed: KpiMetric;
  accuracy_rate: KpiMetric;
  avg_processing_time_seconds: KpiMetric;
  total_invoice_value: KpiMetric;
  pending_triage_count: number;
}

export interface VendorSpendItem {
  name: string;
  value: number;
  count: number;
}

export interface TrendPoint {
  date: string;
  total: number;
}

export interface VendorSpendResponse {
  period: AnalyticsPeriod;
  group_by: "vendor" | "job" | "month";
  items: VendorSpendItem[];
  trend: TrendPoint[];
}

// ─── Search ───────────────────────────────────────────────────────────────────

export interface SearchRequest {
  query: string;
  location_id?: string | null;
  limit?: number;
}

export interface SearchResult {
  document_id: string;
  job_id: string;
  file_name: string;
  chunk_text: string;
  similarity_score: number;
  document_type: string;
  location_name: string;
  created_at: string;
}

export interface SearchResponse {
  query: string;
  results: SearchResult[];
}

// ─── HITL Triage ──────────────────────────────────────────────────────────────

export type TriageStatus = "pending" | "confirmed" | "rejected";
export type TriageAction = "confirm" | "reject" | "correct";

export interface TriageQueueItem {
  document_id: string;
  job_id: string;
  file_name: string;
  document_type: "invoice" | "proposal" | "po";
  min_confidence_score: number;
  low_confidence_field_count: number;
  created_at: string;
  location_name: string;
}

export interface TriageQueueResponse {
  items: TriageQueueItem[];
  total: number;
}

export interface ConfidenceField<T> {
  value: T | null;
  confidence: number;
}

export interface LineItemConfidence {
  description: ConfidenceField<string>;
  quantity: ConfidenceField<number>;
  unit_price: ConfidenceField<number>;
  amount: ConfidenceField<number>;
}

export interface ExtractionWithConfidence {
  vendor_name: ConfidenceField<string>;
  invoice_number: ConfidenceField<string>;
  invoice_date: ConfidenceField<string>;
  due_date: ConfidenceField<string>;
  subtotal: ConfidenceField<number>;
  tax: ConfidenceField<number>;
  total: ConfidenceField<number>;
  notes: ConfidenceField<string>;
  line_items: LineItemConfidence[];
}

export interface TriageDetail {
  document_id: string;
  job_id: string;
  file_name: string;
  document_url: string;
  extraction: ExtractionWithConfidence;
  status: TriageStatus;
}

export interface LineItemCorrection {
  description: string;
  quantity: number;
  unit_price: number;
  amount: number;
}

export interface TriagePatchRequest {
  action: TriageAction;
  corrections?: {
    vendor_name?: string | null;
    invoice_number?: string | null;
    invoice_date?: string | null;
    due_date?: string | null;
    subtotal?: number | null;
    tax?: number | null;
    total?: number | null;
    notes?: string | null;
    line_items?: LineItemCorrection[];
  };
}

export interface TriagePatchResponse {
  document_id: string;
  status: "confirmed" | "rejected";
  updated_at: string;
}

// ─── Settings / Locations ─────────────────────────────────────────────────────

export type ConnectionStatus = "active" | "invalid" | "untested";

export interface Location {
  location_id: string;
  name: string;
  api_key_last4: string;
  connection_status: ConnectionStatus;
  created_at: string;
  updated_at: string;
}

export interface LocationListResponse {
  locations: Location[];
}

export interface CreateLocationRequest {
  name: string;
  acculynx_api_key: string;
}

export interface CreateLocationResponse {
  location_id: string;
  name: string;
  api_key_last4: string;
  connection_status: "untested";
  created_at: string;
}

export interface UpdateLocationRequest {
  name?: string | null;
  acculynx_api_key?: string | null;
}

export interface UpdateLocationResponse {
  location_id: string;
  name: string;
  api_key_last4: string;
  connection_status: "untested";
  updated_at: string;
}

// ─── Health ───────────────────────────────────────────────────────────────────

export type HealthStatus = "healthy" | "degraded" | "down";
export type CheckStatus = "ok" | "error";

export interface ServiceCheck {
  status: CheckStatus;
  latency_ms: number;
}

export interface CeleryCheck {
  status: CheckStatus;
  active_count: number;
  queue_depth: number;
}

export interface HealthResponse {
  status: HealthStatus;
  checks: {
    supabase: ServiceCheck;
    redis: ServiceCheck;
    celery_workers: CeleryCheck;
  };
  timestamp: string;
}
