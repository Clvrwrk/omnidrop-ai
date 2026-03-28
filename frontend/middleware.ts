/**
 * OmniDrop AI — Next.js Middleware (WorkOS AuthKit)
 *
 * Protects all routes except public ones using WorkOS AuthKit.
 * The middleware runs on every matched request before page rendering.
 *
 * Docs: https://workos.com/docs/user-management/nextjs
 *
 * TODO: Run `npm install @workos-inc/authkit-nextjs` then uncomment below.
 * Current state: stub only — authkitMiddleware not yet wired up.
 */

// import { authkitMiddleware } from "@workos-inc/authkit-nextjs";
// export default authkitMiddleware();

import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// STUB: Passthrough middleware — replace with authkitMiddleware() for Phase 2
export function middleware(_request: NextRequest) {
  return NextResponse.next();
}

export const config = {
  /*
   * Match all routes EXCEPT:
   * - /callback (WorkOS auth callback)
   * - /api/v1/webhooks/* (webhook endpoints — authenticated by Hookdeck signature)
   * - /_next/* (Next.js internals)
   * - /favicon.ico, /robots.txt
   */
  matcher: [
    "/((?!callback|api/v1/webhooks|_next/static|_next/image|favicon.ico|robots.txt).*)",
  ],
};
