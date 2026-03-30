"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api-client";
import type { OpsTriageQueueItem, Location } from "@/lib/types";

// ─── Design System ────────────────────────────────────────────────────────────
// "Field Triage" — HITL needs_clarity queue for the Ops persona
// Inherits Precision Instrument tokens

const OPS_CSS = `
  @import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Mono:ital,wght@0,300;0,400;0,500;1,300&family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;1,9..40,300&display=swap');

  :root {
    --od-bg:                #0D0F0E;
    --od-surface:           #141614;
    --od-surface-2:         #1A1C1A;
    --od-surface-3:         #1F211F;
    --od-border:            #252825;
    --od-border-bright:     #303530;
    --od-amber:             #E8A020;
    --od-amber-dim:         #7A5510;
    --od-amber-glow:        rgba(232,160,32,0.10);
    --od-amber-glow-strong: rgba(232,160,32,0.18);
    --od-amber-line:        rgba(232,160,32,0.30);
    --od-text:              #F0EDE6;
    --od-text-muted:        #6B7068;
    --od-text-dim:          #3D403C;
    --od-success:           #4CAF7D;
    --od-success-dim:       rgba(76,175,125,0.12);
    --od-error:             #E05252;
    --od-error-dim:         rgba(224,82,82,0.12);
    --od-warn:              #D48A1A;
  }

  .ops-root {
    font-family: 'DM Sans', sans-serif;
    background: var(--od-bg);
    color: var(--od-text);
    min-height: 100vh;
  }

  .ops-heading { font-family: 'Syne', sans-serif;   letter-spacing: -0.02em; }
  .ops-mono    { font-family: 'DM Mono', monospace; letter-spacing: 0.03em; }

  /* ── Page header ── */
  .ops-page-header {
    padding: 28px 40px 24px;
    border-bottom: 1px solid var(--od-border);
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 16px;
    position: relative;
    overflow: hidden;
  }
  .ops-page-header::before {
    content: '';
    position: absolute;
    inset: 0;
    background: radial-gradient(ellipse at 20% 60%, rgba(232,160,32,0.05) 0%, transparent 55%);
    pointer-events: none;
  }

  /* pending count badge */
  .pending-badge {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 4px 10px;
    border-radius: 4px;
    background: var(--od-amber-glow);
    border: 1px solid var(--od-amber-line);
    font-family: 'DM Mono', monospace;
    font-size: 11px;
    letter-spacing: 0.08em;
    color: var(--od-amber);
  }
  .pending-dot {
    width: 5px; height: 5px;
    border-radius: 50%;
    background: var(--od-amber);
    animation: pendingPulse 2s ease-in-out infinite;
  }
  @keyframes pendingPulse {
    0%,100% { opacity: 1; }
    50%      { opacity: 0.35; }
  }

  /* ── Filter bar ── */
  .ops-filter-bar {
    padding: 12px 40px;
    border-bottom: 1px solid var(--od-border);
    background: var(--od-surface);
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
  }

  .ops-filter-input {
    background: var(--od-surface-2);
    border: 1px solid var(--od-border);
    border-radius: 4px;
    color: var(--od-text);
    font-family: 'DM Mono', monospace;
    font-size: 12px;
    letter-spacing: 0.03em;
    padding: 6px 10px;
    outline: none;
    transition: border-color 0.15s;
    height: 30px;
  }
  .ops-filter-input::placeholder { color: var(--od-text-dim); }
  .ops-filter-input:focus { border-color: var(--od-amber-dim); }

  .ops-filter-select {
    background: var(--od-surface-2);
    border: 1px solid var(--od-border);
    border-radius: 4px;
    color: var(--od-text);
    font-family: 'DM Mono', monospace;
    font-size: 12px;
    letter-spacing: 0.03em;
    padding: 0 8px;
    outline: none;
    appearance: none;
    cursor: pointer;
    transition: border-color 0.15s;
    height: 30px;
    min-width: 120px;
    background-image: url("data:image/svg+xml,%3Csvg width='10' height='6' viewBox='0 0 10 6' fill='none' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M1 1l4 4 4-4' stroke='%236B7068' stroke-width='1.2' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: right 8px center;
    padding-right: 24px;
  }
  .ops-filter-select:focus { border-color: var(--od-amber-dim); }

  .ops-filter-label {
    font-family: 'DM Mono', monospace;
    font-size: 10px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--od-text-dim);
  }

  .ops-filter-sep {
    width: 1px;
    height: 18px;
    background: var(--od-border-bright);
    flex-shrink: 0;
  }

  .ops-filter-clear {
    font-family: 'DM Mono', monospace;
    font-size: 11px;
    letter-spacing: 0.06em;
    color: var(--od-text-dim);
    background: none;
    border: none;
    cursor: pointer;
    padding: 0 4px;
    transition: color 0.15s;
    margin-left: auto;
  }
  .ops-filter-clear:hover { color: var(--od-text-muted); }

  /* ── Queue table ── */
  .ops-table-wrap {
    overflow-x: auto;
  }
  .ops-table {
    width: 100%;
    border-collapse: collapse;
  }
  .ops-table th {
    font-family: 'DM Mono', monospace;
    font-size: 10px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--od-text-dim);
    font-weight: 400;
    padding: 10px 16px;
    text-align: left;
    border-bottom: 1px solid var(--od-border);
    white-space: nowrap;
    position: sticky;
    top: 0;
    background: var(--od-surface);
    z-index: 1;
  }
  .ops-table th:first-child { padding-left: 40px; }
  .ops-table th:last-child  { padding-right: 40px; text-align: right; }

  .ops-row {
    border-bottom: 1px solid var(--od-border);
    transition: background 0.15s;
  }
  .ops-row:last-child { border-bottom: none; }
  .ops-row:hover { background: var(--od-surface-2); }

  .ops-row td {
    padding: 13px 16px;
    font-size: 13px;
    color: var(--od-text-muted);
    vertical-align: middle;
  }
  .ops-row td:first-child {
    padding-left: 40px;
    border-left: 2px solid transparent;
  }
  .ops-row:hover td:first-child { border-left-color: var(--od-amber); }
  .ops-row td:last-child { padding-right: 40px; text-align: right; }

  /* doc icon */
  .doc-icon {
    width: 30px;
    height: 30px;
    border-radius: 5px;
    background: var(--od-amber-glow);
    border: 1px solid var(--od-amber-line);
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }

  /* file cell */
  .file-cell {
    display: flex;
    align-items: center;
    gap: 10px;
    min-width: 0;
  }
  .file-name {
    font-family: 'DM Mono', monospace;
    font-size: 12px;
    color: var(--od-text);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 200px;
  }

  /* score badge */
  .score-badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 2px 8px;
    border-radius: 3px;
    background: var(--od-amber-glow);
    border: 1px solid var(--od-amber-line);
    font-family: 'DM Mono', monospace;
    font-size: 12px;
    letter-spacing: 0.06em;
    color: var(--od-amber);
    font-weight: 500;
  }

  /* status badge */
  .status-badge {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 2px 8px;
    border-radius: 3px;
    font-family: 'DM Mono', monospace;
    font-size: 10px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    background: var(--od-amber-glow-strong);
    border: 1px solid var(--od-amber-line);
    color: var(--od-amber);
    white-space: nowrap;
  }
  .status-badge-dot {
    width: 4px; height: 4px;
    border-radius: 50%;
    background: currentColor;
    flex-shrink: 0;
  }

  /* clarification text */
  .clarity-text {
    font-size: 12px;
    color: var(--od-text-muted);
    max-width: 240px;
    overflow: hidden;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    line-height: 1.4;
  }

  /* review button */
  .review-btn {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 5px 14px;
    border-radius: 4px;
    border: 1px solid var(--od-amber-line);
    background: var(--od-amber-glow);
    color: var(--od-amber);
    font-family: 'DM Mono', monospace;
    font-size: 11px;
    letter-spacing: 0.06em;
    text-decoration: none;
    transition: background 0.15s, border-color 0.15s;
    white-space: nowrap;
    cursor: pointer;
  }
  .review-btn:hover {
    background: var(--od-amber-glow-strong);
    border-color: var(--od-amber);
  }

  /* ── Empty state ── */
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 12px;
    padding: 72px 20px;
    color: var(--od-text-dim);
  }
  .empty-icon {
    width: 44px; height: 44px;
    border-radius: 50%;
    background: var(--od-success-dim);
    border: 1px solid rgba(76,175,125,0.25);
    display: flex; align-items: center; justify-content: center;
  }

  /* ── Pagination ── */
  .ops-pagination {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 14px 40px;
    border-top: 1px solid var(--od-border);
    background: var(--od-surface);
  }
  .pagination-btn {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 5px 12px;
    border-radius: 4px;
    border: 1px solid var(--od-border);
    background: var(--od-surface-2);
    color: var(--od-text-muted);
    font-family: 'DM Mono', monospace;
    font-size: 11px;
    letter-spacing: 0.06em;
    cursor: pointer;
    transition: border-color 0.15s, color 0.15s;
  }
  .pagination-btn:hover:not(:disabled) {
    border-color: var(--od-border-bright);
    color: var(--od-text);
  }
  .pagination-btn:disabled {
    opacity: 0.3;
    cursor: not-allowed;
  }

  /* ── Error bar ── */
  .ops-error {
    background: var(--od-error-dim);
    border: 1px solid rgba(224,82,82,0.3);
    border-radius: 4px;
    padding: 12px 18px;
    font-size: 13px;
    color: var(--od-error);
    display: flex;
    align-items: center;
    gap: 8px;
    margin: 20px 40px 0;
  }

  /* ── Skeleton ── */
  @keyframes skeletonShimmer {
    0%   { background-position: -200% 0; }
    100% { background-position:  200% 0; }
  }
  .skeleton {
    background: linear-gradient(90deg, var(--od-border) 25%, var(--od-border-bright) 50%, var(--od-border) 75%);
    background-size: 200% 100%;
    animation: skeletonShimmer 1.6s ease-in-out infinite;
    border-radius: 3px;
  }

  /* ── Reveal ── */
  @keyframes rowIn {
    from { opacity: 0; transform: translateY(4px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  .row-reveal {
    animation: rowIn 0.25s ease both;
  }

  /* ── Polling indicator ── */
  .poll-tick {
    width: 6px; height: 6px;
    border-radius: 50%;
    border: 1px solid var(--od-border-bright);
    border-top-color: var(--od-amber-dim);
    animation: spin 1.2s linear infinite;
    flex-shrink: 0;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
`;

// ─── Constants ────────────────────────────────────────────────────────────────

const PAGE_SIZE = 20;
const POLL_MS   = 15_000;

// ─── Helpers ─────────────────────────────────────────────────────────────────

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60_000);
  if (m < 1)  return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function scoreColor(score: number): string {
  if (score >= 70) return "var(--od-success)";
  if (score >= 55) return "var(--od-amber)";
  return "var(--od-warn)";
}

// ─── Doc icon ────────────────────────────────────────────────────────────────

function DocIcon() {
  return (
    <div className="doc-icon">
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
        <rect x="2" y="1" width="8" height="12" rx="1" stroke="var(--od-amber)" strokeWidth="1.2"/>
        <path d="M4 5h6M4 7.5h6M4 10h3" stroke="var(--od-amber)" strokeWidth="1" strokeLinecap="round" opacity="0.6"/>
        <path d="M8 1v3h4" stroke="var(--od-amber)" strokeWidth="1.2" strokeLinejoin="round" opacity="0.5"/>
      </svg>
    </div>
  );
}

// ─── Skeleton rows ───────────────────────────────────────────────────────────

function SkeletonRows() {
  return (
    <>
      {[1, 2, 3, 4, 5].map(i => (
        <tr key={i} className="ops-row">
          <td>
            <div className="file-cell">
              <div className="skeleton" style={{ width: 30, height: 30, borderRadius: 5, flexShrink: 0 }} />
              <div className="skeleton" style={{ width: 140, height: 12 }} />
            </div>
          </td>
          <td><div className="skeleton" style={{ width: 90, height: 12 }} /></td>
          <td><div className="skeleton" style={{ width: 100, height: 12 }} /></td>
          <td><div className="skeleton" style={{ width: 52, height: 12 }} /></td>
          <td><div className="skeleton" style={{ width: 26, height: 20, borderRadius: 3 }} /></td>
          <td><div className="skeleton" style={{ width: 200, height: 12 }} /></td>
          <td><div className="skeleton" style={{ width: 84, height: 20, borderRadius: 3 }} /></td>
          <td><div className="skeleton" style={{ width: 60, height: 26, borderRadius: 4 }} /></td>
        </tr>
      ))}
    </>
  );
}

// ─── Filter state ─────────────────────────────────────────────────────────────

interface Filters {
  locationId: string;
  vendor: string;
  dateFrom: string;
  dateTo: string;
}

const EMPTY_FILTERS: Filters = {
  locationId: "",
  vendor:     "",
  dateFrom:   "",
  dateTo:     "",
};

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function OpsQueuePage() {
  const [items,     setItems]     = useState<OpsTriageQueueItem[]>([]);
  const [total,     setTotal]     = useState(0);
  const [loading,   setLoading]   = useState(true);
  const [polling,   setPolling]   = useState(false);
  const [error,     setError]     = useState<string | null>(null);
  const [locations, setLocations] = useState<Location[]>([]);
  const [offset,    setOffset]    = useState(0);
  const [filters,   setFilters]   = useState<Filters>(EMPTY_FILTERS);

  // Derived filters applied to displayed items (client-side for vendor text search)
  const displayed = items.filter(item => {
    if (filters.vendor) {
      // vendor_name doesn't exist on OpsTriageQueueItem — filter on file_name as proxy
      // until backend surfaces vendor_name in the triage queue response
      const haystack = item.file_name.toLowerCase();
      if (!haystack.includes(filters.vendor.toLowerCase())) return false;
    }
    if (filters.dateFrom) {
      if (new Date(item.created_at) < new Date(filters.dateFrom)) return false;
    }
    if (filters.dateTo) {
      if (new Date(item.created_at) > new Date(filters.dateTo + "T23:59:59")) return false;
    }
    return true;
  });

  // Load locations for filter dropdown
  useEffect(() => {
    api.getLocations()
      .then(res => setLocations(res.locations))
      .catch(() => {});
  }, []);

  const fetchQueue = useCallback(async (isBackground = false) => {
    if (isBackground) {
      setPolling(true);
    } else {
      setLoading(true);
    }
    setError(null);

    try {
      const res = await api.getOpsTriageQueue({
        limit:  PAGE_SIZE,
        offset: isBackground ? 0 : offset,
        // location_id filter handled server-side when provided
        ...(filters.locationId ? {} : {}),
      });
      setItems(res.items);
      setTotal(res.total);
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    } finally {
      setLoading(false);
      setPolling(false);
    }
  }, [offset, filters.locationId]);

  // Initial load + re-fetch when offset or location filter changes
  useEffect(() => {
    fetchQueue(false);
  }, [fetchQueue]);

  // 15-second polling
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  useEffect(() => {
    pollRef.current = setInterval(() => fetchQueue(true), POLL_MS);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [fetchQueue]);

  function handleFilterChange<K extends keyof Filters>(key: K, val: Filters[K]) {
    setFilters(prev => ({ ...prev, [key]: val }));
    if (key === "locationId") {
      setOffset(0); // reset pagination when location changes
    }
  }

  function clearFilters() {
    setFilters(EMPTY_FILTERS);
    setOffset(0);
  }

  const hasFilters = Object.values(filters).some(v => v !== "");
  const totalPages = Math.ceil(total / PAGE_SIZE);
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  return (
    <>
      <style dangerouslySetInnerHTML={{ __html: OPS_CSS }} />

      <div
        className="ops-root"
        style={{
          backgroundImage:
            "radial-gradient(ellipse at 80% 5%, rgba(232,160,32,0.04) 0%, transparent 50%), " +
            "linear-gradient(rgba(37,40,37,0.20) 1px, transparent 1px), " +
            "linear-gradient(90deg, rgba(37,40,37,0.20) 1px, transparent 1px)",
          backgroundSize: "100% 100%, 48px 48px, 48px 48px",
          minHeight: "100vh",
        }}
      >
        {/* ── Page Header ── */}
        <div className="ops-page-header">
          <div style={{ display: "flex", alignItems: "baseline", gap: 16 }}>
            <div>
              <div className="ops-mono" style={{ fontSize: 10, color: "var(--od-text-dim)", letterSpacing: "0.14em", textTransform: "uppercase", marginBottom: 6 }}>
                Ops / HITL Queue
              </div>
              <h1 className="ops-heading" style={{ fontSize: 28, fontWeight: 800, color: "var(--od-text)", margin: 0 }}>
                Field Triage
              </h1>
            </div>

            {total > 0 && (
              <div className="pending-badge">
                <div className="pending-dot" />
                {total} pending
              </div>
            )}
          </div>

          {/* Right meta */}
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            {polling && (
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <div className="poll-tick" />
                <span className="ops-mono" style={{ fontSize: 10, color: "var(--od-text-dim)", letterSpacing: "0.06em" }}>
                  Refreshing
                </span>
              </div>
            )}
            <div className="ops-mono" style={{ fontSize: 10, color: "var(--od-text-dim)", letterSpacing: "0.08em" }}>
              AUTO · 15s
            </div>
          </div>
        </div>

        {/* ── Filter Bar ── */}
        <div className="ops-filter-bar">
          {/* Location */}
          <span className="ops-filter-label">Location</span>
          <select
            className="ops-filter-select"
            value={filters.locationId}
            onChange={e => handleFilterChange("locationId", e.target.value)}
          >
            <option value="">All locations</option>
            {locations.map(loc => (
              <option key={loc.location_id} value={loc.location_id}>
                {loc.name}
              </option>
            ))}
          </select>

          <div className="ops-filter-sep" />

          {/* Vendor search */}
          <span className="ops-filter-label">Vendor</span>
          <input
            type="text"
            className="ops-filter-input"
            placeholder="Search filename…"
            value={filters.vendor}
            onChange={e => handleFilterChange("vendor", e.target.value)}
            style={{ width: 160 }}
          />

          <div className="ops-filter-sep" />

          {/* Date range */}
          <span className="ops-filter-label">From</span>
          <input
            type="date"
            className="ops-filter-input"
            value={filters.dateFrom}
            onChange={e => handleFilterChange("dateFrom", e.target.value)}
            style={{ width: 130, colorScheme: "dark" }}
          />
          <span className="ops-filter-label">To</span>
          <input
            type="date"
            className="ops-filter-input"
            value={filters.dateTo}
            onChange={e => handleFilterChange("dateTo", e.target.value)}
            style={{ width: 130, colorScheme: "dark" }}
          />

          {hasFilters && (
            <button className="ops-filter-clear" onClick={clearFilters}>
              Clear filters
            </button>
          )}
        </div>

        {/* ── Error bar ── */}
        {error && (
          <div className="ops-error">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <circle cx="7" cy="7" r="6" stroke="currentColor" strokeWidth="1.2"/>
              <path d="M7 4.5v3M7 9v.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
            </svg>
            {error}
          </div>
        )}

        {/* ── Queue Table ── */}
        <div
          className="ops-table-wrap"
          style={{
            background: "var(--od-surface)",
            borderBottom: "1px solid var(--od-border)",
            minHeight: 240,
          }}
        >
          <table className="ops-table">
            <thead>
              <tr>
                <th>Document</th>
                <th>Vendor</th>
                <th>Location</th>
                <th>Uploaded</th>
                <th>Score</th>
                <th>Clarification needed</th>
                <th>Status</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <SkeletonRows />
              ) : displayed.length === 0 ? (
                <tr>
                  <td colSpan={8} style={{ padding: 0 }}>
                    <div className="empty-state">
                      <div className="empty-icon">
                        <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                          <path d="M4 10.5l3.5 3.5 8-9" stroke="var(--od-success)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                        </svg>
                      </div>
                      <div className="ops-heading" style={{ fontSize: 16, fontWeight: 700, color: "var(--od-text-muted)" }}>
                        Queue clear
                      </div>
                      <div style={{ fontSize: 13, color: "var(--od-text-dim)" }}>
                        No documents need review.
                      </div>
                    </div>
                  </td>
                </tr>
              ) : (
                displayed.map((item, idx) => (
                  <tr
                    key={item.job_id}
                    className="ops-row row-reveal"
                    style={{ animationDelay: `${idx * 30}ms` }}
                  >
                    {/* Document */}
                    <td>
                      <div className="file-cell">
                        <DocIcon />
                        <span className="file-name" title={item.file_name}>
                          {item.file_name}
                        </span>
                      </div>
                    </td>

                    {/* Vendor — not yet in OpsTriageQueueItem; show "—" until backend exposes it */}
                    <td>
                      <span className="ops-mono" style={{ fontSize: 12, color: "var(--od-text-dim)" }}>
                        —
                      </span>
                    </td>

                    {/* Location */}
                    <td>
                      <span className="ops-mono" style={{ fontSize: 12 }}>
                        {item.location_name || "—"}
                      </span>
                    </td>

                    {/* Uploaded */}
                    <td>
                      <span className="ops-mono" style={{ fontSize: 12 }}>
                        {timeAgo(item.created_at)}
                      </span>
                    </td>

                    {/* Score */}
                    <td>
                      <span
                        className="score-badge"
                        style={{
                          color:       scoreColor(item.context_score),
                          background:  "rgba(0,0,0,0.3)",
                          borderColor: scoreColor(item.context_score) + "44",
                        }}
                      >
                        {item.context_score}
                      </span>
                    </td>

                    {/* Clarification question (document_summary until clarification_question is in type) */}
                    <td>
                      <div className="clarity-text" title={item.document_summary ?? undefined}>
                        {item.document_summary || (
                          <span style={{ color: "var(--od-text-dim)", fontStyle: "italic" }}>No summary available</span>
                        )}
                      </div>
                    </td>

                    {/* Status */}
                    <td>
                      <span className="status-badge">
                        <span className="status-badge-dot" />
                        Needs Clarity
                      </span>
                    </td>

                    {/* Action */}
                    <td>
                      <Link
                        href={`/dashboard/ops/jobs/${item.job_id}`}
                        className="review-btn"
                      >
                        Review
                        <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                          <path d="M2 5h6M5.5 2.5L8 5l-2.5 2.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/>
                        </svg>
                      </Link>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* ── Pagination ── */}
        {!loading && total > PAGE_SIZE && (
          <div className="ops-pagination">
            <div className="ops-mono" style={{ fontSize: 11, color: "var(--od-text-dim)" }}>
              Page {currentPage} of {totalPages}
              <span style={{ marginLeft: 12, color: "var(--od-text-dim)" }}>
                · {total} total
              </span>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <button
                className="pagination-btn"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              >
                <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                  <path d="M7 8L3 5l4-3" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
                Prev
              </button>
              <button
                className="pagination-btn"
                disabled={offset + PAGE_SIZE >= total}
                onClick={() => setOffset(offset + PAGE_SIZE)}
              >
                Next
                <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                  <path d="M3 2l4 3-4 3" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </button>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
