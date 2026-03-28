import { redirect } from "next/navigation";
import { withAuth } from "@workos-inc/authkit-nextjs";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

/**
 * Root page — determines where to send the user after login.
 *
 * New user  (no locations)  → /onboarding (5-step setup wizard)
 * Returning user (has locations) → /dashboard
 */
export default async function RootPage() {
  const { organizationId } = await withAuth();

  if (!organizationId) {
    redirect("/onboarding");
  }

  try {
    const res = await fetch(`${API_BASE}/api/v1/settings/locations`, {
      headers: { "x-workos-org-id": organizationId },
      cache: "no-store",
    });
    if (res.ok) {
      const data = await res.json();
      if (Array.isArray(data.locations) && data.locations.length > 0) {
        redirect("/dashboard");
      }
    }
  } catch {
    // API unreachable — fall through to onboarding
  }

  redirect("/onboarding");
}
