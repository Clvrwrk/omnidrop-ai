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
    if (user?.workosOrgId) {
      setAuthContext(user.workosOrgId, user.orgName ?? "");
    }
  }, [user]);

  return (
    <SessionContext.Provider value={user}>{children}</SessionContext.Provider>
  );
}
