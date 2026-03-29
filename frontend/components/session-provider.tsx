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
  // Set auth context synchronously during render so module-level headers are
  // populated before any child useEffect hooks fire (children's effects run
  // before parents', so useEffect alone is too late for the first fetch).
  if (user) {
    setAuthContext(user.workosOrgId, user.orgName ?? "", user.id);
  }

  useEffect(() => {
    if (user) {
      setAuthContext(user.workosOrgId, user.orgName ?? "", user.id);
    }
  }, [user]);

  return (
    <SessionContext.Provider value={user}>{children}</SessionContext.Provider>
  );
}
