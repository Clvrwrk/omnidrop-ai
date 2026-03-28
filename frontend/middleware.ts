import { authkitMiddleware } from "@workos-inc/authkit-nextjs";

export default authkitMiddleware({
  middlewareAuth: {
    enabled: true,
    // These paths are accessible without authentication
    unauthenticatedPaths: [
      "/callback",
      "/api/auth/sign-out",
      "/api/v1/webhooks(.*)",
    ],
  },
});

export const config = {
  /*
   * Match all routes EXCEPT Next.js internals and static assets.
   * Auth logic (which paths require sign-in) is handled above via unauthenticatedPaths.
   */
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|robots.txt).*)",
  ],
};
