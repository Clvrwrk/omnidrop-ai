"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api-client";
import type {
  Location,
  Organization,
  UploadPricingContractResponse,
} from "@/lib/types";

// ─── Design System ────────────────────────────────────────────────────────────
// "The Instrument Panel" — Swiss-watchmaker precision config surface
// Inherits Precision Instrument tokens

const ST_CSS = `
  @import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Mono:ital,wght@0,300;0,400;0,500;1,300&family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;1,9..40,300&display=swap');

  :root {
    --od-bg:            #0D0F0E;
    --od-surface:       #141614;
    --od-surface-2:     #1A1C1A;
    --od-surface-3:     #1F211F;
    --od-border:        #252825;
    --od-border-bright: #303530;
    --od-amber:         #E8A020;
    --od-amber-dim:     #7A5510;
    --od-amber-glow:    rgba(232,160,32,0.10);
    --od-amber-line:    rgba(232,160,32,0.28);
    --od-text:          #F0EDE6;
    --od-text-muted:    #6B7068;
    --od-text-dim:      #3D403C;
    --od-success:       #4CAF7D;
    --od-success-dim:   rgba(76,175,125,0.12);
    --od-error:         #E05252;
    --od-error-dim:     rgba(224,82,82,0.12);
    --od-warn:          #D48A1A;
  }

  .st-root {
    font-family: 'DM Sans', sans-serif;
    background: var(--od-bg);
    color: var(--od-text);
    min-height: 100vh;
    display: flex;
  }

  .st-heading { font-family: 'Syne',    sans-serif;  letter-spacing: -0.02em; }
  .st-mono    { font-family: 'DM Mono', monospace;   letter-spacing: 0.03em; }

  /* ── Left nav ── */
  .st-nav {
    width: 220px;
    flex-shrink: 0;
    border-right: 1px solid var(--od-border);
    display: flex;
    flex-direction: column;
    padding: 32px 0;
    background: var(--od-surface);
  }

  .st-nav-brand {
    padding: 0 24px 28px;
    border-bottom: 1px solid var(--od-border);
    margin-bottom: 8px;
  }

  .st-nav-tab {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 24px;
    background: none;
    border: none;
    border-left: 2px solid transparent;
    cursor: pointer;
    text-align: left;
    width: 100%;
    transition: background 0.12s, border-color 0.12s, color 0.12s;
    color: var(--od-text-muted);
  }
  .st-nav-tab:hover:not(.st-nav-tab-active) {
    background: var(--od-surface-2);
    color: var(--od-text);
  }
  .st-nav-tab-active {
    border-left-color: var(--od-amber);
    background: var(--od-surface-2);
    color: var(--od-text);
  }
  .st-nav-tab-icon {
    width: 16px;
    height: 16px;
    flex-shrink: 0;
    opacity: 0.6;
  }
  .st-nav-tab-active .st-nav-tab-icon { opacity: 1; }

  /* ── Main content ── */
  .st-main {
    flex: 1;
    overflow-y: auto;
    padding: 36px 40px;
    max-width: 760px;
  }

  /* Tab content fade-in */
  @keyframes tabFadeIn {
    from { opacity: 0; transform: translateY(6px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  .st-tab-content { animation: tabFadeIn 0.22s ease both; }

  /* ── Section panel ── */
  .st-panel {
    border: 1px solid var(--od-border);
    border-radius: 6px;
    background: var(--od-surface);
    overflow: hidden;
    margin-bottom: 20px;
  }
  .st-panel-header {
    padding: 14px 20px;
    border-bottom: 1px solid var(--od-border);
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .st-panel-body { padding: 20px; }
  .st-panel-body-flush { padding: 0; }

  /* ── Form fields ── */
  .st-field { margin-bottom: 16px; }
  .st-field:last-child { margin-bottom: 0; }

  .st-label {
    display: block;
    font-family: 'DM Mono', monospace;
    font-size: 10px;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--od-text-muted);
    margin-bottom: 6px;
  }
  .st-label-required::after { content: ' *'; color: var(--od-amber); }

  .st-input {
    width: 100%;
    background: var(--od-surface-2);
    border: 1px solid var(--od-border);
    border-radius: 4px;
    padding: 9px 12px;
    color: var(--od-text);
    font-family: 'DM Sans', sans-serif;
    font-size: 13px;
    outline: none;
    transition: border-color 0.15s, box-shadow 0.15s;
    box-sizing: border-box;
  }
  .st-input::placeholder {
    color: var(--od-text-dim);
    font-family: 'DM Mono', monospace;
    font-size: 12px;
  }
  .st-input:focus {
    border-color: var(--od-amber);
    box-shadow: 0 0 0 2px var(--od-amber-glow);
  }
  .st-input-mono {
    font-family: 'DM Mono', monospace;
    font-size: 12px;
    letter-spacing: 0.04em;
  }

  /* Key input with toggle */
  .st-key-wrap { position: relative; }
  .st-key-toggle {
    position: absolute;
    right: 10px;
    top: 50%;
    transform: translateY(-50%);
    background: none;
    border: none;
    font-family: 'DM Mono', monospace;
    font-size: 9px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--od-amber-dim);
    cursor: pointer;
    transition: color 0.12s;
    padding: 2px 4px;
  }
  .st-key-toggle:hover { color: var(--od-amber); }

  /* ── Buttons ── */
  .st-btn-primary {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    padding: 8px 16px;
    background: var(--od-amber);
    color: #0D0F0E;
    border: none;
    border-radius: 4px;
    font-family: 'Syne', sans-serif;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    cursor: pointer;
    transition: opacity 0.12s, transform 0.1s;
    flex-shrink: 0;
  }
  .st-btn-primary:hover:not(:disabled) { opacity: 0.88; transform: translateY(-1px); }
  .st-btn-primary:active:not(:disabled) { transform: translateY(0); }
  .st-btn-primary:disabled { opacity: 0.3; cursor: not-allowed; }

  .st-btn-ghost {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    padding: 7px 14px;
    background: transparent;
    border: 1px solid var(--od-border-bright);
    border-radius: 4px;
    color: var(--od-text-muted);
    font-family: 'DM Mono', monospace;
    font-size: 11px;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    cursor: pointer;
    transition: border-color 0.12s, color 0.12s;
    flex-shrink: 0;
  }
  .st-btn-ghost:hover:not(:disabled) { border-color: var(--od-amber); color: var(--od-amber); }
  .st-btn-ghost:disabled { opacity: 0.35; cursor: not-allowed; }

  .st-btn-danger {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    background: none;
    border: none;
    font-family: 'DM Mono', monospace;
    font-size: 10px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--od-text-dim);
    cursor: pointer;
    transition: color 0.12s;
    padding: 4px 0;
  }
  .st-btn-danger:hover { color: var(--od-error); }

  /* ── Inline status ticker ── */
  @keyframes tickerIn {
    from { opacity: 0; transform: translateX(-6px); }
    to   { opacity: 1; transform: translateX(0); }
  }
  .st-ticker {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-family: 'DM Mono', monospace;
    font-size: 11px;
    letter-spacing: 0.06em;
    animation: tickerIn 0.2s ease both;
  }
  .st-ticker-ok  { color: var(--od-success); }
  .st-ticker-err { color: var(--od-error); }
  .st-ticker-inf { color: var(--od-text-muted); }

  /* ── Connection status badges ── */
  .st-conn-badge {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 2px 8px;
    border-radius: 3px;
    font-family: 'DM Mono', monospace;
    font-size: 10px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
  .st-conn-active   { background: var(--od-success-dim); border: 1px solid rgba(76,175,125,0.25); color: var(--od-success); }
  .st-conn-invalid  { background: var(--od-error-dim);   border: 1px solid rgba(224,82,82,0.25);  color: var(--od-error); }
  .st-conn-untested { background: rgba(107,112,104,0.12); border: 1px solid rgba(107,112,104,0.22); color: var(--od-text-muted); }

  /* ── Location rows ── */
  .st-loc-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 14px 20px;
    border-bottom: 1px solid var(--od-border);
    gap: 12px;
    transition: background 0.12s;
  }
  .st-loc-row:last-child { border-bottom: none; }
  .st-loc-row:hover { background: var(--od-surface-2); }

  /* ── Divider ── */
  .st-divider {
    border: none;
    border-top: 1px solid var(--od-border);
    margin: 18px 0;
  }

  /* ── Spinner ── */
  @keyframes spin360 { to { transform: rotate(360deg); } }
  .st-spinner {
    width: 11px; height: 11px;
    border: 1.5px solid rgba(13,15,14,0.3);
    border-top-color: #0D0F0E;
    border-radius: 50%;
    animation: spin360 0.7s linear infinite;
    flex-shrink: 0;
  }
  .st-spinner-amber {
    border-color: var(--od-amber-dim);
    border-top-color: var(--od-amber);
  }

  /* ── Dropzone ── */
  .st-drop {
    border: 1px dashed var(--od-border-bright);
    border-radius: 5px;
    padding: 32px 20px;
    text-align: center;
    cursor: pointer;
    transition: border-color 0.15s, background 0.15s;
    position: relative;
    overflow: hidden;
  }
  .st-drop:hover   { border-color: var(--od-amber-dim); background: var(--od-amber-glow); }
  .st-drop-active  { border-color: var(--od-amber) !important; background: var(--od-amber-glow) !important; border-style: solid; }

  /* ── Upload result card ── */
  .st-upload-result {
    border: 1px solid rgba(76,175,125,0.28);
    background: var(--od-success-dim);
    border-radius: 5px;
    padding: 14px 18px;
    animation: tickerIn 0.25s ease both;
  }

  /* ── Error bar ── */
  .st-error {
    background: var(--od-error-dim);
    border: 1px solid rgba(224,82,82,0.28);
    border-radius: 4px;
    padding: 10px 14px;
    font-size: 13px;
    color: var(--od-error);
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 18px;
    animation: tickerIn 0.2s ease both;
  }

  /* ── Grid for form rows ── */
  .st-grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }

  /* ── Vendor chip list ── */
  .st-chip {
    display: inline-block;
    padding: 2px 8px;
    background: var(--od-amber-glow);
    border: 1px solid var(--od-amber-line);
    border-radius: 3px;
    font-family: 'DM Mono', monospace;
    font-size: 11px;
    color: var(--od-amber);
    letter-spacing: 0.04em;
    margin: 3px 3px 3px 0;
  }

  /* ── Scrollbar ── */
  .st-main::-webkit-scrollbar { width: 3px; }
  .st-main::-webkit-scrollbar-track { background: transparent; }
  .st-main::-webkit-scrollbar-thumb { background: var(--od-border-bright); border-radius: 2px; }

  /* ── Notification location selector ── */
  .st-loc-selector {
    display: flex;
    flex-direction: column;
    gap: 1px;
    border: 1px solid var(--od-border);
    border-radius: 4px;
    overflow: hidden;
    background: var(--od-border);
    margin-bottom: 20px;
  }
  .st-loc-select-btn {
    padding: 10px 14px;
    background: var(--od-surface-2);
    border: none;
    text-align: left;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    transition: background 0.12s;
    color: var(--od-text-muted);
  }
  .st-loc-select-btn:hover { background: var(--od-surface-3); }
  .st-loc-select-btn-active {
    background: var(--od-surface-3);
    color: var(--od-text);
    border-left: 2px solid var(--od-amber);
  }

  /* empty state */
  .st-empty {
    padding: 36px 20px;
    text-align: center;
    opacity: 0.45;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 10px;
  }
`;

// ─── Types ────────────────────────────────────────────────────────────────────

type Tab = "locations" | "notifications" | "pricing";

interface SlackState {
  webhookUrl: string;
  channel: string;
  saving: boolean;
  testing: boolean;
  saveMsg: string | null;
  saveOk:  boolean | null;
  testMsg: string | null;
  testOk:  boolean | null;
}

function initSlack(loc: Location): SlackState {
  return {
    webhookUrl: loc.notification_channels?.slack?.webhook_url ?? "",
    channel:    loc.notification_channels?.slack?.channel     ?? "",
    saving: false, testing: false,
    saveMsg: null, saveOk:  null,
    testMsg: null, testOk:  null,
  };
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function ConnBadge({ status }: { status: string }) {
  const cls =
    status === "active"   ? "st-conn-active"   :
    status === "invalid"  ? "st-conn-invalid"  : "st-conn-untested";
  const dot =
    status === "active"   ? "var(--od-success)" :
    status === "invalid"  ? "var(--od-error)"   : "var(--od-text-dim)";
  return (
    <span className={`st-conn-badge ${cls}`}>
      <span style={{ width: 5, height: 5, borderRadius: "50%", background: dot, display: "inline-block", flexShrink: 0 }} />
      {status}
    </span>
  );
}

function Ticker({ msg, ok }: { msg: string; ok: boolean | null }) {
  const cls = ok === true ? "st-ticker-ok" : ok === false ? "st-ticker-err" : "st-ticker-inf";
  const icon = ok === true ? "✓" : ok === false ? "✗" : "·";
  return (
    <span className={`st-ticker ${cls}`}>
      <span style={{ fontSize: 12 }}>{icon}</span>
      {msg}
    </span>
  );
}

function Field({
  id, label, required, children,
}: { id: string; label: string; required?: boolean; children: React.ReactNode }) {
  return (
    <div className="st-field">
      <label htmlFor={id} className={`st-label${required ? " st-label-required" : ""}`}>{label}</label>
      {children}
    </div>
  );
}

function SectionHeader({ title, subtitle, action }: {
  title: string; subtitle?: string; action?: React.ReactNode;
}) {
  return (
    <div className="st-panel-header">
      <div>
        <div className="st-heading" style={{ fontSize: 15, fontWeight: 700, color: "var(--od-text)" }}>{title}</div>
        {subtitle && <div style={{ fontSize: 12, color: "var(--od-text-muted)", marginTop: 2 }}>{subtitle}</div>}
      </div>
      {action}
    </div>
  );
}

// ─── Locations Tab ────────────────────────────────────────────────────────────

function LocationsTab({
  locations, org, onRefresh,
}: { locations: Location[]; org: Organization | null; onRefresh: () => void }) {
  const [name,     setName]     = useState("");
  const [apiKey,   setApiKey]   = useState("");
  const [showKey,  setShowKey]  = useState(false);
  const [adding,   setAdding]   = useState(false);
  const [addErr,   setAddErr]   = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [delErr,   setDelErr]   = useState<string | null>(null);

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || !apiKey.trim() || !org) return;
    setAdding(true); setAddErr(null);
    try {
      await api.createLocation({ name: name.trim(), acculynx_api_key: apiKey.trim(), organization_id: org.organization_id });
      setName(""); setApiKey("");
      onRefresh();
    } catch (err) {
      setAddErr(err instanceof ApiError ? err.message : "Failed to add location.");
    } finally { setAdding(false); }
  }

  async function handleDelete(id: string) {
    setDeleting(id); setDelErr(null);
    try {
      await api.deleteLocation(id);
      onRefresh();
    } catch (err) {
      setDelErr(
        err instanceof ApiError && err.status === 409
          ? "Cannot remove — unprocessed jobs exist for this location."
          : err instanceof ApiError ? err.message : "Delete failed."
      );
    } finally { setDeleting(null); }
  }

  return (
    <div className="st-tab-content">
      {/* Existing locations */}
      <div className="st-panel">
        <SectionHeader
          title="Registered Locations"
          subtitle="Each branch has its own AccuLynx API key"
          action={
            <div className="st-mono" style={{ fontSize: 10, color: "var(--od-text-dim)", letterSpacing: "0.1em" }}>
              {locations.length} LOCATION{locations.length !== 1 ? "S" : ""}
            </div>
          }
        />
        <div className="st-panel-body-flush">
          {delErr && (
            <div style={{ padding: "10px 20px 0" }}>
              <div className="st-error">{delErr}</div>
            </div>
          )}
          {locations.length === 0 ? (
            <div className="st-empty">
              <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
                <rect x="4" y="8" width="24" height="16" rx="2" stroke="currentColor" strokeWidth="1.2"/>
                <path d="M10 14h12M10 18h6" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
              </svg>
              <div className="st-mono" style={{ fontSize: 11, letterSpacing: "0.08em", textTransform: "uppercase" }}>No locations yet</div>
              <div style={{ fontSize: 12 }}>Add your first AccuLynx branch below</div>
            </div>
          ) : (
            locations.map(loc => (
              <div key={loc.location_id} className="st-loc-row">
                {/* Name + meta */}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="st-mono" style={{ fontSize: 13, color: "var(--od-text)", marginBottom: 3 }}>
                    {loc.name}
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <div className="st-mono" style={{ fontSize: 10, color: "var(--od-text-dim)" }}>
                      KEY ****{loc.api_key_last4}
                    </div>
                    <div style={{ color: "var(--od-border-bright)", fontSize: 10 }}>·</div>
                    <div className="st-mono" style={{ fontSize: 10, color: "var(--od-text-dim)" }}>
                      {new Date(loc.created_at).toLocaleDateString()}
                    </div>
                  </div>
                </div>
                {/* Right side */}
                <div style={{ display: "flex", alignItems: "center", gap: 12, flexShrink: 0 }}>
                  <ConnBadge status={loc.connection_status} />
                  <button
                    className="st-btn-danger"
                    onClick={() => handleDelete(loc.location_id)}
                    disabled={deleting === loc.location_id}
                  >
                    {deleting === loc.location_id ? <div className="st-spinner st-spinner-amber" /> : null}
                    Remove
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Add location form */}
      <div className="st-panel">
        <SectionHeader title="Add Location" subtitle="Register a new branch and AccuLynx API key" />
        <div className="st-panel-body">
          {addErr && <div className="st-error">{addErr}</div>}
          <form onSubmit={handleAdd}>
            <div className="st-grid-2" style={{ marginBottom: 14 }}>
              <Field id="loc-name" label="Location name" required>
                <input
                  id="loc-name" className="st-input" type="text"
                  value={name} onChange={e => setName(e.target.value)}
                  placeholder="e.g. Dallas North" autoComplete="off"
                />
              </Field>
              <Field id="api-key" label="AccuLynx API key" required>
                <div className="st-key-wrap">
                  <input
                    id="api-key"
                    className={`st-input st-input-mono`}
                    style={{ paddingRight: 52 }}
                    type={showKey ? "text" : "password"}
                    value={apiKey}
                    onChange={e => setApiKey(e.target.value)}
                    placeholder="AL-XXXX-XXXX"
                    autoComplete="off"
                    spellCheck={false}
                  />
                  <button type="button" className="st-key-toggle" onClick={() => setShowKey(v => !v)}>
                    {showKey ? "HIDE" : "SHOW"}
                  </button>
                </div>
              </Field>
            </div>

            {/* Rate limit notice */}
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16, padding: "7px 10px", background: "var(--od-surface-2)", border: "1px solid var(--od-border)", borderRadius: 4 }}>
              <div className="st-mono" style={{ fontSize: 9, color: "var(--od-text-dim)", letterSpacing: "0.1em" }}>RATE LIMIT</div>
              <div className="st-mono" style={{ fontSize: 11, color: "var(--od-text-dim)" }}>10 req/sec · Celery-managed per key</div>
            </div>

            <button type="submit" className="st-btn-primary" disabled={adding || !name.trim() || !apiKey.trim() || !org}>
              {adding ? <><div className="st-spinner" />Adding...</> : <>Add Location</>}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}

// ─── Notifications Tab ────────────────────────────────────────────────────────

function NotificationsTab({ locations }: { locations: Location[] }) {
  const [selected, setSelected] = useState<string | null>(locations[0]?.location_id ?? null);
  const [forms, setForms] = useState<Record<string, SlackState>>(() => {
    const init: Record<string, SlackState> = {};
    for (const loc of locations) init[loc.location_id] = initSlack(loc);
    return init;
  });

  // Sync if locations change
  useEffect(() => {
    setForms(prev => {
      const next = { ...prev };
      for (const loc of locations) {
        if (!next[loc.location_id]) next[loc.location_id] = initSlack(loc);
      }
      return next;
    });
    if (!selected && locations.length > 0) setSelected(locations[0].location_id);
  }, [locations, selected]);

  function patch(id: string, delta: Partial<SlackState>) {
    setForms(prev => ({ ...prev, [id]: { ...prev[id], ...delta } }));
  }

  async function handleSave(id: string) {
    const f = forms[id]; if (!f) return;
    patch(id, { saving: true, saveMsg: null, saveOk: null });
    try {
      await api.updateLocationNotifications(id, {
        slack_webhook_url: f.webhookUrl.trim() || null,
        slack_channel: f.channel.trim() || null,
      });
      patch(id, { saving: false, saveMsg: "Saved", saveOk: true });
    } catch (err) {
      patch(id, { saving: false, saveMsg: err instanceof ApiError ? err.message : "Save failed", saveOk: false });
    }
  }

  async function handleTest(id: string) {
    patch(id, { testing: true, testMsg: null, testOk: null });
    try {
      const res = await api.testLocationNotifications(id);
      patch(id, { testing: false, testMsg: res.success ? "Message delivered" : res.message ?? "Failed", testOk: res.success });
    } catch {
      patch(id, { testing: false, testMsg: "Delivery failed — check URL", testOk: false });
    }
  }

  const activeLoc = locations.find(l => l.location_id === selected);
  const activeForm = selected ? forms[selected] : null;

  return (
    <div className="st-tab-content">
      {locations.length === 0 ? (
        <div className="st-panel">
          <div className="st-empty">
            <div className="st-mono" style={{ fontSize: 11, letterSpacing: "0.08em", textTransform: "uppercase" }}>No locations configured</div>
            <div style={{ fontSize: 12 }}>Add a location first to configure notifications</div>
          </div>
        </div>
      ) : (
        <>
          {/* Location selector */}
          <div className="st-panel" style={{ marginBottom: 20 }}>
            <SectionHeader title="Select Location" subtitle="Notifications are configured per branch" />
            <div className="st-panel-body-flush">
              {locations.map(loc => (
                <button
                  key={loc.location_id}
                  className={`st-loc-select-btn${selected === loc.location_id ? " st-loc-select-btn-active" : ""}`}
                  style={{ width: "100%" }}
                  onClick={() => setSelected(loc.location_id)}
                >
                  <div>
                    <div className="st-mono" style={{ fontSize: 12, color: "inherit" }}>{loc.name}</div>
                    {forms[loc.location_id]?.webhookUrl && (
                      <div className="st-mono" style={{ fontSize: 10, color: "var(--od-text-dim)", marginTop: 2 }}>
                        Slack configured
                      </div>
                    )}
                  </div>
                  <ConnBadge status={loc.connection_status} />
                </button>
              ))}
            </div>
          </div>

          {/* Slack form for selected location */}
          {activeLoc && activeForm && (
            <div className="st-panel">
              <SectionHeader
                title={`Notifications — ${activeLoc.name}`}
                subtitle="Slack Incoming Webhook · bounce-back alerts sent here"
              />
              <div className="st-panel-body">
                <Field id="slack-url" label="Slack webhook URL">
                  <input
                    id="slack-url"
                    className="st-input st-input-mono"
                    type="text"
                    value={activeForm.webhookUrl}
                    onChange={e => patch(selected!, { webhookUrl: e.target.value, saveMsg: null, testMsg: null })}
                    placeholder="https://hooks.slack.com/services/T.../B.../..."
                    autoComplete="off"
                    spellCheck={false}
                  />
                </Field>

                <Field id="slack-channel" label="Channel (optional)">
                  <input
                    id="slack-channel"
                    className="st-input"
                    type="text"
                    value={activeForm.channel}
                    onChange={e => patch(selected!, { channel: e.target.value })}
                    placeholder="#field-ops"
                  />
                </Field>

                {/* Info note */}
                <div style={{ background: "var(--od-surface-2)", border: "1px solid var(--od-border)", borderRadius: 4, padding: "8px 12px", marginBottom: 16, display: "flex", gap: 8, alignItems: "flex-start" }}>
                  <div className="st-mono" style={{ fontSize: 10, color: "var(--od-amber)", letterSpacing: "0.08em", flexShrink: 0, marginTop: 1 }}>INFO</div>
                  <div style={{ fontSize: 12, color: "var(--od-text-muted)", lineHeight: 1.5 }}>
                    Low-context documents (score 0–39) trigger a bounce-back message here with a deep link to the job review page.
                  </div>
                </div>

                {/* Action row */}
                <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                  <button
                    className="st-btn-primary"
                    onClick={() => handleSave(selected!)}
                    disabled={activeForm.saving}
                  >
                    {activeForm.saving ? <><div className="st-spinner" />Saving...</> : <>Save</>}
                  </button>
                  <button
                    className="st-btn-ghost"
                    onClick={() => handleTest(selected!)}
                    disabled={activeForm.testing || !activeForm.webhookUrl.trim()}
                    title={!activeForm.webhookUrl.trim() ? "Enter a webhook URL first" : "Send a test message"}
                  >
                    {activeForm.testing ? <><div className="st-spinner st-spinner-amber" />Testing...</> : <>Test</>}
                  </button>
                  {activeForm.saveMsg && <Ticker msg={activeForm.saveMsg} ok={activeForm.saveOk} />}
                  {activeForm.testMsg && <Ticker msg={activeForm.testMsg} ok={activeForm.testOk} />}
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ─── Pricing Tab ──────────────────────────────────────────────────────────────

function PricingTab() {
  const [dragOver, setDragOver]   = useState(false);
  const [file,     setFile]       = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [result,   setResult]     = useState<UploadPricingContractResponse | null>(null);
  const [error,    setError]      = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  function handleFileSelect(f: File) {
    if (!/\.(pdf|csv|xlsx|xls)$/i.test(f.name)) {
      setError("Accepted formats: PDF, CSV, Excel (.xlsx, .xls)");
      return;
    }
    setError(null); setResult(null); setFile(f);
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault(); setDragOver(false);
    const f = e.dataTransfer.files[0];
    if (f) handleFileSelect(f);
  }

  async function handleUpload() {
    if (!file) return;
    setUploading(true); setError(null); setResult(null);
    try {
      const res = await api.uploadPricingContract(file);
      setResult(res); setFile(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed — please try again.");
    } finally { setUploading(false); }
  }

  function fmtBytes(b: number) {
    if (b < 1024) return `${b}B`;
    if (b < 1048576) return `${(b/1024).toFixed(0)}KB`;
    return `${(b/1048576).toFixed(1)}MB`;
  }

  return (
    <div className="st-tab-content">
      <div className="st-panel">
        <SectionHeader
          title="Pricing Contracts"
          subtitle="Upload a CSV or PDF — we parse and index every line item for leakage detection"
        />
        <div className="st-panel-body">
          {/* Mode explanation */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 20 }}>
            {[
              { label: "Contract Mode", desc: "Exact line-item match against your uploaded rates. Most accurate.", color: "var(--od-amber)" },
              { label: "Baseline Mode", desc: "Statistical baseline from 30+ days of invoices. Fallback when no contract.", color: "var(--od-text-muted)" },
            ].map(m => (
              <div key={m.label} style={{ padding: "10px 14px", background: "var(--od-surface-2)", border: "1px solid var(--od-border)", borderRadius: 4 }}>
                <div className="st-mono" style={{ fontSize: 10, color: m.color, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 4 }}>{m.label}</div>
                <div style={{ fontSize: 12, color: "var(--od-text-muted)", lineHeight: 1.5 }}>{m.desc}</div>
              </div>
            ))}
          </div>

          {error && <div className="st-error">{error}</div>}

          {/* Result card */}
          {result && (
            <div className="st-upload-result" style={{ marginBottom: 16 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <circle cx="7" cy="7" r="6" stroke="var(--od-success)" strokeWidth="1.2"/>
                  <path d="M4 7l2 2 4-4" stroke="var(--od-success)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
                <div className="st-mono" style={{ fontSize: 11, color: "var(--od-success)", letterSpacing: "0.08em" }}>
                  CONTRACT PARSED SUCCESSFULLY
                </div>
              </div>
              <div style={{ display: "flex", gap: 20, marginBottom: result.vendors_found?.length ? 10 : 0 }}>
                <div>
                  <div className="st-mono" style={{ fontSize: 10, color: "var(--od-text-dim)", letterSpacing: "0.08em", marginBottom: 2 }}>ROWS INSERTED</div>
                  <div className="st-mono" style={{ fontSize: 20, color: "var(--od-text)" }}>{result.rows_inserted?.toLocaleString() ?? "—"}</div>
                </div>
                {result.effective_date && (
                  <div>
                    <div className="st-mono" style={{ fontSize: 10, color: "var(--od-text-dim)", letterSpacing: "0.08em", marginBottom: 2 }}>EFFECTIVE DATE</div>
                    <div className="st-mono" style={{ fontSize: 14, color: "var(--od-text-muted)" }}>{result.effective_date}</div>
                  </div>
                )}
              </div>
              {(result.vendors_found?.length ?? 0) > 0 && (
                <>
                  <div className="st-mono" style={{ fontSize: 10, color: "var(--od-text-dim)", letterSpacing: "0.08em", marginBottom: 6 }}>VENDORS INDEXED</div>
                  <div>{result.vendors_found!.map(v => <span key={v} className="st-chip">{v}</span>)}</div>
                </>
              )}
            </div>
          )}

          {/* Dropzone */}
          <div
            className={`st-drop ${dragOver ? "st-drop-active" : ""}`}
            onDragOver={e => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            onClick={() => fileRef.current?.click()}
            role="button"
            tabIndex={0}
            onKeyDown={e => e.key === "Enter" && fileRef.current?.click()}
            aria-label="Upload pricing contract"
          >
            {file ? (
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
                <div style={{ width: 36, height: 36, borderRadius: 5, background: "var(--od-amber-glow)", border: "1px solid var(--od-amber-line)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <path d="M3 2.5h7l3 3V13a.5.5 0 01-.5.5h-9A.5.5 0 013 13V2.5z" stroke="var(--od-amber)" strokeWidth="1.1"/>
                    <path d="M10 2.5V6h3" stroke="var(--od-amber)" strokeWidth="1.1" strokeLinejoin="round"/>
                  </svg>
                </div>
                <div className="st-mono" style={{ fontSize: 12, color: "var(--od-text)" }}>{file.name}</div>
                <div className="st-mono" style={{ fontSize: 10, color: "var(--od-text-dim)" }}>{fmtBytes(file.size)} — click to replace</div>
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
                <div style={{ width: 36, height: 36, borderRadius: 5, background: "var(--od-surface-3)", border: "1px solid var(--od-border)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <path d="M8 11V5M5 8l3-3 3 3" stroke="var(--od-text-dim)" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
                    <path d="M3 12h10" stroke="var(--od-text-dim)" strokeWidth="1.1" strokeLinecap="round" opacity="0.4"/>
                  </svg>
                </div>
                <div style={{ fontSize: 13, color: "var(--od-text-muted)" }}>Drop contract or click to browse</div>
                <div className="st-mono" style={{ fontSize: 10, color: "var(--od-text-dim)", letterSpacing: "0.1em" }}>PDF · CSV · XLSX</div>
              </div>
            )}
            <input ref={fileRef} type="file" accept=".pdf,.csv,.xlsx,.xls" style={{ display: "none" }}
              onChange={e => { const f = e.target.files?.[0]; if (f) handleFileSelect(f); }} />
          </div>

          {/* Upload button */}
          <div style={{ marginTop: 14, display: "flex", alignItems: "center", gap: 10 }}>
            <button
              className="st-btn-primary"
              onClick={handleUpload}
              disabled={!file || uploading}
            >
              {uploading
                ? <><div className="st-spinner" />Parsing contract...</>
                : <>Upload &amp; Index</>}
            </button>
            {file && !uploading && (
              <button className="st-btn-ghost" onClick={() => { setFile(null); setError(null); }}>
                Clear
              </button>
            )}
          </div>

          {/* Org scope note */}
          <div style={{ marginTop: 14 }}>
            <div className="st-mono" style={{ fontSize: 10, color: "var(--od-text-dim)", letterSpacing: "0.06em", lineHeight: 1.6 }}>
              Pricing contracts are org-scoped — they apply across all locations. Upload one contract and every branch uses it for leakage detection.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

const TAB_META: { key: Tab; label: string; icon: React.ReactNode }[] = [
  {
    key: "locations",
    label: "Locations",
    icon: (
      <svg className="st-nav-tab-icon" viewBox="0 0 16 16" fill="none">
        <path d="M8 2a4 4 0 100 8A4 4 0 008 2z" stroke="currentColor" strokeWidth="1.2"/>
        <path d="M8 10v4M6 14h4" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
      </svg>
    ),
  },
  {
    key: "notifications",
    label: "Notifications",
    icon: (
      <svg className="st-nav-tab-icon" viewBox="0 0 16 16" fill="none">
        <path d="M8 2a5 5 0 015 5v3l1 2H2l1-2V7a5 5 0 015-5z" stroke="currentColor" strokeWidth="1.2"/>
        <path d="M6.5 13a1.5 1.5 0 003 0" stroke="currentColor" strokeWidth="1.2"/>
      </svg>
    ),
  },
  {
    key: "pricing",
    label: "Pricing",
    icon: (
      <svg className="st-nav-tab-icon" viewBox="0 0 16 16" fill="none">
        <rect x="2" y="3" width="12" height="10" rx="1.5" stroke="currentColor" strokeWidth="1.2"/>
        <path d="M5 7h6M5 10h4" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
      </svg>
    ),
  },
];

export default function SettingsPage() {
  const [tab,       setTab]       = useState<Tab>("locations");
  const [locations, setLocations] = useState<Location[]>([]);
  const [org,       setOrg]       = useState<Organization | null>(null);
  const [globalErr, setGlobalErr] = useState<string | null>(null);

  const loadLocations = useCallback(async () => {
    try {
      const res = await api.getLocations();
      setLocations(res.locations);
    } catch (err) {
      if (err instanceof ApiError) setGlobalErr(err.message);
    }
  }, []);

  useEffect(() => {
    api.getOrganization().then(setOrg).catch(() => {});
    loadLocations();
  }, [loadLocations]);

  return (
    <>
      <style dangerouslySetInnerHTML={{ __html: ST_CSS }} />

      <div className="st-root">
        {/* Left nav */}
        <nav className="st-nav">
          <div className="st-nav-brand">
            <div className="st-mono" style={{ fontSize: 10, color: "var(--od-text-dim)", letterSpacing: "0.12em", textTransform: "uppercase", marginBottom: 4 }}>
              Settings
            </div>
            {org ? (
              <>
                <div className="st-heading" style={{ fontSize: 14, fontWeight: 700, color: "var(--od-text)", lineHeight: 1.2 }}>
                  {org.name}
                </div>
                <div className="st-mono" style={{ fontSize: 10, color: "var(--od-text-dim)", marginTop: 3 }}>
                  {org.plan_tier ?? "free"} plan
                </div>
              </>
            ) : (
              <div style={{ height: 32, background: "var(--od-border)", borderRadius: 3, width: "70%" }} />
            )}
          </div>

          {TAB_META.map(t => (
            <button
              key={t.key}
              className={`st-nav-tab${tab === t.key ? " st-nav-tab-active" : ""}`}
              onClick={() => setTab(t.key)}
            >
              {t.icon}
              <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13 }}>{t.label}</span>
            </button>
          ))}

          {/* Bottom links */}
          <div style={{ marginTop: "auto", padding: "24px 24px 0", borderTop: "1px solid var(--od-border)" }}>
            <a href="/dashboard" style={{ display: "block", fontFamily: "'DM Mono', monospace", fontSize: 10, color: "var(--od-text-dim)", letterSpacing: "0.08em", textDecoration: "none", marginBottom: 8 }}>
              ← Dashboard
            </a>
            <a href="/dashboard/c-suite" style={{ display: "block", fontFamily: "'DM Mono', monospace", fontSize: 10, color: "var(--od-text-dim)", letterSpacing: "0.08em", textDecoration: "none" }}>
              Revenue →
            </a>
          </div>
        </nav>

        {/* Main content */}
        <main className="st-main">
          {globalErr && (
            <div className="st-error">
              <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
                <circle cx="6.5" cy="6.5" r="5.5" stroke="currentColor" strokeWidth="1.1"/>
                <path d="M6.5 4v3M6.5 8.5v.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
              </svg>
              {globalErr}
            </div>
          )}

          {tab === "locations" && (
            <LocationsTab
              key="locations"
              locations={locations}
              org={org}
              onRefresh={loadLocations}
            />
          )}
          {tab === "notifications" && (
            <NotificationsTab
              key="notifications"
              locations={locations}
            />
          )}
          {tab === "pricing" && (
            <PricingTab key="pricing" />
          )}
        </main>
      </div>
    </>
  );
}
