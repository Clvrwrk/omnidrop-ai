/**
 * OmniDrop AI — Shared TypeScript interfaces
 * Keep in sync with shared/models/ Python Pydantic models
 */

export type JobStatus = "pending" | "processing" | "completed" | "failed";

export interface IntakeJob {
  jobId: string;
  eventType: string;
  status: JobStatus;
  documentsProcessed: number;
  receivedAt: string;
  completedAt: string | null;
  errorMessage: string | null;
}

export interface HealthResponse {
  status: string;
  env: string;
}
