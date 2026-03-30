"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api-client";

interface FreemiumState {
  documents_processed: number;
  max_documents: number;
}

/**
 * Renders a subtle top banner showing document quota usage for freemium orgs.
 * Hidden if max_documents is 0 or null (unlimited plan).
 */
export function FreemiumBanner() {
  const [usage, setUsage] = useState<FreemiumState | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function fetchUsage() {
      try {
        const org = await api.getOrganization();
        if (!cancelled) {
          setUsage({
            documents_processed: org.documents_processed,
            max_documents: org.max_documents,
          });
        }
      } catch {
        // Silently ignore — banner is non-critical
      }
    }

    fetchUsage();

    return () => {
      cancelled = true;
    };
  }, []);

  // Hide if no data or unlimited plan
  if (!usage || !usage.max_documents) return null;

  const { documents_processed, max_documents } = usage;
  const pct = Math.min((documents_processed / max_documents) * 100, 100);
  const isAtLimit = documents_processed >= max_documents;
  const isWarning = pct >= 80;

  const barColor = isAtLimit ? "bg-red-500" : isWarning ? "bg-amber-500" : "bg-amber-400";
  const textColor = isAtLimit ? "text-red-700" : isWarning ? "text-amber-700" : "text-amber-600";
  const bgColor = isAtLimit ? "bg-red-50 border-red-200" : "bg-amber-50 border-amber-200";

  return (
    <div className={`border-b px-4 py-2 ${bgColor}`}>
      <div className="mx-auto flex max-w-7xl items-center gap-4">
        {/* Progress bar */}
        <div className="flex-1">
          <div className="mb-1 flex items-center justify-between">
            <span className={`text-xs font-medium ${textColor}`}>
              {documents_processed.toLocaleString()} / {max_documents.toLocaleString()} documents used
            </span>
            {isAtLimit && (
              <Link
                href="/settings"
                className="ml-2 rounded-md bg-red-600 px-2.5 py-0.5 text-xs font-semibold text-white hover:bg-red-700"
              >
                Upgrade to continue
              </Link>
            )}
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-gray-200">
            <div
              className={`h-full rounded-full transition-all ${barColor}`}
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
