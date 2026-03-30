"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api-client";
import type { Organization } from "@/lib/types";

// ─── Design Tokens ────────────────────────────────────────────────────────────
// "Precision Instrument" — industrial-financial dark aesthetic
// Background: near-black slate #0D0F0E | Accent: warm amber #E8A020
// Fonts loaded via inline @import in the style block below

// ─── Types ────────────────────────────────────────────────────────────────────

type OnboardingStep = 1 | 2 | 3 | 4 | 5;
type PricingMode = "contract" | "baseline" | null;

const STEP_META = [
  { label: "Company", sublabel: "Your organization" },
  { label: "Location", sublabel: "First branch" },
  { label: "AccuLynx", sublabel: "API integration" },
  { label: "Pricing", sublabel: "Contract upload" },
  { label: "Findings", sublabel: "Revenue scan" },
] as const;

const US_TIMEZONES = [
  { value: "America/New_York", label: "Eastern — New York" },
  { value: "America/Chicago", label: "Central — Chicago" },
  { value: "America/Denver", label: "Mountain — Denver" },
  { value: "America/Los_Angeles", label: "Pacific — Los Angeles" },
  { value: "America/Phoenix", label: "Mountain — Phoenix (no DST)" },
  { value: "America/Anchorage", label: "Alaska — Anchorage" },
  { value: "Pacific/Honolulu", label: "Hawaii — Honolulu" },
];

// ─── Global Styles (injected once) ───────────────────────────────────────────

const GLOBAL_CSS = `
  @import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Mono:ital,wght@0,300;0,400;0,500;1,300&family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;1,9..40,300&display=swap');

  :root {
    --od-bg: #0D0F0E;
    --od-surface: #141614;
    --od-surface-2: #1A1C1A;
    --od-border: #252825;
    --od-border-bright: #303530;
    --od-amber: #E8A020;
    --od-amber-dim: #7A5510;
    --od-amber-glow: rgba(232, 160, 32, 0.12);
    --od-amber-line: rgba(232, 160, 32, 0.35);
    --od-text: #F0EDE6;
    --od-text-muted: #6B7068;
    --od-text-dim: #4A4D48;
    --od-success: #4CAF7D;
    --od-success-dim: rgba(76, 175, 125, 0.15);
    --od-error: #E05252;
    --od-error-dim: rgba(224, 82, 82, 0.12);
  }

  .od-body {
    font-family: 'DM Sans', sans-serif;
    background: var(--od-bg);
    color: var(--od-text);
    min-height: 100vh;
  }

  .od-heading {
    font-family: 'Syne', sans-serif;
    letter-spacing: -0.02em;
  }

  .od-mono {
    font-family: 'DM Mono', monospace;
    letter-spacing: 0.02em;
  }

  /* Step rail fill animation */
  @keyframes railFill {
    from { height: 0%; }
    to { height: var(--fill-pct); }
  }

  @keyframes nodePulse {
    0%, 100% { box-shadow: 0 0 0 0 rgba(232, 160, 32, 0.4); }
    50% { box-shadow: 0 0 0 6px rgba(232, 160, 32, 0); }
  }

  @keyframes slideInRight {
    from {
      opacity: 0;
      transform: translateX(20px);
      filter: blur(4px);
    }
    to {
      opacity: 1;
      transform: translateX(0);
      filter: blur(0);
    }
  }

  @keyframes fadeUp {
    from { opacity: 0; transform: translateY(8px); }
    to { opacity: 1; transform: translateY(0); }
  }

  @keyframes spin360 {
    to { transform: rotate(360deg); }
  }

  @keyframes amberScan {
    0% { transform: translateY(-100%); }
    100% { transform: translateY(400%); }
  }

  @keyframes blink {
    0%, 100% { opacity: 1; }
    50% { opacity: 0; }
  }

  .od-step-content {
    animation: slideInRight 0.35s cubic-bezier(0.22, 1, 0.36, 1) both;
  }

  .od-fade-up {
    animation: fadeUp 0.4s ease both;
  }

  .od-input {
    width: 100%;
    background: var(--od-surface);
    border: 1px solid var(--od-border);
    border-radius: 4px;
    padding: 10px 14px;
    color: var(--od-text);
    font-family: 'DM Sans', sans-serif;
    font-size: 14px;
    outline: none;
    transition: border-color 0.15s, box-shadow 0.15s;
    -webkit-appearance: none;
  }

  .od-input::placeholder {
    color: var(--od-text-dim);
    font-family: 'DM Mono', monospace;
    font-size: 13px;
  }

  .od-input:focus {
    border-color: var(--od-amber);
    box-shadow: 0 0 0 2px var(--od-amber-glow);
  }

  .od-input-mono {
    font-family: 'DM Mono', monospace;
    font-size: 13px;
    letter-spacing: 0.04em;
  }

  .od-select {
    width: 100%;
    background: var(--od-surface);
    border: 1px solid var(--od-border);
    border-radius: 4px;
    padding: 10px 14px;
    color: var(--od-text);
    font-family: 'DM Sans', sans-serif;
    font-size: 14px;
    outline: none;
    cursor: pointer;
    -webkit-appearance: none;
    appearance: none;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%236B7068' stroke-width='2'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: right 14px center;
    padding-right: 36px;
    transition: border-color 0.15s;
  }

  .od-select option {
    background: #1A1C1A;
    color: #F0EDE6;
  }

  .od-select:focus {
    border-color: var(--od-amber);
    box-shadow: 0 0 0 2px var(--od-amber-glow);
  }

  .od-btn-primary {
    width: 100%;
    background: var(--od-amber);
    color: #0D0F0E;
    border: none;
    border-radius: 4px;
    padding: 11px 20px;
    font-family: 'Syne', sans-serif;
    font-size: 14px;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    cursor: pointer;
    transition: opacity 0.15s, transform 0.1s;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
  }

  .od-btn-primary:hover:not(:disabled) {
    opacity: 0.9;
    transform: translateY(-1px);
  }

  .od-btn-primary:active:not(:disabled) {
    transform: translateY(0);
  }

  .od-btn-primary:disabled {
    opacity: 0.3;
    cursor: not-allowed;
  }

  .od-btn-ghost {
    background: transparent;
    border: 1px solid var(--od-border);
    color: var(--od-text-muted);
    border-radius: 4px;
    padding: 9px 16px;
    font-family: 'DM Sans', sans-serif;
    font-size: 13px;
    cursor: pointer;
    transition: border-color 0.15s, color 0.15s;
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .od-btn-ghost:hover {
    border-color: var(--od-border-bright);
    color: var(--od-text);
  }

  .od-label {
    display: block;
    font-family: 'DM Mono', monospace;
    font-size: 11px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--od-text-muted);
    margin-bottom: 7px;
  }

  .od-label-required::after {
    content: ' *';
    color: var(--od-amber);
  }

  .od-field-error {
    font-family: 'DM Mono', monospace;
    font-size: 11px;
    color: var(--od-error);
    margin-top: 5px;
    display: flex;
    align-items: center;
    gap: 4px;
  }

  .od-divider {
    border: none;
    border-top: 1px solid var(--od-border);
    margin: 20px 0;
  }

  .od-card {
    background: var(--od-surface);
    border: 1px solid var(--od-border);
    border-radius: 6px;
    padding: 16px 20px;
  }

  .od-card-amber {
    background: var(--od-amber-glow);
    border: 1px solid var(--od-amber-line);
    border-radius: 6px;
    padding: 14px 18px;
  }

  .od-card-error {
    background: var(--od-error-dim);
    border: 1px solid rgba(224, 82, 82, 0.3);
    border-radius: 6px;
    padding: 12px 16px;
  }

  .od-card-success {
    background: var(--od-success-dim);
    border: 1px solid rgba(76, 175, 125, 0.3);
    border-radius: 6px;
    padding: 16px 20px;
  }

  .od-back-link {
    background: none;
    border: none;
    color: var(--od-text-dim);
    font-family: 'DM Mono', monospace;
    font-size: 11px;
    letter-spacing: 0.08em;
    cursor: pointer;
    text-transform: uppercase;
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 0;
    margin-bottom: 24px;
    transition: color 0.15s;
  }

  .od-back-link:hover {
    color: var(--od-text-muted);
  }

  .od-skip-link {
    background: none;
    border: none;
    color: var(--od-text-dim);
    font-family: 'DM Sans', sans-serif;
    font-size: 13px;
    cursor: pointer;
    text-align: center;
    width: 100%;
    padding: 8px;
    transition: color 0.15s;
  }

  .od-skip-link:hover {
    color: var(--od-text-muted);
  }

  /* Dropzone */
  .od-dropzone {
    border: 1px dashed var(--od-border-bright);
    border-radius: 6px;
    padding: 40px 20px;
    text-align: center;
    cursor: pointer;
    transition: border-color 0.2s, background 0.2s;
    position: relative;
    overflow: hidden;
  }

  .od-dropzone:hover, .od-dropzone-active {
    border-color: var(--od-amber-dim);
    background: var(--od-amber-glow);
  }

  .od-dropzone-active {
    border-style: solid;
    border-color: var(--od-amber);
  }

  /* File list */
  .od-file-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: var(--od-surface-2);
    border: 1px solid var(--od-border);
    border-radius: 4px;
    padding: 8px 12px;
  }

  .od-badge {
    font-family: 'DM Mono', monospace;
    font-size: 10px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    padding: 3px 8px;
    border-radius: 3px;
    font-weight: 500;
  }

  .od-badge-queued {
    background: rgba(107, 112, 104, 0.2);
    color: var(--od-text-muted);
    border: 1px solid rgba(107, 112, 104, 0.3);
  }

  .od-badge-processing {
    background: rgba(232, 160, 32, 0.15);
    color: var(--od-amber);
    border: 1px solid rgba(232, 160, 32, 0.25);
  }

  .od-badge-failed {
    background: var(--od-error-dim);
    color: var(--od-error);
    border: 1px solid rgba(224, 82, 82, 0.3);
  }

  /* Scan animation */
  .od-scan-line {
    position: absolute;
    left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, transparent, var(--od-amber), transparent);
    animation: amberScan 2s linear infinite;
    opacity: 0.7;
  }

  /* Spinner */
  .od-spinner {
    width: 28px;
    height: 28px;
    border: 2px solid var(--od-border-bright);
    border-top-color: var(--od-amber);
    border-radius: 50%;
    animation: spin360 0.8s linear infinite;
  }

  /* Key reveal toggle */
  .od-key-toggle {
    position: absolute;
    right: 12px;
    top: 50%;
    transform: translateY(-50%);
    background: none;
    border: none;
    color: var(--od-amber-dim);
    font-family: 'DM Mono', monospace;
    font-size: 10px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    cursor: pointer;
    transition: color 0.15s;
    padding: 4px;
  }

  .od-key-toggle:hover {
    color: var(--od-amber);
  }

  /* Grid field */
  .od-field {
    display: flex;
    flex-direction: column;
  }

  /* Scrollbar in file list */
  .od-scroll::-webkit-scrollbar { width: 3px; }
  .od-scroll::-webkit-scrollbar-track { background: transparent; }
  .od-scroll::-webkit-scrollbar-thumb { background: var(--od-border-bright); border-radius: 2px; }

  /* Link style */
  .od-link {
    color: var(--od-amber);
    font-family: 'DM Mono', monospace;
    font-size: 12px;
    letter-spacing: 0.06em;
    text-decoration: none;
    transition: opacity 0.15s;
  }
  .od-link:hover { opacity: 0.75; }

  /* Cursor blink in mono fields */
  .od-cursor::after {
    content: '|';
    animation: blink 1s step-end infinite;
    color: var(--od-amber);
    margin-left: 1px;
  }
`;

// ─── Left Rail — Vertical Step Timeline ───────────────────────────────────────

function StepRail({ current }: { current: OnboardingStep }) {
  const fillPct = `${((current - 1) / 4) * 100}%`;

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        width: 200,
        flexShrink: 0,
        paddingTop: 8,
        position: "relative",
      }}
    >
      {/* OmniDrop wordmark */}
      <div style={{ marginBottom: 48, alignSelf: "flex-start" }}>
        <div
          className="od-heading"
          style={{
            fontSize: 15,
            fontWeight: 800,
            color: "var(--od-amber)",
            letterSpacing: "0.12em",
            textTransform: "uppercase",
          }}
        >
          OmniDrop
        </div>
        <div
          className="od-mono"
          style={{ fontSize: 10, color: "var(--od-text-dim)", marginTop: 2 }}
        >
          Revenue Intelligence
        </div>
      </div>

      {/* Rail container */}
      <div style={{ position: "relative", width: "100%", flex: 1 }}>
        {/* Background rail */}
        <div
          style={{
            position: "absolute",
            left: 19,
            top: 12,
            bottom: 12,
            width: 1,
            background: "var(--od-border)",
          }}
        />
        {/* Filled portion */}
        <div
          style={{
            position: "absolute",
            left: 19,
            top: 12,
            width: 1,
            background: "var(--od-amber)",
            transition: "height 0.5s cubic-bezier(0.22, 1, 0.36, 1)",
            height: fillPct,
          }}
        />

        {/* Step nodes */}
        {STEP_META.map((meta, i) => {
          const stepNum = (i + 1) as OnboardingStep;
          const done = stepNum < current;
          const active = stepNum === current;

          return (
            <div
              key={stepNum}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 14,
                marginBottom: i < 4 ? 36 : 0,
                position: "relative",
              }}
            >
              {/* Node */}
              <div
                style={{
                  width: 20,
                  height: 20,
                  borderRadius: "50%",
                  flexShrink: 0,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  background: done
                    ? "var(--od-amber)"
                    : active
                      ? "var(--od-bg)"
                      : "var(--od-surface)",
                  border: done
                    ? "1px solid var(--od-amber)"
                    : active
                      ? "1.5px solid var(--od-amber)"
                      : "1px solid var(--od-border)",
                  transition: "all 0.3s",
                  animation: active ? "nodePulse 2s ease-in-out infinite" : "none",
                  zIndex: 1,
                }}
              >
                {done ? (
                  <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                    <path
                      d="M2 5l2 2 4-4"
                      stroke="#0D0F0E"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                ) : (
                  <div
                    className="od-mono"
                    style={{
                      fontSize: 9,
                      color: active ? "var(--od-amber)" : "var(--od-text-dim)",
                      fontWeight: 500,
                    }}
                  >
                    {stepNum}
                  </div>
                )}
              </div>

              {/* Labels */}
              <div>
                <div
                  className="od-mono"
                  style={{
                    fontSize: 11,
                    fontWeight: 500,
                    color: done
                      ? "var(--od-text-muted)"
                      : active
                        ? "var(--od-text)"
                        : "var(--od-text-dim)",
                    letterSpacing: "0.06em",
                    textTransform: "uppercase",
                    transition: "color 0.3s",
                  }}
                >
                  {meta.label}
                </div>
                <div
                  style={{
                    fontSize: 11,
                    color: active ? "var(--od-text-muted)" : "var(--od-text-dim)",
                    marginTop: 1,
                    transition: "color 0.3s",
                  }}
                >
                  {meta.sublabel}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Footer */}
      <div style={{ marginTop: "auto", paddingTop: 48 }}>
        <a
          href="/dashboard"
          className="od-mono"
          style={{
            fontSize: 10,
            color: "var(--od-text-dim)",
            textDecoration: "none",
            letterSpacing: "0.08em",
            display: "flex",
            alignItems: "center",
            gap: 4,
          }}
        >
          <span style={{ opacity: 0.5 }}>←</span> Back to dashboard
        </a>
      </div>
    </div>
  );
}

// ─── Field Component ──────────────────────────────────────────────────────────

function Field({
  id,
  label,
  required,
  error,
  children,
}: {
  id: string;
  label: string;
  required?: boolean;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="od-field">
      <label
        htmlFor={id}
        className={`od-label ${required ? "od-label-required" : ""}`}
      >
        {label}
      </label>
      {children}
      {error && (
        <div className="od-field-error">
          <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
            <circle cx="5" cy="5" r="4.5" stroke="currentColor" strokeWidth="1" />
            <path d="M5 3v2.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
            <circle cx="5" cy="7.2" r="0.5" fill="currentColor" />
          </svg>
          {error}
        </div>
      )}
    </div>
  );
}

// ─── Step Header ──────────────────────────────────────────────────────────────

function StepHeader({
  step,
  title,
  subtitle,
  onBack,
}: {
  step: OnboardingStep;
  title: string;
  subtitle: string;
  onBack?: () => void;
}) {
  return (
    <div style={{ marginBottom: 32 }}>
      {onBack && (
        <button className="od-back-link" onClick={onBack}>
          <svg width="12" height="10" viewBox="0 0 12 10" fill="none">
            <path
              d="M5 1L1 5l4 4M1 5h10"
              stroke="currentColor"
              strokeWidth="1.2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          Back
        </button>
      )}
      <div
        className="od-mono"
        style={{
          fontSize: 11,
          color: "var(--od-amber)",
          letterSpacing: "0.12em",
          textTransform: "uppercase",
          marginBottom: 8,
        }}
      >
        Step {step} of 5
      </div>
      <div
        className="od-heading"
        style={{
          fontSize: 26,
          fontWeight: 700,
          color: "var(--od-text)",
          lineHeight: 1.1,
          marginBottom: 8,
        }}
      >
        {title}
      </div>
      <div style={{ fontSize: 14, color: "var(--od-text-muted)", lineHeight: 1.5 }}>
        {subtitle}
      </div>
    </div>
  );
}

// ─── Step 1 — Company & Profile ────────────────────────────────────────────────

function Step1({ onContinue }: { onContinue: () => void }) {
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [timezone, setTimezone] = useState("America/Chicago");
  const [errors, setErrors] = useState<Record<string, string>>({});

  function validate() {
    const e: Record<string, string> = {};
    if (!firstName.trim()) e.firstName = "First name is required";
    if (!lastName.trim()) e.lastName = "Last name is required";
    if (!companyName.trim()) e.companyName = "Company name is required";
    return e;
  }

  function handleContinue() {
    const e = validate();
    if (Object.keys(e).length) {
      setErrors(e);
      return;
    }
    onContinue();
  }

  return (
    <div className="od-step-content">
      <StepHeader
        step={1}
        title="Your organization"
        subtitle="Tell us about your company so we can configure your workspace."
      />

      <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
          <Field id="first-name" label="First name" required error={errors.firstName}>
            <input
              id="first-name"
              className="od-input"
              type="text"
              value={firstName}
              onChange={(e) => setFirstName(e.target.value)}
              placeholder="Jane"
              autoFocus
            />
          </Field>
          <Field id="last-name" label="Last name" required error={errors.lastName}>
            <input
              id="last-name"
              className="od-input"
              type="text"
              value={lastName}
              onChange={(e) => setLastName(e.target.value)}
              placeholder="Smith"
            />
          </Field>
        </div>

        <Field id="company" label="Company name" required error={errors.companyName}>
          <input
            id="company"
            className="od-input"
            type="text"
            value={companyName}
            onChange={(e) => setCompanyName(e.target.value)}
            placeholder="e.g. Apex Roofing Group"
          />
        </Field>

        <Field id="timezone" label="Timezone">
          <select
            id="timezone"
            className="od-select"
            value={timezone}
            onChange={(e) => setTimezone(e.target.value)}
          >
            {US_TIMEZONES.map((tz) => (
              <option key={tz.value} value={tz.value}>
                {tz.label}
              </option>
            ))}
          </select>
        </Field>

        {/* Persona selector */}
        <Field id="persona" label="My role">
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            {[
              { value: "csuite", label: "C-Suite / Owner", icon: "◆" },
              { value: "ops", label: "Accountant / Ops", icon: "◈" },
            ].map((p) => (
              <button
                key={p.value}
                type="button"
                className="od-btn-ghost"
                style={{
                  justifyContent: "flex-start",
                  padding: "10px 14px",
                  gap: 10,
                }}
              >
                <span style={{ color: "var(--od-amber)", fontSize: 12 }}>{p.icon}</span>
                <span style={{ fontSize: 13 }}>{p.label}</span>
              </button>
            ))}
          </div>
        </Field>

        <div style={{ paddingTop: 8 }}>
          <button className="od-btn-primary" onClick={handleContinue}>
            Continue
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path
                d="M3 7h8M8 4l3 3-3 3"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Step 2 — Location Setup ───────────────────────────────────────────────────

function Step2({
  org,
  onSuccess,
  onSkip,
  onBack,
}: {
  org: Organization | null;
  onSuccess: (locationId: string) => void;
  onSkip: () => void;
  onBack: () => void;
}) {
  const [locName, setLocName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [locErrors, setLocErrors] = useState<Record<string, string>>({});

  async function handleCreate() {
    const e: Record<string, string> = {};
    if (!locName.trim()) e.locName = "Location name is required";
    if (Object.keys(e).length) {
      setLocErrors(e);
      return;
    }
    if (!org) {
      setError("Organization not loaded — please refresh.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      // Create location without API key yet — key is entered in Step 3
      const res = await api.createLocation({
        name: locName.trim(),
        acculynx_api_key: "",
        organization_id: org.organization_id,
      });
      onSuccess(res.location_id);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Failed to create location. Please try again.",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="od-step-content">
      <StepHeader
        step={2}
        title="Add your first location"
        subtitle="Each roofing branch is a separate location with its own AccuLynx integration."
        onBack={onBack}
      />

      <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
        {error && (
          <div className="od-card-error od-fade-up">
            <div style={{ fontSize: 13, color: "var(--od-error)" }}>{error}</div>
          </div>
        )}

        {/* Info card */}
        <div className="od-card-amber">
          <div className="od-mono" style={{ fontSize: 11, color: "var(--od-amber)", marginBottom: 6, letterSpacing: "0.08em" }}>
            MULTI-TENANT ARCHITECTURE
          </div>
          <div style={{ fontSize: 13, color: "var(--od-text-muted)", lineHeight: 1.6 }}>
            AccuLynx API keys are per-location. Each branch gets its own key —
            you&apos;ll add more locations in Settings at any time.
          </div>
        </div>

        <Field id="loc-name" label="Location name" required error={locErrors.locName}>
          <input
            id="loc-name"
            className="od-input"
            type="text"
            value={locName}
            onChange={(e) => setLocName(e.target.value)}
            placeholder="e.g. Texas — Dallas North"
            autoFocus
          />
        </Field>

        <div style={{ paddingTop: 4, display: "flex", flexDirection: "column", gap: 10 }}>
          <button
            className="od-btn-primary"
            onClick={handleCreate}
            disabled={loading}
          >
            {loading ? (
              <>
                <div className="od-spinner" style={{ width: 14, height: 14, borderWidth: 1.5 }} />
                Creating location...
              </>
            ) : (
              <>
                Create location
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <path d="M3 7h8M8 4l3 3-3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </>
            )}
          </button>
          <button className="od-skip-link" onClick={onSkip}>
            Skip — I&apos;ll set up locations in Settings →
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Step 3 — AccuLynx API Key ─────────────────────────────────────────────────

function Step3({
  locationId,
  onSuccess,
  onSkip,
  onBack,
}: {
  locationId: string | null;
  onSuccess: () => void;
  onSkip: () => void;
  onBack: () => void;
}) {
  const [apiKey, setApiKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [keyError, setKeyError] = useState<string | null>(null);

  async function handleSave() {
    if (!apiKey.trim()) {
      setKeyError("AccuLynx API key is required");
      return;
    }
    if (!locationId) {
      setError("No location found — please go back and create one.");
      return;
    }
    setLoading(true);
    setError(null);
    setKeyError(null);
    try {
      await api.updateLocation(locationId, { acculynx_api_key: apiKey.trim() });
      onSuccess();
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Failed to save API key. Please check and try again.",
      );
    } finally {
      setLoading(false);
    }
  }

  // Mask: show only last 4 chars when hidden
  const displayValue = !showKey && apiKey.length > 4
    ? "••••••••••••" + apiKey.slice(-4)
    : apiKey;

  return (
    <div className="od-step-content">
      <StepHeader
        step={3}
        title="Connect AccuLynx"
        subtitle="Your API key is encrypted at rest and never exposed in the UI after saving."
        onBack={onBack}
      />

      <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
        {error && (
          <div className="od-card-error od-fade-up">
            <div style={{ fontSize: 13, color: "var(--od-error)" }}>{error}</div>
          </div>
        )}

        {/* Where to find the key */}
        <div className="od-card" style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
          <div style={{
            width: 28,
            height: 28,
            borderRadius: 4,
            background: "var(--od-amber-glow)",
            border: "1px solid var(--od-amber-line)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0,
            marginTop: 2,
          }}>
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <circle cx="5.5" cy="5.5" r="3" stroke="var(--od-amber)" strokeWidth="1.2" />
              <path d="M7.5 7.5l3 3" stroke="var(--od-amber)" strokeWidth="1.2" strokeLinecap="round" />
              <path d="M4 5.5h3M5.5 4v3" stroke="var(--od-amber)" strokeWidth="1.1" strokeLinecap="round" />
            </svg>
          </div>
          <div>
            <div className="od-mono" style={{ fontSize: 11, color: "var(--od-amber)", marginBottom: 4, letterSpacing: "0.06em" }}>
              WHERE TO FIND YOUR KEY
            </div>
            <div style={{ fontSize: 13, color: "var(--od-text-muted)", lineHeight: 1.6 }}>
              AccuLynx → Settings → Integrations → API Keys. Generate a key
              scoped to this branch only.
            </div>
          </div>
        </div>

        <Field id="acculynx-key" label="AccuLynx API key" required error={keyError ?? undefined}>
          <div style={{ position: "relative" }}>
            <input
              id="acculynx-key"
              className={`od-input od-input-mono`}
              type={showKey ? "text" : "password"}
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="AL-XXXXXXXX-XXXX-XXXX-XXXX"
              style={{ paddingRight: 60 }}
              autoComplete="off"
              spellCheck={false}
            />
            <button
              type="button"
              className="od-key-toggle"
              onClick={() => setShowKey((v) => !v)}
              aria-label={showKey ? "Hide API key" : "Reveal API key"}
            >
              {showKey ? "HIDE" : "SHOW"}
            </button>
          </div>
          {/* Key preview strip */}
          {apiKey.length > 0 && (
            <div
              className="od-mono od-fade-up"
              style={{
                fontSize: 11,
                color: "var(--od-text-dim)",
                marginTop: 6,
                letterSpacing: "0.1em",
              }}
            >
              Last 4: <span style={{ color: "var(--od-amber)" }}>
                {apiKey.length >= 4 ? apiKey.slice(-4) : "••••"}
              </span>
            </div>
          )}
        </Field>

        {/* Rate limit notice */}
        <div style={{
          display: "flex",
          gap: 8,
          alignItems: "center",
          padding: "8px 12px",
          background: "var(--od-surface-2)",
          border: "1px solid var(--od-border)",
          borderRadius: 4,
        }}>
          <div className="od-mono" style={{ fontSize: 10, color: "var(--od-text-dim)", letterSpacing: "0.08em" }}>
            RATE LIMIT
          </div>
          <div className="od-mono" style={{ fontSize: 11, color: "var(--od-text-muted)" }}>
            10 req/sec enforced per key — Celery-managed
          </div>
        </div>

        <div style={{ paddingTop: 4, display: "flex", flexDirection: "column", gap: 10 }}>
          <button
            className="od-btn-primary"
            onClick={handleSave}
            disabled={loading || !locationId}
          >
            {loading ? (
              <>
                <div className="od-spinner" style={{ width: 14, height: 14, borderWidth: 1.5 }} />
                Saving key...
              </>
            ) : (
              <>
                Save &amp; continue
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <path d="M3 7h8M8 4l3 3-3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </>
            )}
          </button>
          <button className="od-skip-link" onClick={onSkip}>
            Skip — connect AccuLynx later in Settings →
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Step 4 — Pricing Contract Upload ─────────────────────────────────────────

function Step4({
  onSuccess,
  onSkip,
  onBack,
}: {
  onSuccess: (mode: "contract") => void;
  onSkip: () => void;
  onBack: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function handleFileSelect(f: File) {
    const ok = /\.(pdf|csv|xlsx|xls)$/i.test(f.name);
    if (!ok) {
      setError("Accepted formats: PDF, CSV, Excel (.xlsx, .xls)");
      return;
    }
    setError(null);
    setFile(f);
  }

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files[0];
    if (f) handleFileSelect(f);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleUpload() {
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      await api.uploadPricingContract(file);
      onSuccess("contract");
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Upload failed — please try again.",
      );
    } finally {
      setUploading(false);
    }
  }

  function formatBytes(bytes: number) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  return (
    <div className="od-step-content">
      <StepHeader
        step={4}
        title="Upload pricing contract"
        subtitle="Cross-reference every invoice against your negotiated rates. This is where the money is."
        onBack={onBack}
      />

      <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
        {/* Value prop */}
        <div className="od-card-amber">
          <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
            <div
              className="od-mono"
              style={{
                fontSize: 22,
                fontWeight: 500,
                color: "var(--od-amber)",
                lineHeight: 1,
                marginTop: 1,
              }}
            >
              $8,400
            </div>
            <div>
              <div
                className="od-heading"
                style={{ fontSize: 13, color: "var(--od-amber)", marginBottom: 3 }}
              >
                avg. overcharges found
              </div>
              <div style={{ fontSize: 12, color: "var(--od-text-muted)" }}>
                in first 50 invoices for customers who upload a contract
              </div>
            </div>
          </div>
        </div>

        {error && (
          <div className="od-card-error od-fade-up">
            <div style={{ fontSize: 13, color: "var(--od-error)" }}>{error}</div>
          </div>
        )}

        {/* Dropzone */}
        <div
          className={`od-dropzone ${dragOver ? "od-dropzone-active" : ""}`}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => e.key === "Enter" && fileInputRef.current?.click()}
          aria-label="Upload pricing contract"
        >
          {dragOver && <div className="od-scan-line" />}

          {file ? (
            <div className="od-fade-up" style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 10 }}>
              {/* File icon */}
              <div style={{
                width: 44,
                height: 44,
                borderRadius: 6,
                background: "var(--od-amber-glow)",
                border: "1px solid var(--od-amber-line)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}>
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                  <path d="M4 3h8l4 4v10a1 1 0 01-1 1H5a1 1 0 01-1-1V4a1 1 0 011-1z" stroke="var(--od-amber)" strokeWidth="1.2" />
                  <path d="M12 3v4h4" stroke="var(--od-amber)" strokeWidth="1.2" strokeLinejoin="round" />
                </svg>
              </div>
              <div>
                <div
                  className="od-mono"
                  style={{ fontSize: 13, color: "var(--od-text)", marginBottom: 3 }}
                >
                  {file.name}
                </div>
                <div
                  className="od-mono"
                  style={{ fontSize: 11, color: "var(--od-text-dim)" }}
                >
                  {formatBytes(file.size)} — click to replace
                </div>
              </div>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 10 }}>
              <div style={{
                width: 44,
                height: 44,
                borderRadius: 6,
                background: "var(--od-surface-2)",
                border: "1px solid var(--od-border)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}>
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                  <path d="M10 14V6M6 10l4-4 4 4" stroke="var(--od-text-dim)" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
                  <path d="M4 15h12" stroke="var(--od-text-dim)" strokeWidth="1.2" strokeLinecap="round" opacity="0.4" />
                </svg>
              </div>
              <div>
                <div style={{ fontSize: 14, color: "var(--od-text-muted)", marginBottom: 4 }}>
                  Drop file here or click to browse
                </div>
                <div className="od-mono" style={{ fontSize: 11, color: "var(--od-text-dim)", letterSpacing: "0.06em" }}>
                  PDF · CSV · XLSX
                </div>
              </div>
            </div>
          )}

          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.csv,.xlsx,.xls"
            style={{ display: "none" }}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) handleFileSelect(f);
            }}
          />
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <button
            className="od-btn-primary"
            onClick={handleUpload}
            disabled={!file || uploading}
          >
            {uploading ? (
              <>
                <div className="od-spinner" style={{ width: 14, height: 14, borderWidth: 1.5 }} />
                Uploading &amp; parsing...
              </>
            ) : (
              <>
                Upload contract
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <path d="M3 7h8M8 4l3 3-3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </>
            )}
          </button>
          <button className="od-skip-link" onClick={onSkip}>
            Skip — build baseline from invoice history instead →
          </button>
          <div
            className="od-mono"
            style={{
              fontSize: 10,
              color: "var(--od-text-dim)",
              textAlign: "center",
              lineHeight: 1.5,
              letterSpacing: "0.04em",
            }}
          >
            Baseline mode uses your first 30 days of invoices to detect anomalies.
            Contract mode is more accurate.
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Step 5 — First Findings Preview ──────────────────────────────────────────

function Step5({
  pricingMode,
  onBack,
}: {
  pricingMode: PricingMode;
  onBack: () => void;
}) {
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setReady(true), 2800);
    return () => clearTimeout(t);
  }, []);

  return (
    <div className="od-step-content">
      <StepHeader
        step={5}
        title="Revenue scan initiated"
        subtitle={
          pricingMode === "contract"
            ? "Contract mode active — comparing every line item against your pricing agreement."
            : "Baseline mode — we'll calibrate against your invoice history."
        }
        onBack={onBack}
      />

      <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
        {/* Animated scan card */}
        {!ready ? (
          <div
            className="od-card"
            style={{
              position: "relative",
              overflow: "hidden",
              minHeight: 180,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              gap: 16,
            }}
          >
            <div className="od-scan-line" />
            <div className="od-spinner" />
            <div>
              <div
                className="od-mono"
                style={{
                  fontSize: 12,
                  color: "var(--od-text-muted)",
                  textAlign: "center",
                  letterSpacing: "0.08em",
                  marginBottom: 6,
                }}
              >
                ANALYZING DOCUMENTS
              </div>
              {/* Fake progress indicators */}
              {[
                { label: "Extracting line items", pct: 100 },
                { label: "Matching SKUs to contract", pct: 72 },
                { label: "Calculating variance", pct: 38 },
              ].map((row, i) => (
                <div
                  key={row.label}
                  style={{
                    marginBottom: i < 2 ? 8 : 0,
                    opacity: i === 0 ? 1 : i === 1 ? 0.75 : 0.5,
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      marginBottom: 4,
                    }}
                  >
                    <div
                      className="od-mono"
                      style={{ fontSize: 10, color: "var(--od-text-dim)", letterSpacing: "0.06em" }}
                    >
                      {row.label}
                    </div>
                    <div
                      className="od-mono"
                      style={{ fontSize: 10, color: "var(--od-amber)" }}
                    >
                      {row.pct}%
                    </div>
                  </div>
                  <div
                    style={{
                      height: 2,
                      background: "var(--od-border)",
                      borderRadius: 1,
                    }}
                  >
                    <div
                      style={{
                        height: "100%",
                        width: `${row.pct}%`,
                        background:
                          i === 0
                            ? "var(--od-amber)"
                            : i === 1
                              ? "var(--od-amber-dim)"
                              : "var(--od-border-bright)",
                        borderRadius: 1,
                        transition: "width 1s ease",
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="od-card-success od-fade-up">
            <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
              <div style={{
                width: 28,
                height: 28,
                borderRadius: "50%",
                background: "var(--od-success)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
                marginTop: 1,
              }}>
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <path d="M3 7l3 3 5-6" stroke="#0D0F0E" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </div>
              <div>
                <div
                  className="od-heading"
                  style={{ fontSize: 16, color: "var(--od-success)", marginBottom: 5 }}
                >
                  Setup complete. Pipeline is running.
                </div>
                <div style={{ fontSize: 13, color: "var(--od-text-muted)", lineHeight: 1.6 }}>
                  {pricingMode === "contract"
                    ? "Your pricing contract has been parsed and indexed. As invoices arrive, every line item will be cross-referenced automatically."
                    : "Baseline mode is active. After your first 30 days of invoices, we'll identify pricing anomalies based on your historical rates."}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Mode indicator */}
        <div style={{
          display: "flex",
          gap: 10,
          padding: "12px 16px",
          background: "var(--od-surface-2)",
          border: "1px solid var(--od-border)",
          borderRadius: 6,
        }}>
          <div>
            <div className="od-mono" style={{ fontSize: 10, color: "var(--od-text-dim)", letterSpacing: "0.1em", marginBottom: 4 }}>
              DETECTION MODE
            </div>
            <div
              className="od-mono"
              style={{ fontSize: 14, color: pricingMode === "contract" ? "var(--od-amber)" : "var(--od-text-muted)" }}
            >
              {pricingMode === "contract" ? "Contract Mode" : "Baseline Mode"}
            </div>
          </div>
          <div style={{ width: 1, background: "var(--od-border)", margin: "0 6px" }} />
          <div>
            <div className="od-mono" style={{ fontSize: 10, color: "var(--od-text-dim)", letterSpacing: "0.1em", marginBottom: 4 }}>
              STATUS
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <div style={{
                width: 6,
                height: 6,
                borderRadius: "50%",
                background: "var(--od-success)",
                animation: "nodePulse 2s ease-in-out infinite",
              }} />
              <div className="od-mono" style={{ fontSize: 12, color: "var(--od-success)" }}>
                Processing
              </div>
            </div>
          </div>
        </div>

        {/* CTA buttons */}
        <div style={{ display: "flex", flexDirection: "column", gap: 10, paddingTop: 4 }}>
          <a
            href="/dashboard/c-suite"
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 8,
              background: "var(--od-amber)",
              color: "#0D0F0E",
              borderRadius: 4,
              padding: "11px 20px",
              fontFamily: "'Syne', sans-serif",
              fontSize: 14,
              fontWeight: 700,
              letterSpacing: "0.06em",
              textTransform: "uppercase",
              textDecoration: "none",
              transition: "opacity 0.15s",
            }}
          >
            Open Revenue Dashboard
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M3 7h8M8 4l3 3-3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </a>
          <a
            href="/dashboard"
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 6,
              background: "transparent",
              border: "1px solid var(--od-border)",
              color: "var(--od-text-muted)",
              borderRadius: 4,
              padding: "10px 20px",
              fontFamily: "'DM Sans', sans-serif",
              fontSize: 13,
              textDecoration: "none",
              transition: "border-color 0.15s, color 0.15s",
            }}
          >
            Go to main dashboard
          </a>
        </div>

        <div
          className="od-mono"
          style={{
            fontSize: 10,
            color: "var(--od-text-dim)",
            textAlign: "center",
            letterSpacing: "0.05em",
            lineHeight: 1.6,
          }}
        >
          Processing continues in background. Results appear as each document completes.
        </div>
      </div>
    </div>
  );
}

// ─── Main Onboarding Page ─────────────────────────────────────────────────────

export default function OnboardingPage() {
  const [step, setStep] = useState<OnboardingStep>(1);
  const [org, setOrg] = useState<Organization | null>(null);
  const [locationId, setLocationId] = useState<string | null>(null);
  const [pricingMode, setPricingMode] = useState<PricingMode>(null);

  useEffect(() => {
    api.getOrganization().then(setOrg).catch(() => {});
  }, []);

  return (
    <>
      {/* Font + design system injection */}
      <style dangerouslySetInnerHTML={{ __html: GLOBAL_CSS }} />

      <div
        className="od-body"
        style={{
          display: "flex",
          minHeight: "100vh",
          // Subtle grid texture
          backgroundImage:
            "radial-gradient(circle at 20% 80%, rgba(232,160,32,0.03) 0%, transparent 50%), " +
            "linear-gradient(rgba(37,40,37,0.3) 1px, transparent 1px), " +
            "linear-gradient(90deg, rgba(37,40,37,0.3) 1px, transparent 1px)",
          backgroundSize: "100% 100%, 40px 40px, 40px 40px",
        }}
      >
        {/* Left sidebar — step rail */}
        <div
          style={{
            width: 240,
            flexShrink: 0,
            borderRight: "1px solid var(--od-border)",
            padding: "40px 32px",
            display: "flex",
            flexDirection: "column",
            background: "rgba(20,22,20,0.6)",
            backdropFilter: "blur(8px)",
          }}
        >
          <StepRail current={step} />
        </div>

        {/* Right — form area */}
        <div
          style={{
            flex: 1,
            display: "flex",
            alignItems: "flex-start",
            justifyContent: "center",
            padding: "80px 64px",
            overflowY: "auto",
          }}
        >
          <div style={{ width: "100%", maxWidth: 480 }}>
            {/* Amber accent line at top */}
            <div
              style={{
                height: 2,
                background: "linear-gradient(90deg, var(--od-amber), transparent)",
                borderRadius: 1,
                marginBottom: 48,
                width: "40%",
              }}
            />

            {step === 1 && (
              <Step1 onContinue={() => setStep(2)} />
            )}
            {step === 2 && (
              <Step2
                org={org}
                onSuccess={(id) => {
                  setLocationId(id);
                  setStep(3);
                }}
                onSkip={() => setStep(3)}
                onBack={() => setStep(1)}
              />
            )}
            {step === 3 && (
              <Step3
                locationId={locationId}
                onSuccess={() => setStep(4)}
                onSkip={() => setStep(4)}
                onBack={() => setStep(2)}
              />
            )}
            {step === 4 && (
              <Step4
                onSuccess={(mode) => {
                  setPricingMode(mode);
                  setStep(5);
                }}
                onSkip={() => {
                  setPricingMode("baseline");
                  setStep(5);
                }}
                onBack={() => setStep(3)}
              />
            )}
            {step === 5 && (
              <Step5
                pricingMode={pricingMode}
                onBack={() => setStep(4)}
              />
            )}
          </div>
        </div>
      </div>
    </>
  );
}
