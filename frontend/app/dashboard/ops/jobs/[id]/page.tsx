"use client";

import { useCallback, useEffect, useState } from "react";
import { use } from "react";
import Link from "next/link";
import { Badge, Card, Text, Title } from "@tremor/react";
import { api, ApiError } from "@/lib/api-client";
import type { OpsJobDetail } from "@/lib/types";

function contextScoreBadgeProps(
  score: number | null,
): { color: string; label: string } {
  if (score === null) return { color: "gray", label: "Unscored" };
  if (score >= 80) return { color: "green", label: `High — ${score}` };
  if (score >= 61) return { color: "blue", label: `Good — ${score}` };
  if (score >= 40) return { color: "yellow", label: `Medium — ${score}` };
  return { color: "red", label: `Low — ${score}` };
}

function confidenceBadgeProps(confidence: number): {
  color: string;
  label: string;
} {
  if (confidence >= 0.9) return { color: "green", label: "High confidence" };
  if (confidence >= 0.7) return { color: "yellow", label: "Review" };
  return { color: "red", label: "Low confidence" };
}

function formatFieldKey(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatFieldValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number")
    return value.toLocaleString("en-US", { maximumFractionDigits: 2 });
  return String(value);
}

export default function JobDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);

  const [job, setJob] = useState<OpsJobDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [actionState, setActionState] = useState<
    "idle" | "confirming" | "rejecting" | "reprocessing" | "done"
  >("idle");
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  const loadJob = useCallback(async () => {
    setError(null);
    try {
      const res = await api.getJobDetail(id);
      setJob(res);
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    }
  }, [id]);

  useEffect(() => {
    loadJob();
  }, [loadJob]);

  async function handleConfirm() {
    setActionState("confirming");
    setActionMessage(null);
    try {
      await api.confirmTriage(id);
      setActionMessage("Extraction confirmed.");
      setActionState("done");
      await loadJob();
    } catch (e) {
      if (e instanceof ApiError) setActionMessage(`Error: ${e.message}`);
      setActionState("idle");
    }
  }

  async function handleReject() {
    setActionState("rejecting");
    setActionMessage(null);
    try {
      await api.rejectTriage(id);
      setActionMessage("Document rejected.");
      setActionState("done");
      await loadJob();
    } catch (e) {
      if (e instanceof ApiError) setActionMessage(`Error: ${e.message}`);
      setActionState("idle");
    }
  }

  async function handleReprocess() {
    setActionState("reprocessing");
    setActionMessage(null);
    try {
      await api.reprocessJob(id);
      setActionMessage("Re-processing started.");
      setActionState("done");
    } catch (e) {
      if (e instanceof ApiError) setActionMessage(`Error: ${e.message}`);
      setActionState("idle");
    }
  }

  if (error) {
    return (
      <div className="space-y-4">
        <Link
          href="/dashboard/ops"
          className="text-sm text-blue-600 hover:text-blue-800"
        >
          &larr; Back to queue
        </Link>
        <Card className="border-red-200 bg-red-50">
          <Text className="text-red-700">{error}</Text>
        </Card>
      </div>
    );
  }

  if (!job) {
    return (
      <div className="space-y-4">
        <Link
          href="/dashboard/ops"
          className="text-sm text-blue-600 hover:text-blue-800"
        >
          &larr; Back to queue
        </Link>
        <Card>
          <Text className="text-gray-400">Loading document...</Text>
        </Card>
      </div>
    );
  }

  const scoreBadge = contextScoreBadgeProps(job.context_score);
  const isBounced = job.context_routing === "low";
  const extractionEntries = job.extraction
    ? Object.entries(job.extraction)
    : [];

  return (
    <div className="space-y-4">
      <Link
        href="/dashboard/ops"
        className="text-sm text-blue-600 hover:text-blue-800"
      >
        &larr; Back to queue
      </Link>

      {actionMessage && (
        <Card
          className={
            actionMessage.startsWith("Error")
              ? "border-red-200 bg-red-50"
              : "border-green-200 bg-green-50"
          }
        >
          <Text
            className={
              actionMessage.startsWith("Error")
                ? "text-red-700"
                : "text-green-700"
            }
          >
            {actionMessage}
          </Text>
        </Card>
      )}

      {/* Split-screen layout */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* ── Left pane: Document Info ────────────────────────────────── */}
        <div className="space-y-4">
          <Card>
            <div className="space-y-3">
              {/* File name + score badge */}
              <div className="flex items-start gap-3">
                <div className="flex-1 min-w-0">
                  <Title className="truncate">{job.file_name}</Title>
                </div>
                <Badge color={scoreBadge.color as "green" | "blue" | "yellow" | "red" | "gray"}>
                  {scoreBadge.label}
                </Badge>
              </div>

              {/* AI document summary */}
              {job.document_summary && (
                <div>
                  <Text className="text-xs font-medium text-gray-500 uppercase tracking-wide">
                    AI Summary
                  </Text>
                  <Text className="mt-1 text-sm text-gray-700">
                    {job.document_summary}
                  </Text>
                </div>
              )}

              {/* Clarification question callout (bounced docs) */}
              {job.clarification_question && (
                <div className="rounded-lg border border-yellow-300 bg-yellow-50 p-3">
                  <Text className="text-xs font-medium text-yellow-800 uppercase tracking-wide">
                    Clarification Question Sent to Field
                  </Text>
                  <Text className="mt-1 text-sm text-yellow-900">
                    {job.clarification_question}
                  </Text>
                </div>
              )}

              {/* Download link */}
              {job.raw_path && (
                <a
                  href={job.raw_path}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-block text-sm text-blue-600 hover:text-blue-800"
                >
                  Download original document &darr;
                </a>
              )}
            </div>
          </Card>

          {/* Metadata card */}
          <Card>
            <Title>Metadata</Title>
            <dl className="mt-3 space-y-2">
              <div className="flex justify-between">
                <dt className="text-xs text-gray-500">Location</dt>
                <dd className="text-sm font-medium text-gray-700">
                  {job.location_name}
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-xs text-gray-500">Organization</dt>
                <dd className="text-sm font-medium text-gray-700">
                  {job.organization_name}
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-xs text-gray-500">Received</dt>
                <dd className="text-sm font-medium text-gray-700">
                  {new Date(job.created_at).toLocaleString()}
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-xs text-gray-500">Job ID</dt>
                <dd className="font-mono text-xs text-gray-500">{job.job_id}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-xs text-gray-500">Status</dt>
                <dd>
                  <Badge color="gray">{job.triage_status}</Badge>
                </dd>
              </div>
            </dl>
          </Card>
        </div>

        {/* ── Right pane: Extraction or Bounced ───────────────────────── */}
        <div className="space-y-4">
          {isBounced ? (
            /* Bounced document — no extraction yet */
            <Card className="border-yellow-200 bg-yellow-50">
              <div className="space-y-4">
                <Title>Bounced Back to Field</Title>
                <Text className="text-sm text-yellow-800">
                  This document was bounced back to the field for clarification.
                  The AI could not process it autonomously due to a low context
                  score.
                </Text>

                {job.clarification_question && (
                  <div>
                    <Text className="text-xs font-medium text-yellow-700 uppercase tracking-wide">
                      Question sent:
                    </Text>
                    <Text className="mt-1 text-sm text-yellow-900">
                      {job.clarification_question}
                    </Text>
                  </div>
                )}

                <button
                  onClick={handleReprocess}
                  disabled={actionState !== "idle"}
                  className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
                >
                  {actionState === "reprocessing"
                    ? "Starting..."
                    : "Re-process Document"}
                </button>
              </div>
            </Card>
          ) : extractionEntries.length > 0 ? (
            /* Medium-context doc with extraction */
            <Card>
              <div className="flex items-center justify-between mb-4">
                <Title>Extracted Fields</Title>
                <div className="flex gap-2">
                  <button
                    onClick={handleConfirm}
                    disabled={actionState !== "idle"}
                    className="rounded bg-green-600 px-3 py-1.5 text-sm text-white hover:bg-green-700 disabled:opacity-50"
                  >
                    {actionState === "confirming"
                      ? "Confirming..."
                      : "Confirm extraction"}
                  </button>
                  <button
                    onClick={handleReject}
                    disabled={actionState !== "idle"}
                    className="rounded border border-red-300 px-3 py-1.5 text-sm text-red-600 hover:bg-red-50 disabled:opacity-50"
                  >
                    {actionState === "rejecting" ? "Rejecting..." : "Reject"}
                  </button>
                </div>
              </div>

              <div className="space-y-2">
                {extractionEntries.map(([key, field]) => {
                  const badge = confidenceBadgeProps(field.confidence);
                  return (
                    <div
                      key={key}
                      className="flex items-center justify-between gap-2 rounded border border-gray-100 px-3 py-2"
                    >
                      <div className="flex-1 min-w-0">
                        <Text className="text-xs text-gray-500">
                          {formatFieldKey(key)}
                        </Text>
                        <Text className="text-sm font-medium text-gray-800 truncate">
                          {formatFieldValue(field.value)}
                        </Text>
                      </div>
                      <Badge
                        color={badge.color as "green" | "yellow" | "red"}
                        className="flex-shrink-0"
                      >
                        {badge.label}
                      </Badge>
                    </div>
                  );
                })}
              </div>
            </Card>
          ) : (
            /* No extraction data yet */
            <Card>
              <Text className="text-gray-400">
                No extracted fields available for this document yet.
              </Text>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
