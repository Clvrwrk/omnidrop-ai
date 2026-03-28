import { authkitMiddleware } from "@workos-inc/authkit-nextjs";

export default authkitMiddleware();

export const config = {
  /*
   * Match all routes EXCEPT:
   * - /callback (WorkOS auth callback)
   * - /api/v1/webhooks/* (authenticated by Hookdeck HMAC signature)
   * - /_next/* (Next.js internals)
   * - /favicon.ico, /robots.txt
   */
  matcher: [
    "/((?!callback|api/v1/webhooks|_next/static|_next/image|favicon.ico|robots.txt).*)",
  ],
};
