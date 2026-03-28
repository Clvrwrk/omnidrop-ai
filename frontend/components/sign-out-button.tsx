"use client";

import { useSession } from "@/components/session-provider";

export function SignOutButton() {
  const user = useSession();
  if (!user) return null;

  return (
    <div className="flex items-center gap-3">
      <span className="text-sm text-gray-500">{user.email}</span>
      <a
        href="/api/auth/sign-out"
        className="text-sm text-gray-600 hover:text-gray-900"
      >
        Sign out
      </a>
    </div>
  );
}
