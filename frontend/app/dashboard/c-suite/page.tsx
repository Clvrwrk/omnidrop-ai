"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AreaChart, BarList } from "@tremor/react";
import { api, ApiError } from "@/lib/api-client";
import type {
  AnalyticsPeriod,
  KpiResponse,
  LeakageSummary,
  Organization,
  VendorSpendResponse,
} from "@/lib/types";

// ─── Design System ────────────────────────────────────────────────────────────
// "The War Room" — financial intelligence briefing surface
// Inherits Precision Instrument tokens

const CS_CSS = `
  @import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Mono:ital,wght@0,300;0,400;0,500;1,300&family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;1,9..40,300&display=swap');

  :root {
    --od-bg:             #0D0F0E;
    --od-surface:        #141614;
    --od-surface-2:      #1A1C1A;
    --od-surface-3:      #1F211F;
    --od-border:         #252825;
    --od-border-bright:  #303530;
    --od-amber:          #E8A020;
    --od-amber-dim:      #7A5510;
    --od-amber-glow:     rgba(232,160,32,0.10);
    --od-amber-glow-lg:  rgba(232,160,32,0.22);
    --od-amber-line:     rgba(232,160,32,0.28);
    --od-text:           #F0EDE6;
    --od-text-muted:     #6B7068;
    --od-text-dim:       #3D403C;
    --od-success:        #4CAF7D;
    --od-error:          #E05252;
    --od-error-dim:      rgba(224,82,82,0.12);
    --od-warn:           #D48A1A;
    --od-leakage:        #C94040;
    --od-leakage-dim:    rgba(201,64,64,0.12);
    --od-leakage-line:   rgba(201,64,64,0.30);
  }

  .cs-root {
    font-family: 'DM Sans', sans-serif;
    background: var(--od-bg);
    color: var(--od-text);
    min-height: 100vh;
  }

  .cs-heading { font-family: 'Syne', sans-serif;    letter-spacing: -0.02em; }
  .cs-mono    { font-family: 'DM Mono', monospace;  letter-spacing: 0.03em; }

  /* ── Hero section ── */
  .hero-section {
    border-bottom: 1px solid var(--od-border);
    padding: 36px 40px 32px;
    position: relative;
    overflow: hidden;
  }
  .hero-section::before {
    content: '';
    position: absolute;
    inset: 0;
    background:
      radial-gradient(ellipse at 30% 50%, rgba(201,64,64,0.06) 0%, transparent 60%),
      radial-gradient(ellipse at 80% 20%, rgba(232,160,32,0.05) 0%, transparent 50%);
    pointer-events: none;
  }

  /* Counter animation */
  @keyframes counterReveal {
    from { opacity: 0; transform: translateY(12px); filter: blur(8px); }
    to   { opacity: 1; transform: translateY(0);    filter: blur(0); }
  }
  .hero-number {
    animation: counterReveal 0.7s cubic-bezier(0.22,1,0.36,1) 0.2s both;
    font-family: 'DM Mono', monospace;
    font-size: clamp(48px, 6vw, 80px);
    font-weight: 400;
    color: var(--od-amber);
    line-height: 1;
    letter-spacing: -0.02em;
    text-shadow: 0 0 60px rgba(232,160,32,0.25);
  }
  .hero-number-loading {
    color: var(--od-text-dim);
    text-shadow: none;
  }

  /* LIVE badge */
  @keyframes livePulse {
    0%,100% { opacity: 1; }
    50%      { opacity: 0.3; }
  }
  .live-badge {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 3px 8px;
    border-radius: 3px;
    background: var(--od-leakage-dim);
    border: 1px solid var(--od-leakage-line);
    font-family: 'DM Mono', monospace;
    font-size: 10px;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--od-leakage);
  }
  .live-dot {
    width: 5px; height: 5px;
    border-radius: 50%;
    background: var(--od-leakage);
    animation: livePulse 1.5s ease-in-out infinite;
  }

  /* ── Period tabs ── */
  .period-tabs {
    display: flex;
    gap: 2px;
    background: var(--od-surface);
    border: 1px solid var(--od-border);
    border-radius: 5px;
    padding: 3px;
  }
  .period-tab {
    padding: 5px 14px;
    border-radius: 3px;
    font-family: 'DM Mono', monospace;
    font-size: 11px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    border: none;
    background: transparent;
    color: var(--od-text-muted);
    cursor: pointer;
    transition: background 0.15s, color 0.15s;
    white-space: nowrap;
  }
  .period-tab:hover:not(.period-tab-active) {
    color: var(--od-text);
    background: var(--od-surface-2);
  }
  .period-tab-active {
    background: var(--od-amber);
    color: #0D0F0E;
    font-weight: 500;
  }

  /* ── KPI cards ── */
  .kpi-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    border-bottom: 1px solid var(--od-border);
  }
  .kpi-cell {
    padding: 24px 28px;
    border-right: 1px solid var(--od-border);
    position: relative;
    transition: background 0.2s;
  }
  .kpi-cell:last-child { border-right: none; }
  .kpi-cell:hover { background: var(--od-surface); }

  .kpi-delta-pos { color: var(--od-success); }
  .kpi-delta-neg { color: var(--od-leakage); }
  .kpi-delta-neu { color: var(--od-text-muted); }

  /* ── Section cards ── */
  .cs-card {
    border: 1px solid var(--od-border);
    border-radius: 6px;
    background: var(--od-surface);
    overflow: hidden;
  }
  .cs-card-header {
    padding: 18px 22px 14px;
    border-bottom: 1px solid var(--od-border);
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  /* ── Tremor overrides — strip white backgrounds ── */
  .tremor-override .tremor-Card-root { background: transparent !important; border: none !important; box-shadow: none !important; padding: 0 !important; }
  .tremor-override [class*="tremor-AreaChart"] text { fill: #6B7068 !important; font-family: 'DM Mono', monospace !important; font-size: 11px !important; }
  .tremor-override [class*="tremor-BarList"] { }
  .tremor-override .tremor-BarList-bar      { background: var(--od-amber-glow) !important; }
  .tremor-override .tremor-BarList-labelText { color: var(--od-text-muted) !important; font-family: 'DM Mono', monospace !important; font-size: 12px !important; }
  .tremor-override .tremor-BarList-valueText { color: var(--od-amber) !important; font-family: 'DM Mono', monospace !important; font-size: 12px !important; }

  /* ── Findings table ── */
  .findings-table {
    width: 100%;
    border-collapse: collapse;
  }
  .findings-table th {
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
  .findings-table th:first-child { padding-left: 22px; }
  .findings-table th:last-child  { padding-right: 22px; text-align: right; }

  .findings-row {
    border-bottom: 1px solid var(--od-border);
    transition: background 0.15s;
  }
  .findings-row:last-child { border-bottom: none; }
  .findings-row:hover { background: var(--od-surface-2); }

  .findings-row td {
    padding: 11px 16px;
    font-size: 13px;
    color: var(--od-text-muted);
    vertical-align: middle;
  }
  .findings-row td:first-child {
    padding-left: 22px;
    border-left: 2px solid transparent;
  }
  .findings-row:hover td:first-child { border-left-color: var(--od-leakage); }
  .findings-row td:last-child { padding-right: 22px; text-align: right; }

  .ref-badge {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 2px 7px;
    border-radius: 3px;
    font-family: 'DM Mono', monospace;
    font-size: 10px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }
  .ref-contract { background: var(--od-amber-glow); border: 1px solid var(--od-amber-line); color: var(--od-amber); }
  .ref-baseline { background: rgba(107,112,104,0.15); border: 1px solid rgba(107,112,104,0.25); color: var(--od-text-muted); }

  /* price comparison */
  .price-invoiced  { color: var(--od-leakage); font-family: 'DM Mono', monospace; font-size: 12px; }
  .price-reference { color: var(--od-success);  font-family: 'DM Mono', monospace; font-size: 12px; }
  .price-arrow     { color: var(--od-text-dim);  margin: 0 4px; font-size: 10px; }

  .leakage-amount {
    font-family: 'DM Mono', monospace;
    font-size: 13px;
    color: var(--od-leakage);
    font-weight: 500;
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

  /* ── Empty state ── */
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 10px;
    padding: 48px 20px;
    opacity: 0.4;
  }

  /* ── Error bar ── */
  .cs-error {
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

  /* ── Stagger reveals ── */
  @keyframes staggerIn {
    from { opacity: 0; transform: translateY(8px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  .s1 { animation: staggerIn 0.4s 0.05s ease both; }
  .s2 { animation: staggerIn 0.4s 0.12s ease both; }
  .s3 { animation: staggerIn 0.4s 0.20s ease both; }
  .s4 { animation: staggerIn 0.4s 0.28s ease both; }
  .s5 { animation: staggerIn 0.4s 0.36s ease both; }

  /* ── Scrollable findings ── */
  .findings-scroll { max-height: 400px; overflow-y: auto; }
  .findings-scroll::-webkit-scrollbar { width: 3px; }
  .findings-scroll::-webkit-scrollbar-track { background: transparent; }
  .findings-scroll::-webkit-scrollbar-thumb { background: var(--od-border-bright); border-radius: 2px; }

  /* ── Quota strip ── */
  .quota-strip {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 10px 40px;
    background: var(--od-surface);
    border-bottom: 1px solid var(--od-border);
  }
  .quota-track {
    flex: 1;
    height: 2px;
    background: var(--od-border);
    border-radius: 1px;
    overflow: hidden;
  }
  .quota-fill {
    height: 100%;
    border-radius: 1px;
    background: var(--od-amber);
    transition: width 0.8s cubic-bezier(0.22,1,0.36,1);
  }
  .quota-fill-warn { background: var(--od-warn); }
  .quota-fill-crit { background: var(--od-error); }
`;

// ─── Helpers ─────────────────────────────────────────────────────────────────

const PERIODS: { label: string; value: AnalyticsPeriod }[] = [
  { label: "7D",  value: "7d"  },
  { label: "30D", value: "30d" },
  { label: "90D", value: "90d" },
  { label: "YTD", value: "ytd" },
];

function usd(val: number, compact = false): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
    notation: compact ? "compact" : "standard",
  }).format(val);
}

function fmtDelta(pct: number): { label: string; cls: string } {
  if (pct === 0) return { label: "—", cls: "kpi-delta-neu" };
  const sign = pct > 0 ? "+" : "";
  return {
    label: `${sign}${pct.toFixed(1)}%`,
    cls: pct > 0 ? "kpi-delta-pos" : "kpi-delta-neg",
  };
}

// ─── Animated counter hook ────────────────────────────────────────────────────

function useCountUp(target: number, duration = 1200): number {
  const [current, setCurrent] = useState(0);
  const rafRef = useRef<number>(0);
  const startRef = useRef<number | null>(null);
  const prevTarget = useRef(0);

  useEffect(() => {
    if (target === prevTarget.current) return;
    const from = prevTarget.current;
    prevTarget.current = target;
    startRef.current = null;

    cancelAnimationFrame(rafRef.current);

    function tick(ts: number) {
      if (!startRef.current) startRef.current = ts;
      const elapsed = ts - startRef.current;
      const progress = Math.min(elapsed / duration, 1);
      // Ease out cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      setCurrent(Math.round(from + (target - from) * eased));
      if (progress < 1) rafRef.current = requestAnimationFrame(tick);
    }
    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
  }, [target, duration]);

  return current;
}

// ─── Hero Section ─────────────────────────────────────────────────────────────

function HeroSection({
  leakage,
  org,
  period,
  onPeriod,
  loading,
}: {
  leakage: LeakageSummary | null;
  org: Organization | null;
  period: AnalyticsPeriod;
  onPeriod: (p: AnalyticsPeriod) => void;
  loading: boolean;
}) {
  const total = leakage?.total_leakage ?? 0;
  const count = leakage?.finding_count ?? 0;
  const animatedVal = useCountUp(total);

  const docUsed = org?.documents_processed ?? 0;
  const docMax  = org?.max_documents ?? 100;
  const pct     = docMax > 0 ? Math.min((docUsed / docMax) * 100, 100) : 0;
  const isCrit  = pct >= 90;
  const isWarn  = pct >= 70 && !isCrit;

  return (
    <>
      {/* Quota strip */}
      {org && (
        <div className="quota-strip">
          <div className="cs-mono" style={{ fontSize: 10, color: "var(--od-text-dim)", letterSpacing: "0.1em", whiteSpace: "nowrap" }}>
            QUOTA
          </div>
          <div className="quota-track">
            <div
              className={`quota-fill ${isCrit ? "quota-fill-crit" : isWarn ? "quota-fill-warn" : ""}`}
              style={{ width: `${pct}%` }}
            />
          </div>
          <div className="cs-mono" style={{ fontSize: 11, color: isCrit ? "var(--od-error)" : "var(--od-text-muted)", whiteSpace: "nowrap" }}>
            {docUsed.toLocaleString()} / {docMax.toLocaleString()}
            <span style={{ color: "var(--od-text-dim)", marginLeft: 6 }}>docs</span>
          </div>
          {isCrit && (
            <a
              href="/settings"
              style={{
                fontFamily: "'DM Mono', monospace", fontSize: 10,
                letterSpacing: "0.08em", textTransform: "uppercase",
                color: "var(--od-amber)", textDecoration: "none",
                whiteSpace: "nowrap",
              }}
            >
              Upgrade →
            </a>
          )}
        </div>
      )}

      <div className="hero-section">
        {/* Breadcrumb + org */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 28 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <div className="cs-mono" style={{ fontSize: 11, color: "var(--od-text-dim)", letterSpacing: "0.1em", textTransform: "uppercase" }}>
              Revenue Recovery
            </div>
            {org?.name && (
              <>
                <span style={{ color: "var(--od-border-bright)" }}>·</span>
                <div className="cs-mono" style={{ fontSize: 11, color: "var(--od-text-muted)", letterSpacing: "0.06em" }}>
                  {org.name}
                </div>
              </>
            )}
            <div className="live-badge">
              <div className="live-dot" />
              Live
            </div>
          </div>
          {/* Period selector */}
          <div className="period-tabs">
            {PERIODS.map(p => (
              <button
                key={p.value}
                className={`period-tab ${period === p.value ? "period-tab-active" : ""}`}
                onClick={() => onPeriod(p.value)}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>

        {/* Hero metric */}
        <div style={{ display: "flex", alignItems: "flex-end", gap: 32, flexWrap: "wrap" }}>
          <div>
            <div className="cs-mono" style={{ fontSize: 11, color: "var(--od-text-dim)", letterSpacing: "0.14em", textTransform: "uppercase", marginBottom: 8 }}>
              Total Revenue Leakage Detected
            </div>
            <div className={`hero-number ${loading && !leakage ? "hero-number-loading" : ""}`}>
              {loading && !leakage ? "—" : usd(animatedVal)}
            </div>
            <div style={{ marginTop: 10, display: "flex", alignItems: "center", gap: 16 }}>
              <div className="cs-mono" style={{ fontSize: 12, color: "var(--od-text-muted)" }}>
                <span style={{ color: "var(--od-leakage)", marginRight: 5 }}>{count}</span>
                finding{count !== 1 ? "s" : ""} this period
              </div>
              <div className="cs-mono" style={{ fontSize: 12, color: "var(--od-text-dim)" }}>
                {leakage?.period ?? period} window
              </div>
            </div>
          </div>

          {/* Location count pill */}
          {leakage && leakage.by_location.length > 0 && (
            <div style={{
              display: "flex", flexDirection: "column", gap: 4,
              padding: "12px 20px",
              background: "var(--od-leakage-dim)",
              border: "1px solid var(--od-leakage-line)",
              borderRadius: 6,
            }}>
              <div className="cs-mono" style={{ fontSize: 10, color: "var(--od-leakage)", letterSpacing: "0.1em", textTransform: "uppercase" }}>
                Locations Affected
              </div>
              <div className="cs-mono" style={{ fontSize: 28, color: "var(--od-text)", fontWeight: 400 }}>
                {leakage.by_location.length}
              </div>
              <div style={{ fontSize: 11, color: "var(--od-text-muted)" }}>
                branches with overcharges
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}

// ─── KPI Strip ────────────────────────────────────────────────────────────────

function KpiStrip({ kpis, loading }: { kpis: KpiResponse | null; loading: boolean }) {
  const cells = [
    {
      label: "Docs Processed",
      value: loading ? null : kpis?.volume_processed.value.toLocaleString() ?? "—",
      delta: kpis?.volume_processed.delta_pct ?? 0,
      sub: "this period",
    },
    {
      label: "Accuracy Rate",
      value: loading ? null : kpis ? `${(kpis.accuracy_rate.value * 100).toFixed(1)}%` : "—",
      delta: kpis?.accuracy_rate.delta_pct ?? 0,
      sub: "extraction confidence",
    },
    {
      label: "Avg. Process Time",
      value: loading ? null : kpis ? `${kpis.avg_processing_time_seconds.value.toFixed(1)}s` : "—",
      delta: -(kpis?.avg_processing_time_seconds.delta_pct ?? 0), // lower is better
      sub: "per document",
    },
    {
      label: "Total Invoice Value",
      value: loading ? null : kpis ? usd(kpis.total_invoice_value.value, true) : "—",
      delta: kpis?.total_invoice_value.delta_pct ?? 0,
      sub: "invoices audited",
    },
    {
      label: "Pending Review",
      value: loading ? null : kpis?.pending_triage_count.toString() ?? "—",
      delta: 0,
      sub: <a href="/dashboard/ops" style={{ color: "var(--od-amber)", textDecoration: "none", fontFamily: "'DM Mono', monospace", fontSize: 10, letterSpacing: "0.06em" }}>Go to Ops Queue →</a>,
    },
  ];

  return (
    <div className="kpi-grid s1" style={{ gridTemplateColumns: `repeat(${cells.length}, 1fr)` }}>
      {cells.map((cell, i) => {
        const delta = fmtDelta(cell.delta);
        return (
          <div key={cell.label} className="kpi-cell">
            <div className="cs-mono" style={{ fontSize: 10, color: "var(--od-text-dim)", letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 10 }}>
              {cell.label}
            </div>
            {cell.value === null ? (
              <div className="skeleton" style={{ height: 28, width: "60%", marginBottom: 8 }} />
            ) : (
              <div className="cs-mono" style={{ fontSize: 26, fontWeight: 400, color: "var(--od-text)", marginBottom: 4 }}>
                {cell.value}
              </div>
            )}
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              {cell.delta !== 0 && (
                <div className={`cs-mono ${delta.cls}`} style={{ fontSize: 11 }}>
                  {delta.label}
                </div>
              )}
              <div className="cs-mono" style={{ fontSize: 10, color: "var(--od-text-dim)" }}>
                {cell.sub}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ─── Chart Row ────────────────────────────────────────────────────────────────

function ChartRow({
  vendorSpend,
  leakage,
  loading,
}: {
  vendorSpend: VendorSpendResponse | null;
  leakage: LeakageSummary | null;
  loading: boolean;
}) {
  // Build AreaChart data from vendor spend trend
  const trendData = (vendorSpend?.trend ?? []).map(pt => ({
    date: pt.date,
    "Invoice Value": pt.total,
  }));

  // BarList — leakage by vendor, sorted desc
  const vendorBarData = (leakage?.by_vendor ?? [])
    .slice()
    .sort((a, b) => b.total_leakage - a.total_leakage)
    .slice(0, 8)
    .map(v => ({ name: v.vendor_name, value: v.total_leakage }));

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 380px", gap: 20, padding: "20px 40px" }} className="s3">

      {/* Area chart — invoice volume / spend trend */}
      <div className="cs-card">
        <div className="cs-card-header">
          <div>
            <div className="cs-heading" style={{ fontSize: 15, fontWeight: 700, color: "var(--od-text)" }}>
              Invoice Volume &amp; Spend
            </div>
            <div style={{ fontSize: 12, color: "var(--od-text-muted)", marginTop: 3 }}>
              Total invoice value audited by day
            </div>
          </div>
          <div className="cs-mono" style={{ fontSize: 10, color: "var(--od-text-dim)", letterSpacing: "0.08em" }}>
            {vendorSpend?.period ?? "—"}
          </div>
        </div>
        <div style={{ padding: "20px 22px" }}>
          {loading && trendData.length === 0 ? (
            <div className="skeleton" style={{ height: 200 }} />
          ) : trendData.length === 0 ? (
            <div className="empty-state">
              <div className="cs-mono" style={{ fontSize: 11, letterSpacing: "0.08em", textTransform: "uppercase" }}>
                No trend data yet
              </div>
            </div>
          ) : (
            <div className="tremor-override">
              <AreaChart
                data={trendData}
                index="date"
                categories={["Invoice Value"]}
                colors={["amber"]}
                valueFormatter={v => usd(v, true)}
                yAxisWidth={72}
                showLegend={false}
                showGridLines={false}
                className="h-52"
                curveType="monotone"
              />
            </div>
          )}
        </div>
      </div>

      {/* BarList — leakage by vendor */}
      <div className="cs-card">
        <div className="cs-card-header">
          <div>
            <div className="cs-heading" style={{ fontSize: 15, fontWeight: 700, color: "var(--od-text)" }}>
              Overcharges by Vendor
            </div>
            <div style={{ fontSize: 12, color: "var(--od-text-muted)", marginTop: 3 }}>
              Worst offenders this period
            </div>
          </div>
        </div>
        <div style={{ padding: "18px 22px" }}>
          {loading && vendorBarData.length === 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {[80, 65, 55, 40].map(w => (
                <div key={w} className="skeleton" style={{ height: 20, width: `${w}%` }} />
              ))}
            </div>
          ) : vendorBarData.length === 0 ? (
            <div className="empty-state">
              <div className="cs-mono" style={{ fontSize: 11, letterSpacing: "0.08em", textTransform: "uppercase" }}>
                No findings yet
              </div>
            </div>
          ) : (
            <div className="tremor-override">
              <BarList
                data={vendorBarData}
                valueFormatter={v => usd(v, true)}
                color="amber"
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Findings Table ───────────────────────────────────────────────────────────

function FindingsTable({
  leakage,
  loading,
}: {
  leakage: LeakageSummary | null;
  loading: boolean;
}) {
  // Flatten by_location into display rows using finding_count as proxy
  // Real findings come from leakage.findings if present, else synthesise from by_location
  const rows = (leakage?.by_location ?? [])
    .slice()
    .sort((a, b) => b.total_leakage - a.total_leakage);

  return (
    <div style={{ padding: "0 40px 40px" }} className="s5">
      <div className="cs-card">
        <div className="cs-card-header">
          <div>
            <div className="cs-heading" style={{ fontSize: 15, fontWeight: 700, color: "var(--od-text)" }}>
              Leakage by Location
            </div>
            <div style={{ fontSize: 12, color: "var(--od-text-muted)", marginTop: 3 }}>
              Branches paying above contracted or baseline rates
            </div>
          </div>
          <div className="cs-mono" style={{ fontSize: 10, color: "var(--od-text-dim)", letterSpacing: "0.08em" }}>
            {rows.length} BRANCH{rows.length !== 1 ? "ES" : ""}
          </div>
        </div>

        {loading && rows.length === 0 ? (
          <div style={{ padding: "20px 22px", display: "flex", flexDirection: "column", gap: 10 }}>
            {[100, 85, 70].map(w => (
              <div key={w} className="skeleton" style={{ height: 36, width: `${w}%` }} />
            ))}
          </div>
        ) : rows.length === 0 ? (
          <div className="empty-state">
            <svg width="36" height="36" viewBox="0 0 36 36" fill="none">
              <path d="M18 8v10M18 22v2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
              <circle cx="18" cy="18" r="14" stroke="currentColor" strokeWidth="1.2"/>
            </svg>
            <div className="cs-mono" style={{ fontSize: 11, letterSpacing: "0.08em", textTransform: "uppercase" }}>
              No leakage findings for this period
            </div>
            <div style={{ fontSize: 12, textAlign: "center", maxWidth: 240 }}>
              Upload invoices and add a pricing contract to start detecting overcharges
            </div>
          </div>
        ) : (
          <div className="findings-scroll">
            <table className="findings-table">
              <thead>
                <tr>
                  <th>Location</th>
                  <th>Findings</th>
                  <th>Total Overcharge</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((loc, i) => (
                  <tr key={`${loc.location_name}-${i}`} className="findings-row">
                    <td>
                      <div className="cs-mono" style={{ fontSize: 12, color: "var(--od-text)" }}>
                        {loc.location_name}
                      </div>
                    </td>
                    <td>
                      <div className="cs-mono" style={{ fontSize: 12, color: "var(--od-text-muted)" }}>
                        {loc.finding_count} finding{loc.finding_count !== 1 ? "s" : ""}
                      </div>
                    </td>
                    <td>
                      <div className="leakage-amount">
                        {usd(loc.total_leakage)}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Vendor Findings Detail Table ─────────────────────────────────────────────

function VendorFindingsTable({
  leakage,
  loading,
}: {
  leakage: LeakageSummary | null;
  loading: boolean;
}) {
  const rows = (leakage?.by_vendor ?? [])
    .slice()
    .sort((a, b) => b.total_leakage - a.total_leakage);

  if (!loading && rows.length === 0) return null;

  return (
    <div style={{ padding: "0 40px 40px" }} className="s5">
      <div className="cs-card">
        <div className="cs-card-header">
          <div>
            <div className="cs-heading" style={{ fontSize: 15, fontWeight: 700, color: "var(--od-text)" }}>
              Vendor Overcharge Summary
            </div>
            <div style={{ fontSize: 12, color: "var(--od-text-muted)", marginTop: 3 }}>
              Suppliers billing above agreed pricing
            </div>
          </div>
          <div className="cs-mono" style={{ fontSize: 10, color: "var(--od-text-dim)", letterSpacing: "0.08em" }}>
            {rows.length} VENDOR{rows.length !== 1 ? "S" : ""}
          </div>
        </div>

        {loading && rows.length === 0 ? (
          <div style={{ padding: "20px 22px", display: "flex", flexDirection: "column", gap: 10 }}>
            {[100, 80, 65].map(w => (
              <div key={w} className="skeleton" style={{ height: 36, width: `${w}%` }} />
            ))}
          </div>
        ) : (
          <div className="findings-scroll">
            <table className="findings-table">
              <thead>
                <tr>
                  <th>Vendor</th>
                  <th>Findings</th>
                  <th>Total Overcharge</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((vendor, i) => (
                  <tr key={`${vendor.vendor_name}-${i}`} className="findings-row">
                    <td>
                      <div className="cs-mono" style={{ fontSize: 12, color: "var(--od-text)" }}>
                        {vendor.vendor_name}
                      </div>
                    </td>
                    <td>
                      <div className="cs-mono" style={{ fontSize: 12, color: "var(--od-text-muted)" }}>
                        {vendor.finding_count} finding{vendor.finding_count !== 1 ? "s" : ""}
                      </div>
                    </td>
                    <td>
                      <div className="leakage-amount">
                        {usd(vendor.total_leakage)}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function CSuitePage() {
  const [period,      setPeriod]      = useState<AnalyticsPeriod>("30d");
  const [leakage,     setLeakage]     = useState<LeakageSummary | null>(null);
  const [kpis,        setKpis]        = useState<KpiResponse | null>(null);
  const [vendorSpend, setVendorSpend] = useState<VendorSpendResponse | null>(null);
  const [org,         setOrg]         = useState<Organization | null>(null);
  const [loading,     setLoading]     = useState(true);
  const [error,       setError]       = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [leakageRes, kpisRes, spendRes, orgRes] = await Promise.all([
        api.getLeakageSummary({ period }),
        api.getKpis({ period }),
        api.getVendorSpend({ period, group_by: "vendor" }),
        api.getOrganization(),
      ]);
      setLeakage(leakageRes);
      setKpis(kpisRes);
      setVendorSpend(spendRes);
      setOrg(orgRes);
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [period]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  return (
    <>
      <style dangerouslySetInnerHTML={{ __html: CS_CSS }} />

      <div
        className="cs-root"
        style={{
          backgroundImage:
            "radial-gradient(ellipse at 15% 25%, rgba(201,64,64,0.05) 0%, transparent 50%), " +
            "radial-gradient(ellipse at 85% 75%, rgba(232,160,32,0.04) 0%, transparent 45%)",
        }}
      >
        {/* Hero */}
        <HeroSection
          leakage={leakage}
          org={org}
          period={period}
          onPeriod={setPeriod}
          loading={loading}
        />

        {/* Error */}
        {error && (
          <div className="cs-error s1">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <circle cx="7" cy="7" r="6" stroke="currentColor" strokeWidth="1.2"/>
              <path d="M7 4.5v3M7 9v.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
            </svg>
            {error}
          </div>
        )}

        {/* KPI strip */}
        <KpiStrip kpis={kpis} loading={loading} />

        {/* Chart row */}
        <ChartRow
          vendorSpend={vendorSpend}
          leakage={leakage}
          loading={loading}
        />

        {/* Location findings table */}
        <FindingsTable leakage={leakage} loading={loading} />

        {/* Vendor findings table */}
        <VendorFindingsTable leakage={leakage} loading={loading} />
      </div>
    </>
  );
}
