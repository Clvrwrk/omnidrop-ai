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
} from "@/lib/types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

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
  const res = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
    ...options,
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
};

export { ApiError };
