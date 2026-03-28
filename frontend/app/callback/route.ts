/**
 * OmniDrop AI — WorkOS Auth Callback Route
 *
 * WorkOS redirects here after successful authentication.
 * handleAuth() exchanges the authorization code for a session.
 *
 * Docs: https://workos.com/docs/user-management/nextjs
 *
 * TODO: Uncomment once @workos-inc/authkit-nextjs is installed.
 */

// import { handleAuth } from "@workos-inc/authkit-nextjs";
// export const GET = handleAuth();

import { NextResponse } from "next/server";

// STUB: Replace with handleAuth() from @workos-inc/authkit-nextjs
export function GET() {
  return NextResponse.json(
    { error: "WorkOS auth callback not yet implemented" },
    { status: 501 }
  );
}
