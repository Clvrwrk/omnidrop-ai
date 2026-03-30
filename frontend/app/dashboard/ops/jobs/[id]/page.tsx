"use client";

import { use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api-client";
import type { OpsJobDetail, TriageDetail } from "@/lib/types";

// ─── Design System ─────────────────────────────────────────────────────────────
// "Document Review" — split-screen HITL review surface (Slack deep link target)
// Precision Instrument token set — matches Field Triage and War Room

const DR_CSS = `
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
    --od-success-line:      rgba(76,175,125,0.25);
    --od-error:             #E05252;
    --od-error-dim:         rgba(224,82,82,0.12);
    --od-error-line:        rgba(224,82,82,0.28);
    --od-warn:              #D48A1A;
  }

  .dr-root {
    font-family: 'DM Sans', sans-serif;
    background: var(--od-bg);
    color: var(--od-text);
    min-height: 100vh;
    display: flex;
    flex-direction: column;
  }

  .dr-heading { font-family: 'Syne', sans-serif;   letter-spacing: -0.02em; }
  .dr-mono    { font-family: 'DM Mono', monospace; letter-spacing: 0.03em; }

  /* ── Page header ── */
  .dr-page-header {
    padding: 20px 32px 18px;
    border-bottom: 1px solid var(--od-border);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    flex-wrap: wrap;
    position: relative;
    overflow: hidden;
    flex-shrink: 0;
  }
  .dr-page-header::before {
    content: '';
    position: absolute;
    inset: 0;
    background: radial-gradient(ellipse at 20% 60%, rgba(232,160,32,0.04) 0%, transparent 55%);
    pointer-events: none;
  }

  .dr-back-link {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-family: 'DM Mono', monospace;
    font-size: 11px;
    letter-spacing: 0.06em;
    color: var(--od-text-dim);
    text-decoration: none;
    transition: color 0.15s;
  }
  .dr-back-link:hover { color: var(--od-text-muted); }

  .dr-header-left  { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
  .dr-header-right { display: flex; align-items: center; gap: 10px; flex-shrink: 0; flex-wrap: wrap; }

  /* ── Badges ── */
  .dr-badge {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 3px 9px;
    border-radius: 3px;
    font-family: 'DM Mono', monospace;
    font-size: 10px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    white-space: nowrap;
    flex-shrink: 0;
  }
  .dr-badge-dot {
    width: 4px; height: 4px;
    border-radius: 50%;
    background: currentColor;
    flex-shrink: 0;
  }
  .dr-badge-amber {
    background: var(--od-amber-glow-strong);
    border: 1px solid var(--od-amber-line);
    color: var(--od-amber);
  }
  .dr-badge-success {
    background: var(--od-success-dim);
    border: 1px solid var(--od-success-line);
    color: var(--od-success);
  }
  .dr-badge-error {
    background: var(--od-error-dim);
    border: 1px solid var(--od-error-line);
    color: var(--od-error);
  }
  .dr-badge-neutral {
    background: rgba(255,255,255,0.04);
    border: 1px solid var(--od-border);
    color: var(--od-text-muted);
  }
  .dr-score-badge {
    display: inline-flex;
    align-items: center;
    padding: 3px 9px;
    border-radius: 3px;
    font-family: 'DM Mono', monospace;
    font-size: 11px;
    letter-spacing: 0.06em;
    font-weight: 500;
    flex-shrink: 0;
  }

  /* ── Split screen body ── */
  .dr-split {
    display: grid;
    grid-template-columns: 1fr 420px;
    flex: 1;
    min-height: 0;
    overflow: hidden;
  }
  @media (max-width: 900px) {
    .dr-split {
      grid-template-columns: 1fr;
      overflow: auto;
    }
  }

  /* ── Left panel — Document viewer ── */
  .dr-left {
    border-right: 1px solid var(--od-border);
    display: flex;
    flex-direction: column;
    overflow: hidden;
    min-height: 0;
  }
  .dr-viewer-header {
    padding: 14px 24px;
    border-bottom: 1px solid var(--od-border);
    background: var(--od-surface);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    flex-shrink: 0;
  }
  .dr-viewer-body {
    flex: 1;
    overflow: auto;
    background: var(--od-bg);
    position: relative;
  }
  .dr-viewer-iframe {
    width: 100%;
    height: 100%;
    min-height: 600px;
    border: none;
    display: block;
    background: #fff;
  }
  .dr-viewer-img {
    max-width: 100%;
    display: block;
    margin: 0 auto;
  }
  .dr-viewer-no-url {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 300px;
    gap: 10px;
    color: var(--od-text-dim);
    text-align: center;
  }

  /* ── Document metadata strip ── */
  .dr-meta-strip {
    border-top: 1px solid var(--od-border);
    background: var(--od-surface);
    padding: 12px 24px;
    display: flex;
    gap: 28px;
    flex-wrap: wrap;
    flex-shrink: 0;
  }
  .dr-meta-item {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .dr-meta-label {
    font-family: 'DM Mono', monospace;
    font-size: 9px;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--od-text-dim);
  }
  .dr-meta-value {
    font-family: 'DM Mono', monospace;
    font-size: 12px;
    color: var(--od-text);
  }

  /* ── Right panel — Analysis + Actions ── */
  .dr-right {
    overflow-y: auto;
    padding: 24px;
    display: flex;
    flex-direction: column;
    gap: 16px;
    background: var(--od-surface);
  }

  /* ── Callout box ── */
  .dr-callout {
    background: var(--od-amber-glow);
    border: 1px solid var(--od-amber-line);
    border-radius: 6px;
    padding: 14px 16px;
  }
  .dr-callout-label {
    font-family: 'DM Mono', monospace;
    font-size: 9px;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--od-amber-dim);
    margin-bottom: 6px;
    display: block;
  }
  .dr-callout-text {
    font-size: 13px;
    color: var(--od-text);
    line-height: 1.55;
  }

  /* ── Section card ── */
  .dr-section {
    background: var(--od-surface-2);
    border: 1px solid var(--od-border);
    border-radius: 6px;
    overflow: hidden;
  }
  .dr-section-header {
    padding: 10px 14px;
    border-bottom: 1px solid var(--od-border);
    display: flex;
    align-items: center;
    justify-content: space-between;
    cursor: pointer;
    user-select: none;
    transition: background 0.12s;
  }
  .dr-section-header:hover { background: var(--od-surface-3); }
  .dr-section-title {
    font-family: 'DM Mono', monospace;
    font-size: 10px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--od-text-muted);
  }
  .dr-section-chevron {
    color: var(--od-text-dim);
    transition: transform 0.2s;
    flex-shrink: 0;
  }
  .dr-section-chevron-open { transform: rotate(180deg); }
  .dr-section-body {
    padding: 14px;
  }

  /* ── Confidence table ── */
  .dr-conf-table {
    width: 100%;
    border-collapse: collapse;
  }
  .dr-conf-table th {
    font-family: 'DM Mono', monospace;
    font-size: 9px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--od-text-dim);
    font-weight: 400;
    padding: 4px 8px;
    text-align: left;
    border-bottom: 1px solid var(--od-border);
  }
  .dr-conf-table td {
    font-family: 'DM Mono', monospace;
    font-size: 11px;
    color: var(--od-text-muted);
    padding: 6px 8px;
    border-bottom: 1px solid rgba(37,40,37,0.5);
    vertical-align: top;
  }
  .dr-conf-table tr:last-child td { border-bottom: none; }
  .dr-conf-pill {
    display: inline-flex;
    align-items: center;
    padding: 1px 6px;
    border-radius: 2px;
    font-size: 10px;
    white-space: nowrap;
  }
  .dr-conf-high   { background: var(--od-success-dim);  border: 1px solid var(--od-success-line); color: var(--od-success); }
  .dr-conf-medium { background: var(--od-amber-glow);   border: 1px solid var(--od-amber-line);   color: var(--od-amber); }
  .dr-conf-low    { background: var(--od-error-dim);    border: 1px solid var(--od-error-line);   color: var(--od-error); }

  /* ── Action controls ── */
  .dr-actions {
    background: var(--od-surface-2);
    border: 1px solid var(--od-border);
    border-radius: 6px;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .dr-actions-title {
    font-family: 'DM Mono', monospace;
    font-size: 10px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--od-text-muted);
    margin-bottom: 4px;
    display: block;
  }
  .dr-action-row {
    display: flex;
    gap: 8px;
  }
  .dr-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 5px;
    padding: 8px 16px;
    border-radius: 4px;
    font-family: 'DM Mono', monospace;
    font-size: 11px;
    letter-spacing: 0.06em;
    cursor: pointer;
    transition: background 0.15s, border-color 0.15s, opacity 0.15s;
    border: 1px solid transparent;
    white-space: nowrap;
  }
  .dr-btn:disabled {
    opacity: 0.35;
    cursor: not-allowed;
  }
  .dr-btn-confirm {
    background: var(--od-success);
    color: #0D0F0E;
    font-weight: 500;
    flex: 1;
  }
  .dr-btn-confirm:hover:not(:disabled) { background: #5cbf8c; }
  .dr-btn-reject {
    background: transparent;
    border-color: var(--od-error-line);
    color: var(--od-error);
    flex: 1;
  }
  .dr-btn-reject:hover:not(:disabled) { background: var(--od-error-dim); }
  .dr-btn-submit {
    background: var(--od-amber);
    color: #0D0F0E;
    font-weight: 500;
    align-self: flex-start;
    padding: 7px 16px;
  }
  .dr-btn-submit:hover:not(:disabled) { background: #f0aa28; }

  .dr-divider {
    height: 1px;
    background: var(--od-border);
    width: 100%;
  }

  .dr-correct-label {
    font-family: 'DM Mono', monospace;
    font-size: 10px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--od-text-muted);
    display: block;
    margin-bottom: 6px;
  }
  .dr-textarea {
    width: 100%;
    background: var(--od-surface-3);
    border: 1px solid var(--od-border);
    border-radius: 4px;
    color: var(--od-text);
    font-family: 'DM Sans', sans-serif;
    font-size: 13px;
    line-height: 1.5;
    padding: 10px 12px;
    resize: vertical;
    outline: none;
    transition: border-color 0.15s;
    min-height: 80px;
    box-sizing: border-box;
  }
  .dr-textarea::placeholder { color: var(--od-text-dim); }
  .dr-textarea:focus { border-color: var(--od-amber-dim); }

  /* ── Success state ── */
  .dr-success-banner {
    background: var(--od-success-dim);
    border: 1px solid var(--od-success-line);
    border-radius: 6px;
    padding: 14px 16px;
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .dr-success-text {
    font-size: 13px;
    color: var(--od-success);
    flex: 1;
  }
  .dr-return-link {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 5px 12px;
    border-radius: 4px;
    border: 1px solid var(--od-success-line);
    background: transparent;
    color: var(--od-success);
    font-family: 'DM Mono', monospace;
    font-size: 11px;
    letter-spacing: 0.06em;
    text-decoration: none;
    transition: background 0.15s;
    white-space: nowrap;
  }
  .dr-return-link:hover { background: var(--od-success-dim); }

  /* ── Error banner ── */
  .dr-error-banner {
    background: var(--od-error-dim);
    border: 1px solid var(--od-error-line);
    border-radius: 6px;
    padding: 12px 16px;
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    color: var(--od-error);
  }

  /* ── Skeleton shimmer ── */
  @keyframes skeletonShimmer {
    0%   { background-position: -200% 0; }
    100% { background-position:  200% 0; }
  }
  .dr-skeleton {
    background: linear-gradient(90deg, var(--od-border) 25%, var(--od-border-bright) 50%, var(--od-border) 75%);
    background-size: 200% 100%;
    animation: skeletonShimmer 1.6s ease-in-out infinite;
    border-radius: 3px;
  }

  /* ── Spinner ── */
  @keyframes spin { to { transform: rotate(360deg); } }
  .dr-spinner {
    width: 12px; height: 12px;
    border: 1.5px solid currentColor;
    border-top-color: transparent;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    opacity: 0.7;
    flex-shrink: 0;
  }
`;

// ─── Helpers ──────────────────────────────────────────────────────────────────

function isPdf(url: string): boolean {
  try {
    const u = new URL(url);
    return u.pathname.toLowerCase().endsWith(".pdf");
  } catch {
    return url.toLowerCase().includes(".pdf");
  }
}

function confClass(confidence: number): string {
  if (confidence >= 0.8) return "dr-conf-high";
  if (confidence >= 0.5) return "dr-conf-medium";
  return "dr-conf-low";
}

function confLabel(confidence: number): string {
  if (confidence >= 0.8) return `${Math.round(confidence * 100)}%  High`;
  if (confidence >= 0.5) return `${Math.round(confidence * 100)}%  Med`;
  return `${Math.round(confidence * 100)}%  Low`;
}

function formatKey(key: string): string {
  return key.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
}

function formatValue(val: unknown): string {
  if (val === null || val === undefined) return "—";
  if (typeof val === "number") {
    return val.toLocaleString("en-US", { maximumFractionDigits: 2 });
  }
  return String(val);
}

function scoreColorStyle(score: number | null): { color: string; bg: string; border: string } {
  if (score === null) return { color: "var(--od-text-dim)", bg: "rgba(255,255,255,0.03)", border: "var(--od-border)" };
  if (score >= 80) return { color: "var(--od-success)", bg: "var(--od-success-dim)", border: "var(--od-success-line)" };
  if (score >= 40) return { color: "var(--od-amber)",   bg: "var(--od-amber-glow)",   border: "var(--od-amber-line)" };
  return { color: "var(--od-error)", bg: "var(--od-error-dim)", border: "var(--od-error-line)" };
}

function statusBadgeClass(status: string): string {
  if (status === "confirmed") return "dr-badge dr-badge-success";
  if (status === "rejected")  return "dr-badge dr-badge-error";
  return "dr-badge dr-badge-amber";
}

function statusLabel(status: string): string {
  if (status === "confirmed") return "Confirmed";
  if (status === "rejected")  return "Rejected";
  return "Needs Clarity";
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      className={`dr-section-chevron${open ? " dr-section-chevron-open" : ""}`}
      width="12"
      height="12"
      viewBox="0 0 12 12"
      fill="none"
    >
      <path d="M2 4.5l4 4 4-4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function CollapsibleSection({
  title,
  defaultOpen = true,
  children,
}: {
  title: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="dr-section">
      <div className="dr-section-header" onClick={() => setOpen(o => !o)}>
        <span className="dr-section-title">{title}</span>
        <Chevron open={open} />
      </div>
      {open && <div className="dr-section-body">{children}</div>}
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

type ActionState = "idle" | "confirming" | "rejecting" | "correcting" | "done";

export default function JobReviewPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);

  // ── Data state
  const [job,    setJob]    = useState<OpsJobDetail | null>(null);
  const [triage, setTriage] = useState<TriageDetail | null>(null);
  const [loadingJob,    setLoadingJob]    = useState(true);
  const [loadingTriage, setLoadingTriage] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  // ── Action state
  const [actionState, setActionState]   = useState<ActionState>("idle");
  const [actionError, setActionError]   = useState<string | null>(null);
  const [correction,  setCorrection]    = useState("");
  const [actionLabel, setActionLabel]   = useState<string>("");

  // ── Fetch job metadata (context score, clarification question, etc.)
  const fetchJob = useCallback(async () => {
    setLoadingJob(true);
    try {
      const res = await api.getJobDetail(id);
      setJob(res);
    } catch (e) {
      if (e instanceof ApiError) setLoadError(e.message);
    } finally {
      setLoadingJob(false);
    }
  }, [id]);

  // ── Fetch triage detail (signed URL + extracted fields)
  const fetchTriage = useCallback(async () => {
    setLoadingTriage(true);
    try {
      const res = await api.getTriageDetail(id);
      setTriage(res);
    } catch {
      // Non-fatal — triage record may not exist yet (e.g., still processing)
    } finally {
      setLoadingTriage(false);
    }
  }, [id]);

  useEffect(() => {
    fetchJob();
    fetchTriage();
  }, [fetchJob, fetchTriage]);

  // ── Action handlers

  async function handleConfirm() {
    setActionState("confirming");
    setActionError(null);
    try {
      await api.patchTriage(id, { action: "confirm" });
      setActionLabel("Document confirmed. The extraction has been accepted.");
      setActionState("done");
      await Promise.allSettled([fetchJob(), fetchTriage()]);
    } catch (e) {
      if (e instanceof ApiError) setActionError(e.message);
      setActionState("idle");
    }
  }

  async function handleReject() {
    setActionState("rejecting");
    setActionError(null);
    try {
      await api.patchTriage(id, { action: "reject" });
      setActionLabel("Document rejected and removed from the queue.");
      setActionState("done");
      await Promise.allSettled([fetchJob(), fetchTriage()]);
    } catch (e) {
      if (e instanceof ApiError) setActionError(e.message);
      setActionState("idle");
    }
  }

  async function handleCorrect() {
    if (!correction.trim()) return;
    setActionState("correcting");
    setActionError(null);
    try {
      await api.patchTriage(id, { action: "correct", corrections: { notes: correction.trim() } });
      setActionLabel("Correction submitted. The document will be reprocessed.");
      setActionState("done");
      setCorrection("");
      await Promise.allSettled([fetchJob(), fetchTriage()]);
    } catch (e) {
      if (e instanceof ApiError) setActionError(e.message);
      setActionState("idle");
    }
  }

  const busy = actionState !== "idle" && actionState !== "done";

  // ── Derived display values
  const loading = loadingJob && loadingTriage;
  const docUrl  = triage?.document_url ?? null;
  const showPdf = docUrl ? isPdf(docUrl) : false;

  const scoreStyle = scoreColorStyle(job?.context_score ?? null);

  const extractionEntries: Array<[string, { value: unknown; confidence: number }]> = job?.extraction
    ? (Object.entries(job.extraction) as Array<[string, { value: unknown; confidence: number }]>)
    : [];

  // ── Full-page loading skeleton
  if (loading) {
    return (
      <>
        <style dangerouslySetInnerHTML={{ __html: DR_CSS }} />
        <div className="dr-root">
          <div className="dr-page-header">
            <div className="dr-skeleton" style={{ width: 80, height: 12 }} />
            <div style={{ display: "flex", gap: 8 }}>
              <div className="dr-skeleton" style={{ width: 60, height: 20, borderRadius: 3 }} />
              <div className="dr-skeleton" style={{ width: 90, height: 20, borderRadius: 3 }} />
            </div>
          </div>
          <div className="dr-split">
            <div className="dr-left" style={{ alignItems: "center", justifyContent: "center" }}>
              <div className="dr-skeleton" style={{ width: "80%", height: 500, borderRadius: 4 }} />
            </div>
            <div className="dr-right">
              {[1, 2, 3].map(i => (
                <div key={i} className="dr-skeleton" style={{ height: i === 1 ? 80 : 120, borderRadius: 6 }} />
              ))}
            </div>
          </div>
        </div>
      </>
    );
  }

  // ── Top-level load error
  if (loadError) {
    return (
      <>
        <style dangerouslySetInnerHTML={{ __html: DR_CSS }} />
        <div className="dr-root" style={{ padding: 32 }}>
          <Link href="/dashboard/ops" className="dr-back-link" style={{ marginBottom: 20, display: "inline-flex" }}>
            <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
              <path d="M7 2L3 5l4 3" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            Back to queue
          </Link>
          <div className="dr-error-banner" style={{ marginTop: 12 }}>
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <circle cx="7" cy="7" r="6" stroke="currentColor" strokeWidth="1.2" />
              <path d="M7 4.5v3M7 9v.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
            </svg>
            {loadError}
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      <style dangerouslySetInnerHTML={{ __html: DR_CSS }} />

      <div
        className="dr-root"
        style={{
          backgroundImage:
            "radial-gradient(ellipse at 80% 5%, rgba(232,160,32,0.03) 0%, transparent 50%)",
          minHeight: "100vh",
        }}
      >
        {/* ── Page Header ── */}
        <div className="dr-page-header">
          <div className="dr-header-left">
            {/* Back nav */}
            <Link href="/dashboard/ops" className="dr-back-link">
              <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                <path d="M7 2L3 5l4 3" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              Field Triage
            </Link>

            {/* Filename + vendor */}
            <div style={{ display: "flex", alignItems: "baseline", gap: 10, minWidth: 0 }}>
              <h1
                className="dr-heading"
                style={{ fontSize: 20, fontWeight: 700, color: "var(--od-text)", margin: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                title={job?.file_name ?? ""}
              >
                {job?.file_name ?? "Document Review"}
              </h1>
              {job?.location_name && (
                <span className="dr-mono" style={{ fontSize: 12, color: "var(--od-text-dim)", flexShrink: 0 }}>
                  {job.location_name}
                </span>
              )}
            </div>
          </div>

          <div className="dr-header-right">
            {/* Context score badge */}
            {job && (
              <span
                className="dr-score-badge"
                style={{ color: scoreStyle.color, background: scoreStyle.bg, border: `1px solid ${scoreStyle.border}` }}
              >
                Context {job.context_score ?? "—"}
              </span>
            )}

            {/* Status badge */}
            {job && (
              <span className={statusBadgeClass(job.triage_status)}>
                <span className="dr-badge-dot" />
                {statusLabel(job.triage_status)}
              </span>
            )}
          </div>
        </div>

        {/* ── Split screen ── */}
        <div className="dr-split" style={{ flex: 1, minHeight: "calc(100vh - 90px)" }}>

          {/* ── LEFT: Document viewer ── */}
          <div className="dr-left">
            {/* Viewer toolbar */}
            <div className="dr-viewer-header">
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <rect x="2" y="1" width="8" height="12" rx="1" stroke="var(--od-amber)" strokeWidth="1.2" />
                  <path d="M4 5h6M4 7.5h6M4 10h3" stroke="var(--od-amber)" strokeWidth="1" strokeLinecap="round" opacity="0.6" />
                  <path d="M8 1v3h4" stroke="var(--od-amber)" strokeWidth="1.2" strokeLinejoin="round" opacity="0.5" />
                </svg>
                <span className="dr-mono" style={{ fontSize: 11, color: "var(--od-text-muted)", letterSpacing: "0.06em" }}>
                  Document Viewer
                </span>
              </div>
              {docUrl && (
                <a
                  href={docUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="dr-back-link"
                  style={{ fontSize: 10 }}
                >
                  Open original
                  <svg width="9" height="9" viewBox="0 0 9 9" fill="none">
                    <path d="M2 1h6v6M8 1L1 8" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </a>
              )}
            </div>

            {/* Viewer body */}
            <div className="dr-viewer-body">
              {!docUrl ? (
                <div className="dr-viewer-no-url">
                  <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
                    <rect x="6" y="3" width="18" height="26" rx="2" stroke="var(--od-text-dim)" strokeWidth="1.4" />
                    <path d="M10 11h12M10 15h12M10 19h8" stroke="var(--od-text-dim)" strokeWidth="1.2" strokeLinecap="round" opacity="0.5" />
                  </svg>
                  <span className="dr-mono" style={{ fontSize: 11, color: "var(--od-text-dim)" }}>
                    {loadingTriage ? "Loading document…" : "No document URL available"}
                  </span>
                </div>
              ) : showPdf ? (
                <iframe
                  src={docUrl}
                  title={job?.file_name ?? "Document"}
                  className="dr-viewer-iframe"
                  style={{ minHeight: "calc(100vh - 190px)" }}
                />
              ) : (
                <img
                  src={docUrl}
                  alt={job?.file_name ?? "Document"}
                  className="dr-viewer-img"
                />
              )}
            </div>

            {/* Metadata strip — extracted values */}
            {(job || triage) && (
              <div className="dr-meta-strip">
                {triage?.extraction?.vendor_name?.value && (
                  <div className="dr-meta-item">
                    <span className="dr-meta-label">Vendor</span>
                    <span className="dr-meta-value">{String(triage.extraction.vendor_name.value)}</span>
                  </div>
                )}
                {triage?.extraction?.invoice_number?.value && (
                  <div className="dr-meta-item">
                    <span className="dr-meta-label">Invoice #</span>
                    <span className="dr-meta-value">{String(triage.extraction.invoice_number.value)}</span>
                  </div>
                )}
                {triage?.extraction?.invoice_date?.value && (
                  <div className="dr-meta-item">
                    <span className="dr-meta-label">Date</span>
                    <span className="dr-meta-value">{String(triage.extraction.invoice_date.value)}</span>
                  </div>
                )}
                {triage?.extraction?.total?.value !== null && triage?.extraction?.total?.value !== undefined && (
                  <div className="dr-meta-item">
                    <span className="dr-meta-label">Total</span>
                    <span className="dr-meta-value">
                      ${Number(triage.extraction.total.value).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </span>
                  </div>
                )}
                <div className="dr-meta-item" style={{ marginLeft: "auto" }}>
                  <span className="dr-meta-label">Received</span>
                  <span className="dr-meta-value">
                    {job ? new Date(job.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "—"}
                  </span>
                </div>
              </div>
            )}
          </div>

          {/* ── RIGHT: AI Analysis + Actions ── */}
          <div className="dr-right">

            {/* 1 — Clarification question */}
            {job?.clarification_question && (
              <div className="dr-callout">
                <span className="dr-callout-label">Clarification question</span>
                <p className="dr-callout-text" style={{ margin: 0 }}>
                  {job.clarification_question}
                </p>
              </div>
            )}

            {/* 2 — Document summary (collapsible) */}
            {job?.document_summary && (
              <CollapsibleSection title="Document Summary">
                <p style={{ margin: 0, fontSize: 13, color: "var(--od-text-muted)", lineHeight: 1.6 }}>
                  {job.document_summary}
                </p>
              </CollapsibleSection>
            )}

            {/* 3 — Confidence scores */}
            {extractionEntries.length > 0 && (
              <CollapsibleSection title="Confidence Scores">
                <table className="dr-conf-table">
                  <thead>
                    <tr>
                      <th>Field</th>
                      <th>Value</th>
                      <th>Score</th>
                    </tr>
                  </thead>
                  <tbody>
                    {extractionEntries
                      .filter(([key]) => key !== "line_items")
                      .map(([key, field]) => (
                        <tr key={key}>
                          <td style={{ color: "var(--od-text-dim)" }}>{formatKey(key)}</td>
                          <td style={{ color: "var(--od-text)" }}>{formatValue(field.value)}</td>
                          <td>
                            <span className={`dr-conf-pill ${confClass(field.confidence)}`}>
                              {confLabel(field.confidence)}
                            </span>
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </CollapsibleSection>
            )}

            {/* 4 — Action controls */}
            {actionState === "done" ? (
              /* Success state */
              <div className="dr-success-banner">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <circle cx="8" cy="8" r="7" stroke="var(--od-success)" strokeWidth="1.3" />
                  <path d="M5 8l2.5 2.5 4-4.5" stroke="var(--od-success)" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                <span className="dr-success-text">{actionLabel}</span>
                <Link href="/dashboard/ops" className="dr-return-link">
                  Return to queue
                  <svg width="9" height="9" viewBox="0 0 9 9" fill="none">
                    <path d="M2 4.5h5M5 2l2.5 2.5L5 7" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </Link>
              </div>
            ) : (
              <div className="dr-actions">
                <span className="dr-actions-title">Review Actions</span>

                {/* Action error */}
                {actionError && (
                  <div className="dr-error-banner" style={{ fontSize: 12, padding: "8px 12px" }}>
                    <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                      <circle cx="6" cy="6" r="5" stroke="currentColor" strokeWidth="1.2" />
                      <path d="M6 3.5v3M6 8v.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
                    </svg>
                    {actionError}
                  </div>
                )}

                {/* Confirm + Reject */}
                <div className="dr-action-row">
                  <button
                    className="dr-btn dr-btn-confirm"
                    disabled={busy}
                    onClick={handleConfirm}
                  >
                    {actionState === "confirming" ? (
                      <><div className="dr-spinner" /> Confirming…</>
                    ) : (
                      <>
                        <svg width="11" height="11" viewBox="0 0 11 11" fill="none">
                          <path d="M2 5.5l2.5 2.5 4.5-5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                        Confirm
                      </>
                    )}
                  </button>
                  <button
                    className="dr-btn dr-btn-reject"
                    disabled={busy}
                    onClick={handleReject}
                  >
                    {actionState === "rejecting" ? (
                      <><div className="dr-spinner" /> Rejecting…</>
                    ) : (
                      <>
                        <svg width="11" height="11" viewBox="0 0 11 11" fill="none">
                          <path d="M2.5 2.5l6 6M8.5 2.5l-6 6" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
                        </svg>
                        Reject
                      </>
                    )}
                  </button>
                </div>

                <div className="dr-divider" />

                {/* Correct section */}
                <div>
                  <span className="dr-correct-label">Submit Correction</span>
                  <textarea
                    className="dr-textarea"
                    placeholder="Describe the correction needed — vendor name mismatch, wrong total, illegible field, etc."
                    value={correction}
                    onChange={e => setCorrection(e.target.value)}
                    disabled={busy}
                    rows={3}
                  />
                  <div style={{ marginTop: 8 }}>
                    <button
                      className="dr-btn dr-btn-submit"
                      disabled={busy || !correction.trim()}
                      onClick={handleCorrect}
                    >
                      {actionState === "correcting" ? (
                        <><div className="dr-spinner" /> Submitting…</>
                      ) : (
                        "Submit Correction"
                      )}
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* Routing info */}
            {job?.context_routing && (
              <div style={{ padding: "0 4px" }}>
                <span className="dr-mono" style={{ fontSize: 10, color: "var(--od-text-dim)", letterSpacing: "0.08em" }}>
                  ROUTING · {job.context_routing.toUpperCase()} CONTEXT
                </span>
              </div>
            )}

          </div>
        </div>
      </div>
    </>
  );
}
