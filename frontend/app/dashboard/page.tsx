"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api-client";
import type {
  Job,
  HealthResponse,
  Organization,
} from "@/lib/types";

// ─── Design System ────────────────────────────────────────────────────────────
// "Mission Control" — operational telemetry surface
// Inherits Precision Instrument tokens from /onboarding

const DASH_CSS = `
  @import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Mono:ital,wght@0,300;0,400;0,500;1,300&family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;1,9..40,300&display=swap');

  :root {
    --od-bg: #0D0F0E;
    --od-surface: #141614;
    --od-surface-2: #1A1C1A;
    --od-surface-3: #1F211F;
    --od-border: #252825;
    --od-border-bright: #303530;
    --od-amber: #E8A020;
    --od-amber-dim: #7A5510;
    --od-amber-glow: rgba(232,160,32,0.10);
    --od-amber-glow-strong: rgba(232,160,32,0.18);
    --od-amber-line: rgba(232,160,32,0.30);
    --od-text: #F0EDE6;
    --od-text-muted: #6B7068;
    --od-text-dim: #3D403C;
    --od-success: #4CAF7D;
    --od-success-dim: rgba(76,175,125,0.12);
    --od-error: #E05252;
    --od-error-dim: rgba(224,82,82,0.12);
    --od-warn: #D48A1A;
  }

  .dash-root {
    font-family: 'DM Sans', sans-serif;
    background: var(--od-bg);
    color: var(--od-text);
    min-height: 100vh;
  }

  .dash-heading { font-family: 'Syne', sans-serif; letter-spacing: -0.02em; }
  .dash-mono    { font-family: 'DM Mono', monospace; letter-spacing: 0.03em; }

  /* ── Health strip ── */
  .health-strip {
    display: flex;
    align-items: center;
    gap: 0;
    border-bottom: 1px solid var(--od-border);
    background: var(--od-surface);
    height: 42px;
    padding: 0 24px;
    overflow: hidden;
  }

  .health-cell {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 0 20px;
    border-right: 1px solid var(--od-border);
    height: 100%;
    flex-shrink: 0;
  }
  .health-cell:first-child { padding-left: 0; }
  .health-cell:last-child  { border-right: none; }

  .health-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .health-dot-ok      { background: var(--od-success); }
  .health-dot-error   { background: var(--od-error); }
  .health-dot-pulse   { animation: healthPulse 2s ease-in-out infinite; }

  @keyframes healthPulse {
    0%,100% { box-shadow: 0 0 0 0 rgba(76,175,125,0.5); }
    50%      { box-shadow: 0 0 0 4px rgba(76,175,125,0); }
  }

  /* ── Drop zone ── */
  .drop-zone {
    position: relative;
    border: 1px solid var(--od-border);
    border-radius: 8px;
    overflow: hidden;
    cursor: pointer;
    transition: border-color 0.2s;
    background: var(--od-surface);
  }
  .drop-zone:hover    { border-color: var(--od-amber-dim); }
  .drop-zone-active   { border-color: var(--od-amber) !important; background: var(--od-surface-2); }

  .drop-zone-inner {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-height: 320px;
    gap: 16px;
    padding: 40px;
    position: relative;
    z-index: 1;
  }

  /* Radar sweep */
  .radar-ring {
    position: absolute;
    border-radius: 50%;
    border: 1px solid var(--od-border);
    pointer-events: none;
  }
  .radar-sweep-arm {
    position: absolute;
    width: 50%;
    height: 1px;
    top: 50%;
    left: 50%;
    transform-origin: left center;
    background: linear-gradient(90deg, transparent, var(--od-amber));
    opacity: 0;
    transition: opacity 0.3s;
  }
  .drop-zone:hover .radar-sweep-arm,
  .drop-zone-active .radar-sweep-arm {
    opacity: 1;
    animation: radarSweep 2.4s linear infinite;
  }
  .radar-center {
    width: 8px; height: 8px;
    border-radius: 50%;
    background: var(--od-amber);
    opacity: 0;
    transition: opacity 0.3s;
    position: absolute;
    box-shadow: 0 0 12px var(--od-amber);
  }
  .drop-zone:hover .radar-center,
  .drop-zone-active .radar-center { opacity: 1; }

  @keyframes radarSweep {
    from { transform: rotate(0deg); }
    to   { transform: rotate(360deg); }
  }

  /* Lock-on pulse when file drops */
  @keyframes lockOn {
    0%   { transform: scale(1);   opacity: 1; }
    50%  { transform: scale(1.4); opacity: 0.4; }
    100% { transform: scale(1);   opacity: 1; }
  }
  .lock-on { animation: lockOn 0.5s ease-out; }

  /* crosshair lines */
  .crosshair-h, .crosshair-v {
    position: absolute;
    background: var(--od-border);
    pointer-events: none;
    opacity: 0;
    transition: opacity 0.3s;
  }
  .crosshair-h { width: 100%; height: 1px; top: 50%; left: 0; }
  .crosshair-v { width: 1px; height: 100%; left: 50%; top: 0; }
  .drop-zone:hover .crosshair-h,
  .drop-zone:hover .crosshair-v,
  .drop-zone-active .crosshair-h,
  .drop-zone-active .crosshair-v { opacity: 1; }

  /* ── Upload queue strip ── */
  .upload-row {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 8px 14px;
    border-top: 1px solid var(--od-border);
    background: var(--od-surface-2);
    animation: fadeSlideIn 0.25s ease both;
  }
  @keyframes fadeSlideIn {
    from { opacity: 0; transform: translateY(-6px); }
    to   { opacity: 1; transform: translateY(0); }
  }

  /* ── Quota bar ── */
  .quota-track {
    height: 3px;
    background: var(--od-border);
    border-radius: 2px;
    overflow: hidden;
  }
  .quota-fill {
    height: 100%;
    border-radius: 2px;
    background: var(--od-amber);
    transition: width 0.6s cubic-bezier(0.22,1,0.36,1);
  }
  .quota-fill-warn { background: var(--od-warn); }
  .quota-fill-crit { background: var(--od-error); }

  /* ── Job feed ── */
  .feed-header {
    position: sticky;
    top: 0;
    z-index: 10;
    background: var(--od-bg);
    border-bottom: 1px solid var(--od-border);
    padding: 14px 0 12px;
  }

  .job-card {
    border: 1px solid var(--od-border);
    border-radius: 6px;
    background: var(--od-surface);
    padding: 14px 16px;
    transition: border-color 0.2s, background 0.2s;
    animation: cardAppear 0.3s ease both;
    cursor: default;
  }
  @keyframes cardAppear {
    from { opacity: 0; transform: translateX(8px); }
    to   { opacity: 1; transform: translateX(0); }
  }
  .job-card:hover { border-color: var(--od-border-bright); background: var(--od-surface-2); }
  .job-card-processing { border-color: rgba(232,160,32,0.2); }
  .job-card-complete   { border-color: rgba(76,175,125,0.2); }
  .job-card-failed     { border-color: rgba(224,82,82,0.2); }
  .job-card-bounced    { border-color: rgba(212,138,26,0.2); }

  /* pipeline stage bar */
  .pipeline-bar {
    display: flex;
    gap: 2px;
    margin-top: 10px;
  }
  .pipeline-seg {
    height: 2px;
    border-radius: 1px;
    flex: 1;
    background: var(--od-border);
    transition: background 0.4s;
    position: relative;
    overflow: hidden;
  }
  .pipeline-seg-done    { background: var(--od-success); }
  .pipeline-seg-active  { background: var(--od-amber); }
  .pipeline-seg-active::after {
    content: '';
    position: absolute;
    inset: 0;
    background: linear-gradient(90deg, transparent, rgba(255,255,255,0.4), transparent);
    animation: shimmer 1.2s ease-in-out infinite;
  }
  @keyframes shimmer {
    from { transform: translateX(-100%); }
    to   { transform: translateX(100%); }
  }

  /* status badges */
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
    font-weight: 500;
    flex-shrink: 0;
  }
  .badge-queued     { background: rgba(107,112,104,0.15); color: var(--od-text-muted); border: 1px solid rgba(107,112,104,0.25); }
  .badge-processing { background: var(--od-amber-glow);   color: var(--od-amber);      border: 1px solid var(--od-amber-line); }
  .badge-complete   { background: var(--od-success-dim);  color: var(--od-success);    border: 1px solid rgba(76,175,125,0.25); }
  .badge-failed     { background: var(--od-error-dim);    color: var(--od-error);      border: 1px solid rgba(224,82,82,0.25); }
  .badge-bounced    { background: rgba(212,138,26,0.12);  color: var(--od-warn);       border: 1px solid rgba(212,138,26,0.25); }

  .doc-type-chip {
    display: inline-block;
    padding: 1px 6px;
    border-radius: 2px;
    font-family: 'DM Mono', monospace;
    font-size: 10px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    background: var(--od-surface-3);
    color: var(--od-text-muted);
    border: 1px solid var(--od-border);
  }

  /* poll indicator */
  @keyframes pollBlink {
    0%,100% { opacity: 1; }
    50%      { opacity: 0.25; }
  }
  .poll-dot {
    width: 5px; height: 5px;
    border-radius: 50%;
    background: var(--od-amber);
    animation: pollBlink 2s ease-in-out infinite;
    flex-shrink: 0;
  }

  /* empty state */
  .feed-empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 12px;
    padding: 60px 20px;
    opacity: 0.45;
  }

  /* scroll */
  .feed-scroll { overflow-y: auto; max-height: calc(100vh - 240px); }
  .feed-scroll::-webkit-scrollbar { width: 3px; }
  .feed-scroll::-webkit-scrollbar-track { background: transparent; }
  .feed-scroll::-webkit-scrollbar-thumb { background: var(--od-border-bright); border-radius: 2px; }

  /* page stagger */
  @keyframes staggerIn {
    from { opacity: 0; transform: translateY(10px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  .stagger-1 { animation: staggerIn 0.4s 0.05s ease both; }
  .stagger-2 { animation: staggerIn 0.4s 0.15s ease both; }
  .stagger-3 { animation: staggerIn 0.4s 0.25s ease both; }

  /* error bar */
  .error-bar {
    background: var(--od-error-dim);
    border: 1px solid rgba(224,82,82,0.3);
    border-radius: 4px;
    padding: 10px 14px;
    font-size: 13px;
    color: var(--od-error);
    display: flex;
    align-items: center;
    gap: 8px;
  }
`;

// ─── Constants ────────────────────────────────────────────────────────────────

const POLL_INTERVAL_MS = 5000;

const PIPELINE_STAGES = [
  "Intake",
  "Parse",
  "Score",
  "Extract",
  "Leakage",
] as const;

// Map job status → how many pipeline stages are "done"
function pipelineProgress(status: Job["status"]): number {
  switch (status) {
    case "queued":     return 0;
    case "processing": return 2; // active on stage 3
    case "complete":   return 5;
    case "failed":     return 2;
    case "bounced":    return 2;
    default:           return 0;
  }
}

function formatRelTime(iso: string): string {
  const delta = (Date.now() - new Date(iso).getTime()) / 1000;
  if (delta < 60)   return `${Math.floor(delta)}s ago`;
  if (delta < 3600) return `${Math.floor(delta / 60)}m ago`;
  if (delta < 86400) return `${Math.floor(delta / 3600)}h ago`;
  return new Date(iso).toLocaleDateString();
}

// ─── Health Strip ─────────────────────────────────────────────────────────────

function HealthStrip({ health }: { health: HealthResponse | null }) {
  if (!health) {
    return (
      <div className="health-strip">
        <div className="health-cell">
          <div className="dash-mono" style={{ fontSize: 10, color: "var(--od-text-dim)", letterSpacing: "0.1em" }}>
            SYSTEM — CONNECTING...
          </div>
        </div>
      </div>
    );
  }

  const isHealthy = health.status === "healthy";
  const isDegraded = health.status === "degraded";

  return (
    <div className="health-strip">
      {/* Overall status */}
      <div className="health-cell">
        <div
          className={`health-dot ${isHealthy ? "health-dot-ok health-dot-pulse" : "health-dot-error"}`}
        />
        <div
          className="dash-mono"
          style={{
            fontSize: 10,
            letterSpacing: "0.1em",
            textTransform: "uppercase",
            color: isHealthy ? "var(--od-success)" : isDegraded ? "var(--od-warn)" : "var(--od-error)",
          }}
        >
          {health.status}
        </div>
      </div>

      {/* Celery workers */}
      <div className="health-cell">
        <div className="dash-mono" style={{ fontSize: 10, color: "var(--od-text-dim)", letterSpacing: "0.08em" }}>
          WORKERS
        </div>
        <div className="dash-mono" style={{ fontSize: 11, color: "var(--od-text-muted)" }}>
          {health.checks.celery_workers.active_count}
          <span style={{ color: "var(--od-text-dim)", marginLeft: 4 }}>active</span>
        </div>
      </div>

      {/* Queue depth */}
      <div className="health-cell">
        <div className="dash-mono" style={{ fontSize: 10, color: "var(--od-text-dim)", letterSpacing: "0.08em" }}>
          QUEUE
        </div>
        <div
          className="dash-mono"
          style={{
            fontSize: 11,
            color: health.checks.celery_workers.queue_depth > 50
              ? "var(--od-warn)"
              : "var(--od-text-muted)",
          }}
        >
          {health.checks.celery_workers.queue_depth}
          <span style={{ color: "var(--od-text-dim)", marginLeft: 4 }}>pending</span>
        </div>
      </div>

      {/* DB latency */}
      <div className="health-cell">
        <div className="dash-mono" style={{ fontSize: 10, color: "var(--od-text-dim)", letterSpacing: "0.08em" }}>
          DB
        </div>
        <div
          className="dash-mono"
          style={{
            fontSize: 11,
            color: health.checks.supabase.status === "ok"
              ? "var(--od-text-muted)"
              : "var(--od-error)",
          }}
        >
          {health.checks.supabase.latency_ms}
          <span style={{ color: "var(--od-text-dim)", marginLeft: 2 }}>ms</span>
        </div>
      </div>

      {/* Redis */}
      <div className="health-cell">
        <div className="dash-mono" style={{ fontSize: 10, color: "var(--od-text-dim)", letterSpacing: "0.08em" }}>
          REDIS
        </div>
        <div
          className="dash-mono"
          style={{
            fontSize: 11,
            color: health.checks.redis.status === "ok"
              ? "var(--od-text-muted)"
              : "var(--od-error)",
          }}
        >
          {health.checks.redis.latency_ms}
          <span style={{ color: "var(--od-text-dim)", marginLeft: 2 }}>ms</span>
        </div>
      </div>

      {/* Timestamp — push to right */}
      <div style={{ marginLeft: "auto", paddingLeft: 20 }}>
        <div className="dash-mono" style={{ fontSize: 10, color: "var(--od-text-dim)", letterSpacing: "0.06em" }}>
          {new Date(health.timestamp).toLocaleTimeString()}
        </div>
      </div>
    </div>
  );
}

// ─── Quota Bar ────────────────────────────────────────────────────────────────

function QuotaBar({ org }: { org: Organization | null }) {
  if (!org) return null;

  const used = org.documents_processed ?? 0;
  const max  = org.max_documents ?? 100;
  const pct  = Math.min((used / max) * 100, 100);
  const isCrit = pct >= 90;
  const isWarn = pct >= 70 && !isCrit;

  return (
    <div
      style={{
        border: "1px solid var(--od-border)",
        borderRadius: 6,
        background: "var(--od-surface)",
        padding: "14px 18px",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 10 }}>
        <div className="dash-mono" style={{ fontSize: 10, letterSpacing: "0.1em", color: "var(--od-text-muted)", textTransform: "uppercase" }}>
          Document Quota
        </div>
        <div style={{ display: "flex", alignItems: "baseline", gap: 4 }}>
          <span
            className="dash-mono"
            style={{
              fontSize: 18,
              fontWeight: 500,
              color: isCrit ? "var(--od-error)" : isWarn ? "var(--od-warn)" : "var(--od-text)",
            }}
          >
            {used.toLocaleString()}
          </span>
          <span className="dash-mono" style={{ fontSize: 11, color: "var(--od-text-muted)" }}>
            / {max.toLocaleString()}
          </span>
        </div>
      </div>
      <div className="quota-track">
        <div
          className={`quota-fill ${isCrit ? "quota-fill-crit" : isWarn ? "quota-fill-warn" : ""}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      {isCrit && (
        <div className="dash-mono" style={{ fontSize: 10, color: "var(--od-error)", marginTop: 6, letterSpacing: "0.06em" }}>
          Quota nearly reached — contact sales to upgrade
        </div>
      )}
      {!isCrit && (
        <div className="dash-mono" style={{ fontSize: 10, color: "var(--od-text-dim)", marginTop: 6, letterSpacing: "0.06em" }}>
          {(max - used).toLocaleString()} remaining · {org.plan_tier ?? "free"} plan
        </div>
      )}
    </div>
  );
}

// ─── Upload Row Item ──────────────────────────────────────────────────────────

interface UploadItem {
  id: string;
  name: string;
  size: number;
  state: "uploading" | "queued" | "error";
  jobId?: string;
  errorMsg?: string;
}

function UploadRow({ item }: { item: UploadItem }) {
  function fmt(b: number) {
    if (b < 1024)        return `${b}B`;
    if (b < 1048576)     return `${(b/1024).toFixed(0)}KB`;
    return `${(b/1048576).toFixed(1)}MB`;
  }

  return (
    <div className="upload-row">
      {/* Icon */}
      <div style={{
        width: 28, height: 28, borderRadius: 4, flexShrink: 0,
        background: item.state === "error" ? "var(--od-error-dim)" : "var(--od-amber-glow)",
        border: `1px solid ${item.state === "error" ? "rgba(224,82,82,0.3)" : "var(--od-amber-line)"}`,
        display: "flex", alignItems: "center", justifyContent: "center",
      }}>
        {item.state === "uploading" ? (
          <div style={{
            width: 12, height: 12, borderRadius: "50%",
            border: "1.5px solid var(--od-amber-dim)",
            borderTopColor: "var(--od-amber)",
            animation: "radarSweep 0.7s linear infinite",
          }} />
        ) : item.state === "error" ? (
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
            <path d="M6 4v3M6 8.5v.5" stroke="var(--od-error)" strokeWidth="1.3" strokeLinecap="round"/>
          </svg>
        ) : (
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
            <path d="M2.5 6.5l2.5 2.5 5-6" stroke="var(--od-amber)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        )}
      </div>

      {/* Name + meta */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="dash-mono" style={{ fontSize: 12, color: "var(--od-text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {item.name}
        </div>
        <div className="dash-mono" style={{ fontSize: 10, color: "var(--od-text-dim)", marginTop: 1 }}>
          {item.state === "error"
            ? item.errorMsg ?? "Upload failed"
            : item.state === "uploading"
              ? `${fmt(item.size)} — uploading...`
              : `${fmt(item.size)} — job ${item.jobId?.slice(0,8)}...`
          }
        </div>
      </div>

      {/* State badge */}
      <div className={`status-badge ${
        item.state === "uploading" ? "badge-processing" :
        item.state === "error"     ? "badge-failed" :
        "badge-queued"
      }`}>
        {item.state === "uploading" ? "Sending" : item.state === "error" ? "Error" : "Queued"}
      </div>
    </div>
  );
}

// ─── Drop Zone ────────────────────────────────────────────────────────────────

function DropZone({
  org,
  onUploaded,
}: {
  org: Organization | null;
  onUploaded: () => void;
}) {
  const [dragOver, setDragOver] = useState(false);
  const [lockAnim, setLockAnim] = useState(false);
  const [uploads, setUploads] = useState<UploadItem[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function processFile(file: File) {
    if (!org) return;

    const id = `${Date.now()}-${Math.random()}`;
    const item: UploadItem = { id, name: file.name, size: file.size, state: "uploading" };
    setUploads(prev => [item, ...prev.slice(0, 9)]);

    try {
      const res = await api.uploadDocument(file, org.organization_id);
      setUploads(prev => prev.map(u =>
        u.id === id ? { ...u, state: "queued", jobId: res.job_id } : u
      ));
      onUploaded();
    } catch (err) {
      const msg = err instanceof ApiError ? err.body : "Upload failed";
      setUploads(prev => prev.map(u =>
        u.id === id ? { ...u, state: "error", errorMsg: msg } : u
      ));
    }
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    setLockAnim(true);
    setTimeout(() => setLockAnim(false), 600);
    Array.from(e.dataTransfer.files).forEach(processFile);
  }

  function handleInput(e: React.ChangeEvent<HTMLInputElement>) {
    Array.from(e.target.files ?? []).forEach(processFile);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  const RADAR_SIZE = 200;

  return (
    <div
      className={`drop-zone ${dragOver ? "drop-zone-active" : ""}`}
      onDragOver={e => { e.preventDefault(); setDragOver(true); }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
      onClick={() => fileInputRef.current?.click()}
    >
      {/* Crosshair */}
      <div className="crosshair-h" />
      <div className="crosshair-v" />

      {/* Radar rings + sweep — centered absolutely */}
      <div style={{
        position: "absolute",
        top: "50%", left: "50%",
        transform: "translate(-50%, -50%)",
        width: RADAR_SIZE, height: RADAR_SIZE,
        pointerEvents: "none",
      }}>
        {[1, 0.67, 0.4].map((scale, i) => (
          <div
            key={i}
            className="radar-ring"
            style={{
              width: RADAR_SIZE * scale,
              height: RADAR_SIZE * scale,
              top: "50%", left: "50%",
              transform: "translate(-50%, -50%)",
              opacity: 0.4 - i * 0.1,
            }}
          />
        ))}
        {/* Sweep arm pivots from center */}
        <div style={{ position: "absolute", top: "50%", left: "50%", width: 0, height: 0 }}>
          <div
            className="radar-sweep-arm"
            style={{ width: RADAR_SIZE * 0.5 }}
          />
        </div>
        <div
          className={`radar-center ${lockAnim ? "lock-on" : ""}`}
          style={{ top: "50%", left: "50%", transform: "translate(-50%, -50%)" }}
        />
      </div>

      {/* Center content */}
      <div className="drop-zone-inner">
        <div style={{ textAlign: "center", position: "relative" }}>
          {/* Upload icon */}
          <div style={{
            width: 52, height: 52, borderRadius: 8, margin: "0 auto 14px",
            background: dragOver ? "var(--od-amber-glow-strong)" : "var(--od-surface-2)",
            border: `1px solid ${dragOver ? "var(--od-amber-line)" : "var(--od-border)"}`,
            display: "flex", alignItems: "center", justifyContent: "center",
            transition: "all 0.2s",
          }}>
            <svg width="22" height="22" viewBox="0 0 22 22" fill="none">
              <path
                d="M11 15V7M7 11l4-4 4 4"
                stroke={dragOver ? "var(--od-amber)" : "var(--od-text-muted)"}
                strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"
              />
              <path
                d="M4 17h14"
                stroke={dragOver ? "var(--od-amber)" : "var(--od-text-dim)"}
                strokeWidth="1.3" strokeLinecap="round" opacity="0.5"
              />
            </svg>
          </div>

          <div
            className="dash-heading"
            style={{
              fontSize: 22,
              fontWeight: 700,
              color: dragOver ? "var(--od-amber)" : "var(--od-text)",
              marginBottom: 6,
              transition: "color 0.2s",
            }}
          >
            {dragOver ? "Release to drop" : "Omni-Drop"}
          </div>
          <div style={{ fontSize: 13, color: "var(--od-text-muted)", marginBottom: 14 }}>
            {dragOver
              ? "Files will be queued for AI processing"
              : "Drag invoices, proposals, POs, or any document"}
          </div>
          <div
            className="dash-mono"
            style={{
              fontSize: 10,
              color: "var(--od-text-dim)",
              letterSpacing: "0.12em",
              textTransform: "uppercase",
            }}
          >
            PDF · PNG · JPG · XLSX · CSV
          </div>
        </div>

        {!org && (
          <div className="dash-mono" style={{ fontSize: 11, color: "var(--od-warn)", letterSpacing: "0.06em" }}>
            Loading organization...
          </div>
        )}
      </div>

      {/* Upload queue — stacked below the zone content */}
      {uploads.length > 0 && (
        <div onClick={e => e.stopPropagation()}>
          {uploads.map(item => (
            <UploadRow key={item.id} item={item} />
          ))}
        </div>
      )}

      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept=".pdf,.png,.jpg,.jpeg,.xlsx,.xls,.csv"
        style={{ display: "none" }}
        onChange={handleInput}
      />
    </div>
  );
}

// ─── Pipeline Stage Bar ───────────────────────────────────────────────────────

function PipelineBar({ job }: { job: Job }) {
  if (job.status === "queued") return null;

  const done   = pipelineProgress(job.status);
  const isFail = job.status === "failed" || job.status === "bounced";

  return (
    <div>
      <div className="pipeline-bar">
        {PIPELINE_STAGES.map((stage, i) => {
          const segDone   = i < done;
          const segActive = i === done && !isFail && job.status !== "complete";
          return (
            <div
              key={stage}
              className={`pipeline-seg ${segDone ? "pipeline-seg-done" : ""} ${segActive ? "pipeline-seg-active" : ""} ${isFail && i === done - 1 ? "!bg-[var(--od-error)]" : ""}`}
              title={stage}
            />
          );
        })}
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4 }}>
        {PIPELINE_STAGES.map((stage, i) => (
          <div
            key={stage}
            className="dash-mono"
            style={{
              fontSize: 9,
              letterSpacing: "0.06em",
              color: i < done
                ? "var(--od-success)"
                : i === done && !isFail && job.status !== "complete"
                  ? "var(--od-amber)"
                  : "var(--od-text-dim)",
              textTransform: "uppercase",
            }}
          >
            {stage}
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Job Card ─────────────────────────────────────────────────────────────────

function JobCard({ job }: { job: Job }) {
  const cardClass = `job-card ${
    job.status === "processing" ? "job-card-processing" :
    job.status === "complete"   ? "job-card-complete" :
    job.status === "failed"     ? "job-card-failed" :
    job.status === "bounced"    ? "job-card-bounced" : ""
  }`;

  return (
    <div className={cardClass}>
      {/* Top row */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 8 }}>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div
            className="dash-mono"
            style={{
              fontSize: 12,
              color: "var(--od-text)",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              marginBottom: 4,
            }}
          >
            {job.file_name ?? `job_${job.job_id.slice(0,8)}`}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
            {job.document_type && (
              <span className="doc-type-chip">{job.document_type}</span>
            )}
            {job.location_name && (
              <span className="dash-mono" style={{ fontSize: 10, color: "var(--od-text-dim)" }}>
                {job.location_name}
              </span>
            )}
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 4, flexShrink: 0 }}>
          <div className={`status-badge badge-${job.status}`}>
            {job.status === "processing" && (
              <div style={{
                width: 5, height: 5, borderRadius: "50%",
                background: "var(--od-amber)",
                animation: "pollBlink 1s ease-in-out infinite",
              }} />
            )}
            {job.status}
          </div>
          <div className="dash-mono" style={{ fontSize: 9, color: "var(--od-text-dim)", letterSpacing: "0.06em" }}>
            {formatRelTime(job.created_at)}
          </div>
        </div>
      </div>

      {/* Pipeline progress */}
      <PipelineBar job={job} />

      {/* Error message */}
      {job.error_message && (
        <div
          className="dash-mono"
          style={{
            fontSize: 10,
            color: "var(--od-error)",
            marginTop: 8,
            padding: "6px 8px",
            background: "var(--od-error-dim)",
            borderRadius: 3,
            letterSpacing: "0.04em",
          }}
        >
          {job.error_message}
        </div>
      )}
    </div>
  );
}

// ─── Job Feed ─────────────────────────────────────────────────────────────────

function JobFeed({
  jobs,
  polling,
  total,
}: {
  jobs: Job[];
  polling: boolean;
  total: number;
}) {
  const processingCount = jobs.filter(j => j.status === "processing").length;
  const completeCount   = jobs.filter(j => j.status === "complete").length;
  const failedCount     = jobs.filter(j => j.status === "failed" || j.status === "bounced").length;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* Sticky header */}
      <div className="feed-header">
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div
              className="dash-heading"
              style={{ fontSize: 16, fontWeight: 700, color: "var(--od-text)" }}
            >
              Pipeline Feed
            </div>
            {polling && <div className="poll-dot" title="Live — polling every 5s" />}
          </div>
          <div className="dash-mono" style={{ fontSize: 10, color: "var(--od-text-dim)", letterSpacing: "0.08em" }}>
            {total} total
          </div>
        </div>

        {/* Mini stats row */}
        <div style={{ display: "flex", gap: 16 }}>
          {[
            { label: "Running",  val: processingCount, color: "var(--od-amber)" },
            { label: "Complete", val: completeCount,   color: "var(--od-success)" },
            { label: "Failed",   val: failedCount,     color: "var(--od-error)" },
          ].map(s => (
            <div key={s.label} style={{ display: "flex", alignItems: "baseline", gap: 4 }}>
              <span className="dash-mono" style={{ fontSize: 14, fontWeight: 500, color: s.color }}>
                {s.val}
              </span>
              <span className="dash-mono" style={{ fontSize: 9, color: "var(--od-text-dim)", letterSpacing: "0.08em", textTransform: "uppercase" }}>
                {s.label}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Scrollable job list */}
      <div className="feed-scroll" style={{ flex: 1, paddingTop: 12 }}>
        {jobs.length === 0 ? (
          <div className="feed-empty">
            <svg width="40" height="40" viewBox="0 0 40 40" fill="none">
              <rect x="8" y="10" width="24" height="20" rx="2" stroke="currentColor" strokeWidth="1.2"/>
              <path d="M14 17h12M14 21h8" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
            </svg>
            <div className="dash-mono" style={{ fontSize: 11, letterSpacing: "0.08em", textTransform: "uppercase" }}>
              No jobs yet
            </div>
            <div style={{ fontSize: 12, textAlign: "center", maxWidth: 180 }}>
              Drop a document to start the pipeline
            </div>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {jobs.map(job => (
              <JobCard key={job.job_id} job={job} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const [jobs,    setJobs]    = useState<Job[]>([]);
  const [total,   setTotal]   = useState(0);
  const [health,  setHealth]  = useState<HealthResponse | null>(null);
  const [org,     setOrg]     = useState<Organization | null>(null);
  const [polling, setPolling] = useState(false);
  const [error,   setError]   = useState<string | null>(null);
  const [triggerRefresh, setTriggerRefresh] = useState(0);

  // Load org once
  useEffect(() => {
    api.getOrganization().then(setOrg).catch(() => {});
  }, []);

  // Polling loop: jobs + health every 5s
  const fetchData = useCallback(async () => {
    setPolling(true);
    try {
      const [jobsRes, healthRes] = await Promise.all([
        api.getJobs({ limit: 50 }),
        api.getHealth(),
      ]);
      setJobs(jobsRes.jobs);
      setTotal(jobsRes.total);
      setHealth(healthRes);
      setError(null);
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    } finally {
      setPolling(false);
    }
  }, []);

  // Initial load + re-fetch when a file is uploaded
  useEffect(() => {
    fetchData();
  }, [fetchData, triggerRefresh]);

  // 5-second polling interval
  useEffect(() => {
    const id = setInterval(fetchData, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [fetchData]);

  return (
    <>
      <style dangerouslySetInnerHTML={{ __html: DASH_CSS }} />

      <div
        className="dash-root"
        style={{
          backgroundImage:
            "radial-gradient(ellipse at 70% 10%, rgba(232,160,32,0.04) 0%, transparent 55%), " +
            "linear-gradient(rgba(37,40,37,0.25) 1px, transparent 1px), " +
            "linear-gradient(90deg, rgba(37,40,37,0.25) 1px, transparent 1px)",
          backgroundSize: "100% 100%, 48px 48px, 48px 48px",
          minHeight: "100vh",
        }}
      >
        {/* System health strip */}
        <HealthStrip health={health} />

        {/* Main content */}
        <div style={{ maxWidth: 1280, margin: "0 auto", padding: "28px 28px 0" }}>

          {/* Error bar */}
          {error && (
            <div className="error-bar" style={{ marginBottom: 20 }}>
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <circle cx="7" cy="7" r="6" stroke="currentColor" strokeWidth="1.2"/>
                <path d="M7 4.5v3M7 9v.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
              </svg>
              {error}
            </div>
          )}

          {/* Two-column layout */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 420px", gap: 24, alignItems: "start" }}>

            {/* Left column */}
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              {/* Page title */}
              <div className="stagger-1" style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
                <div>
                  <div
                    className="dash-heading"
                    style={{ fontSize: 28, fontWeight: 800, color: "var(--od-text)", marginBottom: 2 }}
                  >
                    Mission Control
                  </div>
                  <div style={{ fontSize: 13, color: "var(--od-text-muted)" }}>
                    Drop documents — the pipeline handles the rest
                  </div>
                </div>
                <div style={{ display: "flex", gap: 10 }}>
                  <a
                    href="/dashboard/c-suite"
                    style={{
                      display: "flex", alignItems: "center", gap: 6,
                      padding: "7px 14px", borderRadius: 4,
                      border: "1px solid var(--od-border)",
                      background: "var(--od-surface)",
                      color: "var(--od-text-muted)",
                      fontFamily: "'DM Mono', monospace",
                      fontSize: 11, letterSpacing: "0.08em",
                      textDecoration: "none", textTransform: "uppercase",
                      transition: "border-color 0.15s, color 0.15s",
                    }}
                  >
                    Revenue →
                  </a>
                  <a
                    href="/dashboard/ops"
                    style={{
                      display: "flex", alignItems: "center", gap: 6,
                      padding: "7px 14px", borderRadius: 4,
                      border: "1px solid var(--od-border)",
                      background: "var(--od-surface)",
                      color: "var(--od-text-muted)",
                      fontFamily: "'DM Mono', monospace",
                      fontSize: 11, letterSpacing: "0.08em",
                      textDecoration: "none", textTransform: "uppercase",
                      transition: "border-color 0.15s, color 0.15s",
                    }}
                  >
                    Ops Queue →
                  </a>
                </div>
              </div>

              {/* Drop zone */}
              <div className="stagger-2">
                <DropZone
                  org={org}
                  onUploaded={() => setTriggerRefresh(n => n + 1)}
                />
              </div>

              {/* Quota bar */}
              <div className="stagger-3">
                <QuotaBar org={org} />
              </div>
            </div>

            {/* Right column — job feed */}
            <div className="stagger-2" style={{ position: "sticky", top: 0 }}>
              <JobFeed jobs={jobs} polling={polling} total={total} />
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
