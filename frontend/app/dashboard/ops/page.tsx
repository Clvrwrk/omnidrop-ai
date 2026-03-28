"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Badge, Card, Text, Title } from "@tremor/react";
import { api, ApiError } from "@/lib/api-client";
import type { OpsTriageQueueItem } from "@/lib/types";

function contextScoreBadge(score: number): { color: string; label: string } {
  if (score >= 61) return { color: "blue", label: "Good" };
  return { color: "yellow", label: "Medium" };
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export default function OpsQueuePage() {
  const [items, setItems] = useState<OpsTriageQueueItem[]>([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const loadQueue = useCallback(async () => {
    try {
      const res = await api.getOpsTriageQueue({ limit: 50 });
      setItems(res.items);
      setTotal(res.total);
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    }
  }, []);

  // Initial load
  useEffect(() => {
    loadQueue();
  }, [loadQueue]);

  // Auto-refresh every 30 seconds
  useEffect(() => {
    const interval = setInterval(loadQueue, 30_000);
    return () => clearInterval(interval);
  }, [loadQueue]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Title>Needs Clarity</Title>
        {total > 0 && (
          <Badge color="yellow">{total} awaiting review</Badge>
        )}
      </div>

      {error && (
        <Card className="border-red-200 bg-red-50">
          <Text className="text-red-700">{error}</Text>
        </Card>
      )}

      {/* Empty state */}
      {items.length === 0 && !error && (
        <Card>
          <div className="py-12 text-center">
            <Text className="text-lg text-gray-500">
              No documents need review right now. 🎉
            </Text>
          </div>
        </Card>
      )}

      {/* Document queue */}
      <div className="space-y-3">
        {items.map((item) => {
          const badge = contextScoreBadge(item.context_score);
          return (
            <Card key={item.job_id} className="hover:shadow-md transition-shadow">
              <div className="flex items-start justify-between gap-4">
                {/* Left: document info */}
                <div className="flex-1 min-w-0 space-y-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium text-gray-900 truncate">
                      {item.file_name}
                    </span>
                    <Badge color={badge.color as "yellow" | "blue"}>
                      {badge.label} — {item.context_score}
                    </Badge>
                  </div>
                  <div className="flex items-center gap-2 text-xs text-gray-500">
                    <span>{item.location_name}</span>
                    <span>·</span>
                    <span>{timeAgo(item.created_at)}</span>
                  </div>
                  {item.document_summary && (
                    <Text className="text-sm text-gray-600 line-clamp-2">
                      {item.document_summary}
                    </Text>
                  )}
                </div>

                {/* Right: action */}
                <div className="flex-shrink-0">
                  <Link
                    href={`/dashboard/ops/jobs/${item.job_id}`}
                    className="inline-block rounded bg-blue-600 px-4 py-1.5 text-sm text-white hover:bg-blue-700"
                  >
                    Review
                  </Link>
                </div>
              </div>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
