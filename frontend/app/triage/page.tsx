"use client";

import { useCallback, useEffect, useState } from "react";
import { Badge, Card, Text, Title } from "@tremor/react";
import { api, ApiError } from "@/lib/api-client";
import type { TriageQueueItem, TriageDetail } from "@/lib/types";

const confidenceColor = (score: number) =>
  score >= 0.95 ? "green" : score >= 0.8 ? "yellow" : "red";

const fieldLabels: Record<string, string> = {
  vendor_name: "Vendor Name",
  invoice_number: "Invoice Number",
  invoice_date: "Invoice Date",
  due_date: "Due Date",
  subtotal: "Subtotal",
  tax: "Tax",
  total: "Total",
  notes: "Notes",
};

export default function TriagePage() {
  const [queue, setQueue] = useState<TriageQueueItem[]>([]);
  const [selected, setSelected] = useState<TriageDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadQueue = useCallback(async () => {
    try {
      const res = await api.getTriageQueue({ limit: 50 });
      setQueue(res.items);
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadQueue();
  }, [loadQueue]);

  async function selectItem(documentId: string) {
    setError(null);
    try {
      const detail = await api.getTriageDetail(documentId);
      setSelected(detail);
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    }
  }

  async function handleAction(action: "confirm" | "reject") {
    if (!selected) return;
    setSubmitting(true);
    setError(null);
    try {
      await api.patchTriage(selected.document_id, { action });
      setSelected(null);
      await loadQueue();
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    } finally {
      setSubmitting(false);
    }
  }

  // Queue list view (no item selected)
  if (!selected) {
    return (
      <div className="space-y-6">
        <Title>Triage Review</Title>
        <Text>Documents with low-confidence AI extractions needing human review</Text>

        {error && (
          <Card className="border-red-200 bg-red-50">
            <Text className="text-red-700">{error}</Text>
          </Card>
        )}

        {loading && <Text>Loading...</Text>}

        {!loading && queue.length === 0 && (
          <Card>
            <Text className="text-center text-gray-400">
              No documents pending triage
            </Text>
          </Card>
        )}

        <div className="space-y-3">
          {queue.map((item) => (
            <Card
              key={item.document_id}
              className="cursor-pointer hover:border-blue-300 transition-colors"
              onClick={() => selectItem(item.document_id)}
            >
              <div className="flex items-center justify-between">
                <div>
                  <Text className="font-semibold">{item.file_name}</Text>
                  <Text className="text-xs text-gray-500">
                    {item.location_name} &middot; {item.document_type}
                  </Text>
                </div>
                <div className="flex items-center gap-2">
                  <Badge color="yellow">
                    {item.low_confidence_field_count} fields flagged
                  </Badge>
                  <Badge color={confidenceColor(item.min_confidence_score)}>
                    Min: {(item.min_confidence_score * 100).toFixed(0)}%
                  </Badge>
                </div>
              </div>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  // Split-screen review view
  const extraction = selected.extraction;
  const headerFields = Object.entries(fieldLabels).map(([key, label]) => ({
    key,
    label,
    ...extraction[key as keyof typeof extraction] as { value: string | number | null; confidence: number },
  }));

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={() => setSelected(null)}
            className="text-sm text-blue-600 hover:text-blue-800"
          >
            &larr; Back to queue
          </button>
          <Title>{selected.file_name}</Title>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => handleAction("reject")}
            disabled={submitting}
            className="rounded border border-red-300 px-4 py-2 text-sm text-red-700 hover:bg-red-50 disabled:opacity-50"
          >
            Reject
          </button>
          <button
            onClick={() => handleAction("confirm")}
            disabled={submitting}
            className="rounded bg-green-600 px-4 py-2 text-sm text-white hover:bg-green-700 disabled:opacity-50"
          >
            Confirm
          </button>
        </div>
      </div>

      {error && (
        <Card className="border-red-200 bg-red-50">
          <Text className="text-red-700">{error}</Text>
        </Card>
      )}

      {/* Split-screen layout */}
      <div className="grid grid-cols-2 gap-4" style={{ height: "calc(100vh - 200px)" }}>
        {/* Left: PDF viewer */}
        <div className="overflow-hidden rounded-lg border">
          <iframe
            src={selected.document_url}
            className="h-full w-full"
            title="Original document"
          />
        </div>

        {/* Right: Extracted fields with confidence */}
        <div className="space-y-3 overflow-auto">
          {headerFields.map((field) => (
            <Card
              key={field.key}
              className={field.confidence < 0.8 ? "border-yellow-400" : ""}
            >
              <div className="flex items-center justify-between">
                <Text className="text-xs font-medium text-gray-500">
                  {field.label}
                </Text>
                <Badge color={confidenceColor(field.confidence)}>
                  {(field.confidence * 100).toFixed(0)}%
                </Badge>
              </div>
              <Text className="mt-1 text-sm font-medium">
                {field.value != null ? String(field.value) : "—"}
              </Text>
            </Card>
          ))}

          {/* Line Items */}
          {extraction.line_items.length > 0 && (
            <Card>
              <Text className="text-xs font-medium text-gray-500 mb-3">
                Line Items
              </Text>
              <div className="space-y-2">
                {extraction.line_items.map((item, i) => (
                  <div key={i} className="rounded border p-3 text-sm">
                    <div className="flex justify-between">
                      <span>{item.description.value ?? "—"}</span>
                      <Badge color={confidenceColor(Math.min(
                        item.description.confidence,
                        item.quantity.confidence,
                        item.unit_price.confidence,
                        item.amount.confidence,
                      ))}>
                        {(Math.min(
                          item.description.confidence,
                          item.quantity.confidence,
                          item.unit_price.confidence,
                          item.amount.confidence,
                        ) * 100).toFixed(0)}%
                      </Badge>
                    </div>
                    <div className="mt-1 flex gap-4 text-xs text-gray-500">
                      <span>Qty: {item.quantity.value ?? "—"}</span>
                      <span>Unit: ${item.unit_price.value?.toFixed(2) ?? "—"}</span>
                      <span>Amount: ${item.amount.value?.toFixed(2) ?? "—"}</span>
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
