"use client";

import { createContext, useContext, useEffect } from "react";
import { setAuthContext } from "@/lib/api-client";

export interface SessionUser {
  id: string;
  email: string;
  firstName: string | null;
  lastName: string | null;
  workosOrgId: string | null;
  orgName: string | null;
}

const SessionContext = createContext<SessionUser | null>(null);

export function useSession(): SessionUser | null {
  return useContext(SessionContext);
}

export function SessionProvider({
  user,
  children,
}: {
  user: SessionUser | null;
  children: React.ReactNode;
}) {
  useEffect(() => {
    if (user) {
      // Always set auth context — backend accepts x-workos-user-id as fallback
      // when the user doesn't yet have a WorkOS org (common for direct signups).
      setAuthContext(user.workosOrgId, user.orgName ?? "", user.id);
    }
  }, [user]);

  return (
    <SessionContext.Provider value={user}>{children}</SessionContext.Provider>
  );
}
