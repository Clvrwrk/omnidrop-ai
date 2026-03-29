"use client";

import { useEffect, useRef, useState } from "react";
import { Badge, Card, Text, Title } from "@tremor/react";
import { api, ApiError } from "@/lib/api-client";
import type { Organization, UploadResponse } from "@/lib/types";

// ─── Types ────────────────────────────────────────────────────────────────────

type OnboardingStep = 1 | 2 | 3 | 4 | 5;
type PricingMode = "contract" | "baseline" | null;

const US_TIMEZONES = [
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "America/Phoenix",
  "America/Anchorage",
  "Pacific/Honolulu",
];

// ─── Step Indicator ───────────────────────────────────────────────────────────

function StepIndicator({ current }: { current: OnboardingStep }) {
  const steps = [1, 2, 3, 4, 5] as const;
  return (
    <div className="flex items-center justify-center gap-2 mb-8">
      {steps.map((s) => {
        const done = s < current;
        const active = s === current;
        return (
          <div key={s} className="flex items-center gap-2">
            <div
              className={`flex h-8 w-8 items-center justify-center rounded-full text-sm font-semibold transition-colors ${
                done
                  ? "bg-green-500 text-white"
                  : active
                    ? "bg-blue-600 text-white"
                    : "bg-gray-200 text-gray-500"
              }`}
            >
              {done ? (
                <svg
                  className="h-4 w-4"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth={2.5}
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M4.5 12.75l6 6 9-13.5"
                  />
                </svg>
              ) : (
                s
              )}
            </div>
            {s < 5 && (
              <div
                className={`h-0.5 w-8 transition-colors ${
                  s < current ? "bg-green-400" : "bg-gray-200"
                }`}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ─── Shared input + label styles ──────────────────────────────────────────────

const inputClass =
  "block w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none";
const labelClass = "block text-sm font-medium text-gray-700 mb-1";

// ─── Step 1 — Profile + Company Setup ────────────────────────────────────────

interface Step1Props {
  firstName: string;
  setFirstName: (v: string) => void;
  lastName: string;
  setLastName: (v: string) => void;
  email: string;
  setEmail: (v: string) => void;
  phone: string;
  setPhone: (v: string) => void;
  companyName: string;
  setCompanyName: (v: string) => void;
  timezone: string;
  setTimezone: (v: string) => void;
  onContinue: () => void;
}

function Step1({
  firstName,
  setFirstName,
  lastName,
  setLastName,
  email,
  setEmail,
  phone,
  setPhone,
  companyName,
  setCompanyName,
  timezone,
  setTimezone,
  onContinue,
}: Step1Props) {
  const [errors, setErrors] = useState<Record<string, string>>({});

  function handleContinue() {
    const next: Record<string, string> = {};
    if (!firstName.trim()) next.firstName = "First name is required.";
    if (!lastName.trim()) next.lastName = "Last name is required.";
    if (!email.trim()) next.email = "Email is required.";
    if (!phone.trim()) next.phone = "Phone number is required.";
    if (!companyName.trim()) next.companyName = "Company name is required.";
    if (Object.keys(next).length) {
      setErrors(next);
      return;
    }
    setErrors({});
    onContinue();
  }

  return (
    <div className="space-y-5">
      <div>
        <Title>Your profile &amp; company</Title>
        <Text className="mt-1 text-gray-500">
          Tell us about yourself and your organization.
        </Text>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label htmlFor="first-name" className={labelClass}>
            First name <span className="text-red-500">*</span>
          </label>
          <input
            id="first-name"
            type="text"
            value={firstName}
            onChange={(e) => setFirstName(e.target.value)}
            placeholder="Jane"
            className={inputClass}
          />
          {errors.firstName && (
            <Text className="mt-1 text-xs text-red-600">{errors.firstName}</Text>
          )}
        </div>
        <div>
          <label htmlFor="last-name" className={labelClass}>
            Last name <span className="text-red-500">*</span>
          </label>
          <input
            id="last-name"
            type="text"
            value={lastName}
            onChange={(e) => setLastName(e.target.value)}
            placeholder="Smith"
            className={inputClass}
          />
          {errors.lastName && (
            <Text className="mt-1 text-xs text-red-600">{errors.lastName}</Text>
          )}
        </div>
      </div>

      <div>
        <label htmlFor="email" className={labelClass}>
          Email <span className="text-red-500">*</span>
        </label>
        <input
          id="email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="jane@apexroofing.com"
          className={inputClass}
        />
        {errors.email && (
          <Text className="mt-1 text-xs text-red-600">{errors.email}</Text>
        )}
      </div>

      <div>
        <label htmlFor="phone" className={labelClass}>
          Phone <span className="text-red-500">*</span>
        </label>
        <input
          id="phone"
          type="tel"
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          placeholder="(555) 000-0000"
          className={inputClass}
        />
        {errors.phone && (
          <Text className="mt-1 text-xs text-red-600">{errors.phone}</Text>
        )}
      </div>

      <div>
        <label htmlFor="company-name" className={labelClass}>
          Company name <span className="text-red-500">*</span>
        </label>
        <input
          id="company-name"
          type="text"
          value={companyName}
          onChange={(e) => setCompanyName(e.target.value)}
          placeholder="e.g. Apex Roofing Group"
          className={inputClass}
        />
        {errors.companyName && (
          <Text className="mt-1 text-xs text-red-600">{errors.companyName}</Text>
        )}
      </div>

      <div>
        <label htmlFor="timezone" className={labelClass}>
          Timezone
        </label>
        <select
          id="timezone"
          value={timezone}
          onChange={(e) => setTimezone(e.target.value)}
          className={inputClass}
        >
          {US_TIMEZONES.map((tz) => (
            <option key={tz} value={tz}>
              {tz.replace("America/", "").replace("Pacific/", "Pacific / ")}
            </option>
          ))}
        </select>
      </div>

      <button
        onClick={handleContinue}
        className="w-full rounded bg-blue-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-blue-700"
      >
        Continue
      </button>
    </div>
  );
}

// ─── Step 2 — Connect First Location ─────────────────────────────────────────

interface Step2Props {
  org: Organization | null;
  onSuccess: (locationId: string) => void;
  onSkip: () => void;
  onBack: () => void;
}

function Step2({ org, onSuccess, onSkip, onBack }: Step2Props) {
  const [locName, setLocName] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [slackWebhook, setSlackWebhook] = useState("");
  const [slackChannel, setSlackChannel] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleConnect() {
    if (!locName.trim()) {
      setError("Location name is required to save an AccuLynx integration.");
      return;
    }
    if (!org) {
      setError("Organization not loaded. Please refresh and try again.");
      return;
    }
    setError(null);
    setLoading(true);
    try {
      const res = await api.createLocation({
        name: locName.trim(),
        acculynx_api_key: apiKey.trim(),
        organization_id: org.organization_id,
        notification_channels:
          slackWebhook.trim()
            ? {
                slack: {
                  webhook_url: slackWebhook.trim(),
                  channel: slackChannel.trim() || null,
                },
              }
            : undefined,
      });
      onSuccess(res.location_id);
    } catch (e) {
      setError(
        e instanceof ApiError
          ? e.message
          : "Failed to connect location. Check your API key and try again.",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <button
          onClick={onBack}
          className="mb-4 text-sm text-gray-500 hover:text-gray-700"
        >
          ← Back
        </button>
        <Title>Connect AccuLynx <span className="text-gray-400 text-base font-normal">(optional)</span></Title>
        <Text className="mt-1 text-gray-500">
          If you use AccuLynx, add your first location now. You can skip this
          and connect later in Settings.
        </Text>
      </div>

      {error && (
        <Card className="border-red-200 bg-red-50">
          <Text className="text-sm text-red-700">{error}</Text>
        </Card>
      )}

      <div>
        <label htmlFor="loc-name" className={labelClass}>
          Location name <span className="text-red-500">*</span>
        </label>
        <input
          id="loc-name"
          type="text"
          value={locName}
          onChange={(e) => setLocName(e.target.value)}
          placeholder="e.g. Texas Branch"
          className={inputClass}
        />
      </div>

      <div>
        <label htmlFor="acculynx-key" className={labelClass}>
          AccuLynx API key
        </label>
        <div className="relative">
          <input
            id="acculynx-key"
            type={showKey ? "text" : "password"}
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="Paste your AccuLynx API key"
            className={`${inputClass} pr-16`}
          />
          <button
            type="button"
            onClick={() => setShowKey((v) => !v)}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-blue-600 hover:text-blue-800"
          >
            {showKey ? "Hide" : "Show"}
          </button>
        </div>
      </div>

      <div className="border-t pt-4 space-y-4">
        <Text className="text-sm font-medium text-gray-600">
          Slack notifications{" "}
          <span className="text-gray-400 font-normal">(optional)</span>
        </Text>

        <div>
          <label htmlFor="slack-webhook" className={labelClass}>
            Slack webhook URL
          </label>
          <input
            id="slack-webhook"
            type="text"
            value={slackWebhook}
            onChange={(e) => setSlackWebhook(e.target.value)}
            placeholder="https://hooks.slack.com/services/..."
            className={inputClass}
          />
        </div>

        <div>
          <label htmlFor="slack-channel" className={labelClass}>
            Slack channel
          </label>
          <input
            id="slack-channel"
            type="text"
            value={slackChannel}
            onChange={(e) => setSlackChannel(e.target.value)}
            placeholder="#field-ops"
            className={inputClass}
          />
        </div>
      </div>

      <button
        onClick={handleConnect}
        disabled={loading}
        className="w-full rounded bg-blue-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
      >
        {loading ? "Connecting..." : "Connect Location"}
      </button>

      <div className="text-center">
        <button
          type="button"
          onClick={onSkip}
          className="text-sm text-gray-500 hover:text-gray-700"
        >
          Skip — I don&apos;t use AccuLynx →
        </button>
      </div>
    </div>
  );
}

// ─── Step 3 — Unlock Revenue Detection ───────────────────────────────────────

interface Step3Props {
  onSuccess: (mode: "contract") => void;
  onSkip: () => void;
  onBack: () => void;
}

function Step3({ onSuccess, onSkip, onBack }: Step3Props) {
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function handleFileSelect(selected: File) {
    const allowed = [".pdf", ".xlsx", ".xls", ".csv"];
    const ext = "." + selected.name.split(".").pop()?.toLowerCase();
    if (!allowed.includes(ext)) {
      setError("Please upload a PDF, Excel, or CSV file.");
      return;
    }
    setError(null);
    setFile(selected);
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped) handleFileSelect(dropped);
  }

  async function handleUpload() {
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      await api.uploadPricingContract(file);
      onSuccess("contract");
    } catch (e) {
      setError(
        e instanceof ApiError
          ? e.message
          : "Upload failed. Please try again.",
      );
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <button
          onClick={onBack}
          className="mb-4 text-sm text-gray-500 hover:text-gray-700"
        >
          ← Back
        </button>
        <Title>Unlock Revenue Detection</Title>
        <Text className="mt-1 text-gray-500">
          Upload your national pricing agreement
        </Text>
      </div>

      <Card className="border-amber-200 bg-amber-50">
        <Text className="text-sm text-amber-800">
          Customers who complete this step find an average of{" "}
          <strong>$8,400 in overcharges</strong> within their first 50 invoices.
        </Text>
      </Card>

      {error && (
        <Card className="border-red-200 bg-red-50">
          <Text className="text-sm text-red-700">{error}</Text>
        </Card>
      )}

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={`flex flex-col items-center justify-center rounded-lg border-2 border-dashed p-10 text-center cursor-pointer transition-colors ${
          dragOver
            ? "border-blue-400 bg-blue-50"
            : "border-gray-300 hover:border-blue-400"
        }`}
      >
        <svg
          className="mb-3 h-10 w-10 text-gray-400"
          fill="none"
          stroke="currentColor"
          strokeWidth={1.5}
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5"
          />
        </svg>
        {file ? (
          <Text className="text-sm text-blue-700 font-medium">{file.name}</Text>
        ) : (
          <>
            <Text className="text-sm text-gray-600">
              Drop your pricing contract or supplier price list here
            </Text>
            <Text className="mt-1 text-xs text-gray-400">
              PDF, Excel, or CSV
            </Text>
          </>
        )}
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.xlsx,.xls,.csv"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) handleFileSelect(f);
          }}
        />
      </div>

      <button
        onClick={handleUpload}
        disabled={!file || uploading}
        className="w-full rounded bg-blue-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
      >
        {uploading ? "Uploading..." : "Upload & Continue"}
      </button>

      <div className="text-center">
        <button
          onClick={onSkip}
          className="text-sm text-gray-500 hover:text-gray-700"
        >
          Skip — use my invoice history as the baseline instead →
        </button>
        <Text className="mt-1 text-xs text-gray-400">
          We&apos;ll calculate your baseline pricing from your first 30 days of
          invoices.
        </Text>
      </div>
    </div>
  );
}

// ─── Step 4 — Process First Batch ─────────────────────────────────────────────

interface UploadedFile {
  name: string;
  status: "queued" | "processing" | "failed";
  jobId?: string;
}

interface Step4Props {
  org: Organization | null;
  locationId: string | null;
  onContinue: () => void;
  onBack: () => void;
}

function Step4({ org, locationId, onContinue, onBack }: Step4Props) {
  const [files, setFiles] = useState<UploadedFile[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function uploadFile(f: File) {
    if (!org) {
      setError("Organization not loaded. Please refresh.");
      return;
    }
    const entry: UploadedFile = { name: f.name, status: "queued" };
    setFiles((prev) => [...prev, entry]);

    try {
      const res: UploadResponse = await api.uploadDocument(
        f,
        org.organization_id,
        locationId ?? undefined,
      );
      setFiles((prev) =>
        prev.map((item) =>
          item.name === f.name && item.status === "queued"
            ? { ...item, status: "queued", jobId: res.job_id }
            : item,
        ),
      );
    } catch (e) {
      setFiles((prev) =>
        prev.map((item) =>
          item.name === f.name && item.status === "queued"
            ? { ...item, status: "failed" }
            : item,
        ),
      );
      if (e instanceof ApiError) setError(e.message);
    }
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    const dropped = Array.from(e.dataTransfer.files);
    dropped.forEach(uploadFile);
  }

  function handleFileInput(e: React.ChangeEvent<HTMLInputElement>) {
    const selected = Array.from(e.target.files ?? []);
    selected.forEach(uploadFile);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  const uploadedCount = files.filter((f) => f.status !== "failed").length;

  const statusBadgeColor: Record<UploadedFile["status"], string> = {
    queued: "gray",
    processing: "yellow",
    failed: "red",
  };

  return (
    <div className="space-y-5">
      <div>
        <button
          onClick={onBack}
          className="mb-4 text-sm text-gray-500 hover:text-gray-700"
        >
          ← Back
        </button>
        <Title>Upload your first documents</Title>
        <Text className="mt-1 text-gray-500">
          Start with invoices for the best results.
        </Text>
      </div>

      {error && (
        <Card className="border-red-200 bg-red-50">
          <Text className="text-sm text-red-700">{error}</Text>
        </Card>
      )}

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={`flex flex-col items-center justify-center rounded-lg border-2 border-dashed p-10 text-center cursor-pointer transition-colors ${
          dragOver
            ? "border-blue-400 bg-blue-50"
            : "border-gray-300 hover:border-blue-400"
        }`}
      >
        <svg
          className="mb-3 h-10 w-10 text-gray-400"
          fill="none"
          stroke="currentColor"
          strokeWidth={1.5}
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5"
          />
        </svg>
        <Text className="text-sm text-gray-600">
          Drop files here or click to browse
        </Text>
        <Text className="mt-1 text-xs text-gray-400">
          PDF, PNG, JPG, Excel, CSV
        </Text>
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.png,.jpg,.jpeg,.xlsx,.xls,.csv"
          multiple
          className="hidden"
          onChange={handleFileInput}
        />
      </div>

      {files.length > 0 && (
        <div className="space-y-2">
          <Text className="text-sm font-medium text-gray-700">
            Files uploaded: {uploadedCount}
          </Text>
          <div className="max-h-40 overflow-y-auto space-y-1.5">
            {files.map((f, i) => (
              <div
                key={`${f.name}-${i}`}
                className="flex items-center justify-between rounded border border-gray-100 bg-gray-50 px-3 py-1.5 text-sm"
              >
                <Text className="truncate text-gray-700 text-xs">
                  {f.name}
                </Text>
                <Badge
                  color={
                    (statusBadgeColor[f.status] as
                      | "gray"
                      | "yellow"
                      | "red") ?? "gray"
                  }
                >
                  {f.status}
                </Badge>
              </div>
            ))}
          </div>
        </div>
      )}

      <button
        onClick={() => onContinue()}
        disabled={uploadedCount < 1}
        className="w-full rounded bg-blue-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
      >
        Continue to Results →
      </button>

      {locationId && (
        <div className="text-center">
          {/* TODO: wire AccuLynx sync — link to /settings for now */}
          <a
            href="/settings"
            className="text-sm text-gray-500 hover:text-gray-700"
          >
            Or sync from AccuLynx instead →
          </a>
        </div>
      )}
    </div>
  );
}

// ─── Step 5 — First Findings ──────────────────────────────────────────────────

interface Step5Props {
  pricingMode: PricingMode;
  onBack: () => void;
}

function Step5({ pricingMode, onBack }: Step5Props) {
  const [showResults, setShowResults] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setShowResults(true), 3000);
    return () => clearTimeout(timer);
  }, []);

  return (
    <div className="space-y-5">
      <div>
        <button
          onClick={onBack}
          className="mb-4 text-sm text-gray-500 hover:text-gray-700"
        >
          ← Back
        </button>
        <Title>Looking for revenue leakage...</Title>
      </div>

      {!showResults ? (
        <Card>
          <div className="flex flex-col items-center justify-center py-8 space-y-4">
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-200 border-t-blue-600" />
            <Text className="text-sm text-gray-500">
              Analyzing your documents...
            </Text>
          </div>
        </Card>
      ) : pricingMode === "contract" ? (
        <Card className="border-green-200 bg-green-50">
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <div className="flex h-6 w-6 items-center justify-center rounded-full bg-green-500">
                <svg
                  className="h-4 w-4 text-white"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth={2.5}
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M4.5 12.75l6 6 9-13.5"
                  />
                </svg>
              </div>
              <Text className="font-semibold text-green-800">
                Your first batch is processing.
              </Text>
            </div>
            <Text className="text-sm text-green-700">
              Check back in a few minutes to see your findings. The AI will
              compare every invoice against your uploaded pricing contract.
            </Text>
            <a
              href="/dashboard/c-suite"
              className="mt-2 inline-block rounded bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700"
            >
              Go to Revenue Dashboard →
            </a>
          </div>
        </Card>
      ) : (
        <Card className="border-blue-200 bg-blue-50">
          <div className="space-y-3">
            <Text className="font-semibold text-blue-800">
              Your documents are processing.
            </Text>
            <Text className="text-sm text-blue-700">
              We&apos;ll start building your pricing baseline — you&apos;ll see
              comparisons after your first 30 days of invoices.
            </Text>
            <a
              href="/dashboard/c-suite"
              className="mt-2 inline-block rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
            >
              Go to Revenue Dashboard →
            </a>
          </div>
        </Card>
      )}

      <Text className="text-center text-xs text-gray-400">
        Processing happens in the background. You&apos;ll see results as
        documents complete.
      </Text>
    </div>
  );
}

// ─── Main Onboarding Page ─────────────────────────────────────────────────────

export default function OnboardingPage() {
  const [step, setStep] = useState<OnboardingStep>(1);
  const [pricingMode, setPricingMode] = useState<PricingMode>(null);
  // Step 1 — profile + company
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [timezone, setTimezone] = useState("America/Chicago");
  // Step 2 — location
  const [locationId, setLocationId] = useState<string | null>(null);
  const [org, setOrg] = useState<Organization | null>(null);

  useEffect(() => {
    api.getOrganization().then(setOrg).catch(() => {});
  }, []);

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-lg">
        <div className="mb-6 text-center">
          <Text className="text-2xl font-bold text-gray-900">OmniDrop AI</Text>
          <Text className="mt-1 text-sm text-gray-500">
            Let&apos;s get you set up in 5 steps
          </Text>
          <a
            href="/dashboard"
            className="mt-3 inline-block text-xs text-gray-400 hover:text-gray-600 underline underline-offset-2"
          >
            Already set up? Go to dashboard →
          </a>
        </div>

        <StepIndicator current={step} />

        <Card>
          {step === 1 && (
            <Step1
              firstName={firstName}
              setFirstName={setFirstName}
              lastName={lastName}
              setLastName={setLastName}
              email={email}
              setEmail={setEmail}
              phone={phone}
              setPhone={setPhone}
              companyName={companyName}
              setCompanyName={setCompanyName}
              timezone={timezone}
              setTimezone={setTimezone}
              onContinue={() => setStep(2)}
            />
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
              onSuccess={(mode) => {
                setPricingMode(mode);
                setStep(4);
              }}
              onSkip={() => {
                setPricingMode("baseline");
                setStep(4);
              }}
              onBack={() => setStep(2)}
            />
          )}
          {step === 4 && (
            <Step4
              org={org}
              locationId={locationId}
              onContinue={() => {
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
        </Card>
      </div>
    </div>
  );
}
