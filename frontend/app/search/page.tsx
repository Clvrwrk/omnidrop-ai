"use client";

// NOTE: The CMD+K listener below navigates to this page from within /search.
// For app-wide CMD+K support, move the useEffect listener to frontend/app/layout.tsx
// and call router.push("/search") from there. Left here because this agent only owns
// files under /frontend/app/search/.

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api-client";
import type { Location, SearchResult } from "@/lib/types";

// ─── Design System ────────────────────────────────────────────────────────────
// "Signal Search" — CMD+K semantic search surface
// Inherits Precision Instrument tokens (identical to Field Triage + War Room)

const SEARCH_CSS = `
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
  }

  .ss-root {
    font-family: 'DM Sans', sans-serif;
    background: var(--od-bg);
    color: var(--od-text);
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
  }

  .ss-heading { font-family: 'Syne', sans-serif;   letter-spacing: -0.02em; }
  .ss-mono    { font-family: 'DM Mono', monospace; letter-spacing: 0.03em; }

  /* ── Inner column ── */
  .ss-column {
    width: 100%;
    max-width: 760px;
    padding: 0 20px;
  }

  /* ── Page header ── */
  .ss-page-header {
    width: 100%;
    padding: 28px 0 24px;
    border-bottom: 1px solid var(--od-border);
    display: flex;
    align-items: center;
    justify-content: center;
    position: relative;
    overflow: hidden;
    margin-bottom: 0;
  }
  .ss-page-header::before {
    content: '';
    position: absolute;
    inset: 0;
    background: radial-gradient(ellipse at 50% 80%, rgba(232,160,32,0.06) 0%, transparent 60%);
    pointer-events: none;
  }
  .ss-header-inner {
    text-align: center;
  }

  /* ── Search well ── */
  .ss-well {
    padding: 36px 0 0;
    display: flex;
    flex-direction: column;
    align-items: stretch;
    gap: 12px;
  }

  /* ── Search input ── */
  .ss-input-wrap {
    position: relative;
  }
  .ss-input-icon {
    position: absolute;
    left: 18px;
    top: 50%;
    transform: translateY(-50%);
    pointer-events: none;
    color: var(--od-text-dim);
    transition: color 0.15s;
    display: flex;
    align-items: center;
  }
  .ss-input-wrap:focus-within .ss-input-icon {
    color: var(--od-amber);
  }
  .ss-input {
    width: 100%;
    box-sizing: border-box;
    background: var(--od-surface);
    border: 1px solid var(--od-border);
    border-radius: 8px;
    color: var(--od-text);
    font-family: 'DM Sans', sans-serif;
    font-size: 17px;
    font-weight: 400;
    padding: 16px 18px 16px 50px;
    outline: none;
    transition: border-color 0.18s, box-shadow 0.18s;
  }
  .ss-input::placeholder { color: var(--od-text-dim); }
  .ss-input:focus {
    border-color: var(--od-amber);
    box-shadow: 0 0 0 3px rgba(232,160,32,0.10);
  }

  /* clear button inside input */
  .ss-input-clear {
    position: absolute;
    right: 14px;
    top: 50%;
    transform: translateY(-50%);
    background: none;
    border: none;
    cursor: pointer;
    color: var(--od-text-dim);
    display: flex;
    align-items: center;
    padding: 4px;
    border-radius: 3px;
    transition: color 0.15s;
  }
  .ss-input-clear:hover { color: var(--od-text-muted); }

  /* ── Location filter ── */
  .ss-filters {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }
  .ss-filter-label {
    font-family: 'DM Mono', monospace;
    font-size: 10px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--od-text-dim);
  }
  .ss-filter-select {
    background: var(--od-surface-2);
    border: 1px solid var(--od-border);
    border-radius: 4px;
    color: var(--od-text-muted);
    font-family: 'DM Mono', monospace;
    font-size: 11px;
    letter-spacing: 0.03em;
    padding: 0 24px 0 8px;
    outline: none;
    appearance: none;
    cursor: pointer;
    transition: border-color 0.15s, color 0.15s;
    height: 28px;
    min-width: 140px;
    background-image: url("data:image/svg+xml,%3Csvg width='10' height='6' viewBox='0 0 10 6' fill='none' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M1 1l4 4 4-4' stroke='%236B7068' stroke-width='1.2' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: right 8px center;
  }
  .ss-filter-select:focus {
    border-color: var(--od-amber-dim);
    color: var(--od-text);
  }

  /* kbd hint */
  .ss-kbd {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    margin-left: auto;
  }
  .ss-kbd-key {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: var(--od-surface-2);
    border: 1px solid var(--od-border-bright);
    border-radius: 3px;
    font-family: 'DM Mono', monospace;
    font-size: 10px;
    letter-spacing: 0.04em;
    color: var(--od-text-dim);
    padding: 2px 5px;
    line-height: 1;
  }

  /* ── Divider ── */
  .ss-divider {
    width: 100%;
    height: 1px;
    background: var(--od-border);
    margin: 28px 0 24px;
  }

  /* ── Result cards ── */
  .ss-results {
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding-bottom: 60px;
  }

  .ss-card {
    background: var(--od-surface);
    border: 1px solid var(--od-border);
    border-radius: 8px;
    padding: 18px 20px;
    transition: border-color 0.15s, background 0.15s;
    position: relative;
    overflow: hidden;
  }
  .ss-card::before {
    content: '';
    position: absolute;
    left: 0; top: 0; bottom: 0;
    width: 2px;
    background: transparent;
    transition: background 0.15s;
  }
  .ss-card:hover {
    border-color: var(--od-border-bright);
    background: var(--od-surface-2);
  }
  .ss-card:hover::before {
    background: var(--od-amber);
  }

  .ss-card-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 10px;
  }
  .ss-card-meta {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    min-width: 0;
  }
  .ss-file-name {
    font-family: 'DM Mono', monospace;
    font-size: 12px;
    color: var(--od-text);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 280px;
  }
  .ss-location-badge {
    display: inline-flex;
    align-items: center;
    padding: 1px 7px;
    border-radius: 3px;
    background: var(--od-surface-3);
    border: 1px solid var(--od-border-bright);
    font-family: 'DM Mono', monospace;
    font-size: 10px;
    letter-spacing: 0.06em;
    color: var(--od-text-dim);
    white-space: nowrap;
  }
  .ss-type-badge {
    display: inline-flex;
    align-items: center;
    padding: 1px 7px;
    border-radius: 3px;
    background: var(--od-surface-3);
    border: 1px solid var(--od-border-bright);
    font-family: 'DM Mono', monospace;
    font-size: 10px;
    letter-spacing: 0.06em;
    color: var(--od-text-dim);
    text-transform: uppercase;
    white-space: nowrap;
  }

  /* similarity score */
  .ss-score {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 3px 9px;
    border-radius: 4px;
    font-family: 'DM Mono', monospace;
    font-size: 11px;
    letter-spacing: 0.06em;
    font-weight: 500;
    white-space: nowrap;
    flex-shrink: 0;
  }
  .ss-score-high {
    background: var(--od-amber-glow);
    border: 1px solid var(--od-amber-line);
    color: var(--od-amber);
  }
  .ss-score-mid {
    background: rgba(76,175,125,0.10);
    border: 1px solid rgba(76,175,125,0.25);
    color: #4CAF7D;
  }
  .ss-score-low {
    background: var(--od-surface-3);
    border: 1px solid var(--od-border-bright);
    color: var(--od-text-muted);
  }

  /* chunk text */
  .ss-chunk {
    font-size: 13.5px;
    line-height: 1.6;
    color: var(--od-text-muted);
    display: -webkit-box;
    -webkit-line-clamp: 4;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  /* review link */
  .ss-review-link {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    margin-top: 12px;
    font-family: 'DM Mono', monospace;
    font-size: 11px;
    letter-spacing: 0.06em;
    color: var(--od-amber-dim);
    text-decoration: none;
    transition: color 0.15s;
  }
  .ss-review-link:hover { color: var(--od-amber); }

  /* ── Skeleton shimmer ── */
  @keyframes skeletonShimmer {
    0%   { background-position: -200% 0; }
    100% { background-position:  200% 0; }
  }
  .skeleton {
    background: linear-gradient(90deg, var(--od-border) 25%, var(--od-border-bright) 50%, var(--od-border) 75%);
    background-size: 200% 100%;
    animation: skeletonShimmer 1.6s ease-in-out infinite;
    border-radius: 4px;
  }

  .ss-card-skeleton {
    background: var(--od-surface);
    border: 1px solid var(--od-border);
    border-radius: 8px;
    padding: 18px 20px;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  /* ── State screens ── */
  .ss-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 10px;
    padding: 60px 20px;
    text-align: center;
  }
  .ss-state-icon {
    width: 44px; height: 44px;
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    flex-shrink: 0;
  }

  /* ── Error bar ── */
  .ss-error {
    background: var(--od-error-dim);
    border: 1px solid rgba(224,82,82,0.3);
    border-radius: 6px;
    padding: 12px 16px;
    font-size: 13px;
    color: var(--od-error);
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;
  }

  /* ── Card reveal ── */
  @keyframes cardIn {
    from { opacity: 0; transform: translateY(6px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  .card-reveal {
    animation: cardIn 0.22s ease both;
  }

  /* ── Result count hint ── */
  .ss-count-hint {
    font-family: 'DM Mono', monospace;
    font-size: 10px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--od-text-dim);
    margin-bottom: 4px;
  }
`;

// ─── Constants ────────────────────────────────────────────────────────────────

const DEBOUNCE_MS = 400;
const RESULT_LIMIT = 20;

// ─── Helpers ─────────────────────────────────────────────────────────────────

function scoreClass(score: number): string {
  if (score >= 0.85) return "ss-score ss-score-high";
  if (score >= 0.65) return "ss-score ss-score-mid";
  return "ss-score ss-score-low";
}

// ─── Skeleton cards ───────────────────────────────────────────────────────────

function SkeletonCards() {
  return (
    <>
      {[1, 2, 3].map(i => (
        <div key={i} className="ss-card-skeleton">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <div className="skeleton" style={{ width: 160, height: 12 }} />
              <div className="skeleton" style={{ width: 60, height: 18, borderRadius: 3 }} />
            </div>
            <div className="skeleton" style={{ width: 66, height: 22, borderRadius: 4 }} />
          </div>
          <div className="skeleton" style={{ width: "100%", height: 12 }} />
          <div className="skeleton" style={{ width: "90%", height: 12 }} />
          <div className="skeleton" style={{ width: "70%", height: 12 }} />
          <div className="skeleton" style={{ width: 80, height: 11 }} />
        </div>
      ))}
    </>
  );
}

// ─── Result card ─────────────────────────────────────────────────────────────

function ResultCard({ result, idx }: { result: SearchResult; idx: number }) {
  const pct = Math.round(result.similarity_score * 100);
  return (
    <div
      className="ss-card card-reveal"
      style={{ animationDelay: `${idx * 35}ms` }}
    >
      <div className="ss-card-header">
        <div className="ss-card-meta">
          <span className="ss-file-name" title={result.file_name}>
            {result.file_name}
          </span>
          {result.location_name && (
            <span className="ss-location-badge">{result.location_name}</span>
          )}
          {result.document_type && (
            <span className="ss-type-badge">{result.document_type}</span>
          )}
        </div>
        <span className={scoreClass(result.similarity_score)}>
          {pct}% match
        </span>
      </div>

      <p className="ss-chunk">{result.chunk_text}</p>

      <Link
        href={`/dashboard/ops/jobs/${result.document_id}`}
        className="ss-review-link"
      >
        Open document
        <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
          <path d="M2 5h6M5.5 2.5L8 5l-2.5 2.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </Link>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function SearchPage() {
  const router = useRouter();

  const [query,      setQuery]      = useState("");
  const [locationId, setLocationId] = useState("");
  const [locations,  setLocations]  = useState<Location[]>([]);
  const [results,    setResults]    = useState<SearchResult[]>([]);
  const [loading,    setLoading]    = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [error,      setError]      = useState<string | null>(null);

  const inputRef   = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Auto-focus on mount
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // Load locations for filter dropdown
  useEffect(() => {
    api.getLocations()
      .then(res => setLocations(res.locations))
      .catch(() => {});
  }, []);

  // CMD+K / Ctrl+K listener — re-focuses input when already on /search.
  // NOTE: For app-wide navigation to /search, move this listener to
  // frontend/app/layout.tsx and call router.push("/search") from there.
  useEffect(() => {
    function handleCmdK(e: KeyboardEvent) {
      const isMac  = navigator.platform.toUpperCase().includes("MAC");
      const modKey = isMac ? e.metaKey : e.ctrlKey;
      if (modKey && e.key === "k") {
        e.preventDefault();
        inputRef.current?.focus();
        inputRef.current?.select();
      }
    }
    window.addEventListener("keydown", handleCmdK);
    return () => window.removeEventListener("keydown", handleCmdK);
  }, [router]);

  // Escape to clear
  useEffect(() => {
    function handleEscape(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setQuery("");
        setResults([]);
        setHasSearched(false);
        setError(null);
        inputRef.current?.focus();
      }
    }
    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, []);

  const runSearch = useCallback(async (q: string, locId: string) => {
    if (!q.trim()) {
      setResults([]);
      setHasSearched(false);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await api.search(
        q.trim(),
        locId || undefined,
        RESULT_LIMIT,
      );
      setResults(res.results);
      setHasSearched(true);
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  // Debounced search on query or location change
  function handleQueryChange(value: string) {
    setQuery(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      void runSearch(value, locationId);
    }, DEBOUNCE_MS);
  }

  function handleLocationChange(locId: string) {
    setLocationId(locId);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      void runSearch(query, locId);
    }, DEBOUNCE_MS);
  }

  function clearQuery() {
    setQuery("");
    setResults([]);
    setHasSearched(false);
    setError(null);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    inputRef.current?.focus();
  }

  // Derived
  const showInitial  = !hasSearched && !loading && !query.trim();
  const showEmpty    = hasSearched && !loading && results.length === 0;
  const showResults  = (hasSearched || loading) && query.trim().length > 0;

  return (
    <>
      <style dangerouslySetInnerHTML={{ __html: SEARCH_CSS }} />

      <div
        className="ss-root"
        style={{
          backgroundImage:
            "radial-gradient(ellipse at 50% 0%, rgba(232,160,32,0.04) 0%, transparent 55%), " +
            "linear-gradient(rgba(37,40,37,0.18) 1px, transparent 1px), " +
            "linear-gradient(90deg, rgba(37,40,37,0.18) 1px, transparent 1px)",
          backgroundSize: "100% 100%, 48px 48px, 48px 48px",
          minHeight: "100vh",
        }}
      >
        {/* ── Page header ── */}
        <div className="ss-page-header" style={{ width: "100%" }}>
          <div className="ss-header-inner">
            <div
              className="ss-mono"
              style={{
                fontSize: 10,
                color: "var(--od-text-dim)",
                letterSpacing: "0.14em",
                textTransform: "uppercase",
                marginBottom: 6,
              }}
            >
              Signal Search
            </div>
            <h1
              className="ss-heading"
              style={{
                fontSize: 26,
                fontWeight: 800,
                color: "var(--od-text)",
                margin: 0,
              }}
            >
              Document Search
            </h1>
          </div>
        </div>

        {/* ── Search well ── */}
        <div className="ss-column">
          <div className="ss-well">

            {/* Search input */}
            <div className="ss-input-wrap">
              <span className="ss-input-icon">
                <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                  <circle cx="7.5" cy="7.5" r="5.5" stroke="currentColor" strokeWidth="1.4"/>
                  <path d="M11.5 11.5L16 16" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
                </svg>
              </span>

              <input
                ref={inputRef}
                type="text"
                className="ss-input"
                placeholder="Search documents, invoices, line items…"
                value={query}
                onChange={e => handleQueryChange(e.target.value)}
                autoComplete="off"
                spellCheck={false}
              />

              {query && (
                <button
                  className="ss-input-clear"
                  onClick={clearQuery}
                  aria-label="Clear search"
                >
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                    <path d="M3 3l8 8M11 3L3 11" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
                  </svg>
                </button>
              )}
            </div>

            {/* Location filter + kbd hint */}
            <div className="ss-filters">
              <span className="ss-filter-label">Location</span>
              <select
                className="ss-filter-select"
                value={locationId}
                onChange={e => handleLocationChange(e.target.value)}
              >
                <option value="">All locations</option>
                {locations.map(loc => (
                  <option key={loc.location_id} value={loc.location_id}>
                    {loc.name}
                  </option>
                ))}
              </select>

              <span className="ss-kbd ss-mono" style={{ marginLeft: "auto" }}>
                <span className="ss-kbd-key">⌘</span>
                <span className="ss-kbd-key">K</span>
                <span style={{ fontSize: 10, color: "var(--od-text-dim)", marginLeft: 4 }}>
                  to focus
                </span>
              </span>
            </div>
          </div>

          <div className="ss-divider" />

          {/* ── Error bar ── */}
          {error && (
            <div className="ss-error">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <circle cx="7" cy="7" r="6" stroke="currentColor" strokeWidth="1.2"/>
                <path d="M7 4.5v3M7 9v.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
              </svg>
              {error}
            </div>
          )}

          {/* ── Results area ── */}
          <div className="ss-results">

            {/* Initial state */}
            {showInitial && (
              <div className="ss-state">
                <div
                  className="ss-state-icon"
                  style={{
                    background: "var(--od-amber-glow)",
                    border: "1px solid var(--od-amber-line)",
                  }}
                >
                  <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                    <circle cx="8.5" cy="8.5" r="6" stroke="var(--od-amber)" strokeWidth="1.4"/>
                    <path d="M13 13L18 18" stroke="var(--od-amber)" strokeWidth="1.4" strokeLinecap="round"/>
                    <path d="M6 8.5h5M8.5 6v5" stroke="var(--od-amber)" strokeWidth="1.2" strokeLinecap="round" opacity="0.7"/>
                  </svg>
                </div>
                <div
                  className="ss-heading"
                  style={{ fontSize: 16, fontWeight: 700, color: "var(--od-text-muted)" }}
                >
                  Signal Search
                </div>
                <div style={{ fontSize: 13, color: "var(--od-text-dim)", maxWidth: 340 }}>
                  Start typing to search across all ingested documents.
                </div>
              </div>
            )}

            {/* Loading skeleton */}
            {loading && <SkeletonCards />}

            {/* No results */}
            {showEmpty && !error && (
              <div className="ss-state">
                <div
                  className="ss-state-icon"
                  style={{
                    background: "var(--od-surface-2)",
                    border: "1px solid var(--od-border-bright)",
                  }}
                >
                  <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                    <circle cx="8.5" cy="8.5" r="6" stroke="var(--od-text-dim)" strokeWidth="1.4"/>
                    <path d="M13 13L18 18" stroke="var(--od-text-dim)" strokeWidth="1.4" strokeLinecap="round"/>
                    <path d="M6 8.5h5" stroke="var(--od-text-dim)" strokeWidth="1.2" strokeLinecap="round" opacity="0.5"/>
                  </svg>
                </div>
                <div
                  className="ss-heading"
                  style={{ fontSize: 15, fontWeight: 700, color: "var(--od-text-muted)" }}
                >
                  No results
                </div>
                <div style={{ fontSize: 13, color: "var(--od-text-dim)" }}>
                  No documents matched your search.
                </div>
              </div>
            )}

            {/* Results */}
            {showResults && !loading && results.length > 0 && (
              <>
                <div className="ss-count-hint">
                  {results.length} result{results.length !== 1 ? "s" : ""}
                  {locationId ? " · filtered by location" : ""}
                </div>
                {results.map((result, idx) => (
                  <ResultCard
                    key={`${result.document_id}-${idx}`}
                    result={result}
                    idx={idx}
                  />
                ))}
              </>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
