import type {
  Organization,
  OrgUsersResponse,
  JobListResponse,
  JobDetail,
  UploadResponse,
  EventListResponse,
  KpiResponse,
  AnalyticsPeriod,
  VendorSpendResponse,
  SearchResponse,
  TriageQueueResponse,
  TriageDetail,
  TriagePatchRequest,
  TriagePatchResponse,
  LocationListResponse,
  CreateLocationRequest,
  CreateLocationResponse,
  UpdateLocationRequest,
  UpdateLocationResponse,
  HealthResponse,
  LeakageSummary,
  OpsTriageQueueResponse,
  OpsJobDetail,
  UpdateLocationNotificationsRequest,
  UpdateLocationNotificationsResponse,
  TestLocationNotificationsResponse,
  UploadPricingContractResponse,
} from "@/lib/types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

// Module-level auth context — set once after login via setAuthContext()
let _workosOrgId: string | null = null;
let _workosUserId: string | null = null;
let _workosOrgName: string | null = null;

export function setAuthContext(
  workosOrgId: string | null,
  orgName: string,
  workosUserId?: string,
) {
  _workosOrgId = workosOrgId;
  _workosOrgName = orgName;
  if (workosUserId) _workosUserId = workosUserId;
}

class ApiError extends Error {
  constructor(
    public status: number,
    public statusText: string,
    public body: string,
  ) {
    super(`API error ${status}: ${statusText}`);
    this.name = "ApiError";
  }
}

async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const authHeaders: Record<string, string> = {};
  if (_workosOrgId) authHeaders["x-workos-org-id"] = _workosOrgId;
  if (_workosUserId) authHeaders["x-workos-user-id"] = _workosUserId;
  if (_workosOrgName) authHeaders["x-workos-org-name"] = _workosOrgName;

  // Don't set Content-Type for FormData — browser sets it with the boundary.
  const isFormData = options.body instanceof FormData;
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      ...(isFormData ? {} : { "Content-Type": "application/json" }),
      ...authHeaders,
      ...options.headers,
    },
  });

  if (!res.ok) {
    const body = await res.text();
    throw new ApiError(res.status, res.statusText, body);
  }

  if (res.status === 204) {
    return undefined as T;
  }

  return res.json() as Promise<T>;
}

function qs(params: Record<string, string | number | undefined | null>): string {
  const entries = Object.entries(params).filter(
    (entry): entry is [string, string | number] =>
      entry[1] !== undefined && entry[1] !== null,
  );
  if (entries.length === 0) return "";
  return "?" + new URLSearchParams(entries.map(([k, v]) => [k, String(v)])).toString();
}

// ─── API Methods ──────────────────────────────────────────────────────────────

export const api = {
  // Organizations
  getOrganization: () =>
    apiFetch<Organization>("/api/v1/organizations/me"),

  getOrgUsers: () =>
    apiFetch<OrgUsersResponse>("/api/v1/organizations/me/users"),

  // Jobs
  getJobs: (params?: {
    location_id?: string;
    status?: string;
    limit?: number;
    offset?: number;
  }) => apiFetch<JobListResponse>(`/api/v1/jobs${qs(params ?? {})}`),

  getJob: (jobId: string) =>
    apiFetch<JobDetail>(`/api/v1/jobs/${jobId}`),

  uploadDocument: (file: File, organizationId: string, locationId?: string) => {
    const form = new FormData();
    form.append("file", file);
    form.append("organization_id", organizationId);
    if (locationId) {
      form.append("location_id", locationId);
    }
    return apiFetch<UploadResponse>("/api/v1/documents/upload", {
      method: "POST",
      body: form,
      headers: {}, // let browser set Content-Type with boundary
    });
  },

  // Events
  getEvents: (params?: {
    limit?: number;
    offset?: number;
    location_id?: string;
  }) => apiFetch<EventListResponse>(`/api/v1/events${qs(params ?? {})}`),

  // Analytics
  getKpis: (params?: { period?: AnalyticsPeriod; location_id?: string }) =>
    apiFetch<KpiResponse>(`/api/v1/analytics/kpis${qs(params ?? {})}`),

  getVendorSpend: (params?: {
    period?: AnalyticsPeriod;
    location_id?: string;
    group_by?: "vendor" | "job" | "month";
  }) =>
    apiFetch<VendorSpendResponse>(
      `/api/v1/analytics/vendor-spend${qs(params ?? {})}`,
    ),

  // Search
  search: (query: string, locationId?: string, limit?: number) =>
    apiFetch<SearchResponse>("/api/v1/search", {
      method: "POST",
      body: JSON.stringify({
        query,
        location_id: locationId ?? null,
        limit: limit ?? 10,
      }),
    }),

  // Triage
  getTriageQueue: (params?: {
    location_id?: string;
    limit?: number;
    offset?: number;
  }) => apiFetch<TriageQueueResponse>(`/api/v1/triage${qs(params ?? {})}`),

  getTriageDetail: (documentId: string) =>
    apiFetch<TriageDetail>(`/api/v1/triage/${documentId}`),

  patchTriage: (documentId: string, body: TriagePatchRequest) =>
    apiFetch<TriagePatchResponse>(`/api/v1/triage/${documentId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  // Settings — Locations
  getLocations: () =>
    apiFetch<LocationListResponse>("/api/v1/settings/locations"),

  createLocation: (body: CreateLocationRequest) =>
    apiFetch<CreateLocationResponse>("/api/v1/settings/locations", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  updateLocation: (locationId: string, body: UpdateLocationRequest) =>
    apiFetch<UpdateLocationResponse>(
      `/api/v1/settings/locations/${locationId}`,
      {
        method: "PATCH",
        body: JSON.stringify(body),
      },
    ),

  deleteLocation: (locationId: string) =>
    apiFetch<void>(`/api/v1/settings/locations/${locationId}`, {
      method: "DELETE",
    }),

  // Health
  getHealth: () => apiFetch<HealthResponse>("/api/v1/health"),

  // Analytics — Leakage (C-Suite)
  getLeakageSummary: (params?: { period?: AnalyticsPeriod }) =>
    apiFetch<LeakageSummary>(`/api/v1/analytics/leakage${qs(params ?? {})}`),

  // Ops HITL queue (needs_clarity)
  getOpsTriageQueue: (params?: { limit?: number; offset?: number }) =>
    apiFetch<OpsTriageQueueResponse>(
      `/api/v1/triage${qs({ status: "needs_clarity", ...params })}`,
    ),

  // Ops job detail (context-scored view)
  getJobDetail: (jobId: string) =>
    apiFetch<OpsJobDetail>(`/api/v1/jobs/${jobId}`),

  // Triage actions on context-scored jobs
  confirmTriage: (jobId: string) =>
    apiFetch<{ job_id: string; updated_at: string }>(
      `/api/v1/triage/${jobId}/confirm`,
      { method: "PATCH" },
    ),

  rejectTriage: (jobId: string) =>
    apiFetch<{ job_id: string; updated_at: string }>(
      `/api/v1/triage/${jobId}/reject`,
      { method: "PATCH" },
    ),

  reprocessJob: (jobId: string) =>
    apiFetch<{ job_id: string; status: string }>(
      `/api/v1/jobs/${jobId}/reprocess`,
      { method: "POST" },
    ),

  // Notification settings per location
  updateLocationNotifications: (
    locationId: string,
    body: UpdateLocationNotificationsRequest,
  ) =>
    apiFetch<UpdateLocationNotificationsResponse>(
      `/api/v1/settings/locations/${locationId}/notifications`,
      { method: "PATCH", body: JSON.stringify(body) },
    ),

  testLocationNotifications: (locationId: string) =>
    apiFetch<TestLocationNotificationsResponse>(
      `/api/v1/settings/locations/${locationId}/notifications/test`,
      { method: "POST" },
    ),

  // Pricing contracts — POST /api/v1/settings/pricing-contracts (multipart)
  // Org is resolved server-side from the x-workos-org-id header.
  uploadPricingContract: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return apiFetch<UploadPricingContractResponse>(
      "/api/v1/settings/pricing-contracts",
      { method: "POST", body: form },
    );
  },
};

export { ApiError };
