"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api-client";

/**
 * Fetches the ops (needs_clarity) queue count and renders an inline badge.
 * Rendered inside the nav — keeps the server RootLayout server-only.
 */
export function OpsQueueBadge() {
  const [count, setCount] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function fetchCount() {
      try {
        const res = await api.getOpsTriageQueue({ limit: 1 });
        if (!cancelled) setCount(res.total);
      } catch {
        // Silently ignore — badge is non-critical
      }
    }

    fetchCount();

    // Refresh every 60 s so the badge stays reasonably current
    const interval = setInterval(fetchCount, 60_000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  if (!count || count <= 0) return null;

  return (
    <span className="ml-1 inline-flex items-center justify-center rounded-full bg-yellow-400 px-1.5 py-0.5 text-xs font-semibold leading-none text-yellow-900">
      {count > 99 ? "99+" : count}
    </span>
  );
}
