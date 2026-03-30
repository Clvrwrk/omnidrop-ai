"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/**
 * Global CMD+K / Ctrl+K listener that navigates to /search.
 * Renders nothing — purely a keyboard shortcut side-effect component.
 */
export function CmdK() {
  const router = useRouter();

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        router.push("/search");
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [router]);

  return null;
}
