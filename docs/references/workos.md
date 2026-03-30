# WorkOS — OmniDrop Reference

## 1. What It Does Here

WorkOS AuthKit provides authentication and organization management for OmniDrop AI.
Every request to the Next.js frontend passes through WorkOS middleware; every
protected FastAPI endpoint reads the organization identity from session headers
injected by the frontend.

Two distinct responsibilities:

**Authentication** — Login/logout, session management, and the `/callback` route
are handled entirely by WorkOS. OmniDrop never stores passwords or manages sessions.

**Organization provisioning** — When a user authenticates, their `workos_org_id` is
used to lazy-provision a corresponding row in the Supabase `organizations` table via
`GET /api/v1/organizations/me`. All multi-tenant data isolation flows from this
`organization_id`.

Files that touch WorkOS:
- `frontend/middleware.ts` — `authkitMiddleware` runs on ALL routes
- `frontend/app/callback/route.ts` — WorkOS OAuth callback handler
- `frontend/app/layout.tsx` — `AuthKitProvider` wraps the app
- `backend/api/v1/organizations.py` — lazy-provisions org on first login
- Every protected FastAPI endpoint — reads `x-workos-org-id` from session header

## 2. Credentials & Environment Variables

| Variable | Where to Find It | Used By |
|---|---|---|
| `WORKOS_API_KEY` | WorkOS Dashboard → **API Keys** | Backend only — server-side SDK calls |
| `WORKOS_CLIENT_ID` | WorkOS Dashboard → **Applications** → your app | Backend + Next.js middleware |
| `NEXT_PUBLIC_WORKOS_CLIENT_ID` | Same value as `WORKOS_CLIENT_ID` | Frontend client components only |

**Never expose `WORKOS_API_KEY` to the browser.** Only `NEXT_PUBLIC_WORKOS_CLIENT_ID`
is safe for client-side use.

Set these in:
- Local dev: `.env.local`
- Render: `omnidrop-secrets` Environment Group

## 3. Key Concepts

### AuthKit Middleware
`authkitMiddleware` runs on every request. It:
1. Verifies the session token
2. Injects session data (including `organization_id`) as request headers
3. Redirects unauthenticated users to the WorkOS-hosted login page

Public routes that bypass auth:
- `/api/v1/webhooks/*` — AccuLynx/Hookdeck ingestion (verified by HMAC, not session)
- `/callback` — WorkOS OAuth callback

All other routes are protected automatically.

### Session Headers (Frontend → Backend)
After the middleware runs, the Next.js app forwards these headers on every API call
to FastAPI via `lib/api-client.ts`:

| Header | Value | Used For |
|---|---|---|
| `x-workos-org-id` | WorkOS organization UUID | Org lookup / lazy-provision |
| `x-workos-org-name` | Human-readable org name | Display + Supabase upsert |
| `x-workos-user-id` | WorkOS user UUID | Audit trails |

**FastAPI endpoints always read `organization_id` from `x-workos-org-id` — never
from the request body.**

### Lazy Organization Provisioning
On first login (or any request where the org row doesn't exist yet), `GET /api/v1/organizations/me`
calls `get_or_create_organization(workos_org_id, workos_org_name)` in
`backend/services/supabase_client.py`. This upserts a row in `organizations` and
returns the internal `organization_id` UUID used for all subsequent queries.

### Role-Based Routing
WorkOS organization membership roles drive dashboard routing:

| WorkOS Role | Destination |
|---|---|
| `c-suite` | `/dashboard/c-suite` — Revenue Recovery |
| `ops`, `accountant` (default) | `/dashboard/ops` — HITL Queue |

Role checks happen in `frontend/middleware.ts` after authentication.

## 4. Integration Points

### Frontend
```typescript
// middleware.ts
import { authkitMiddleware } from "@workos-inc/authkit-nextjs";

export default authkitMiddleware({
  redirectUri: `${process.env.NEXT_PUBLIC_APP_URL}/callback`,
});

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
```

```typescript
// Server component — reading auth
import { withAuth } from "@workos-inc/authkit-nextjs";

export default async function ProtectedPage() {
  const { user, organizationId } = await withAuth();
  // ...
}
```

```typescript
// Client component — reading auth
"use client";
import { useAuth } from "@workos-inc/authkit-nextjs";

export function ClientComponent() {
  const { user, isLoading } = useAuth();
  // ...
}
```

### Backend (FastAPI)
Every protected endpoint reads the org from the session header and calls the
lazy-provision helper:

```python
from fastapi import Request, HTTPException
from backend.services.supabase_client import get_or_create_organization

@router.get("/some-endpoint")
async def some_endpoint(request: Request):
    workos_org_id = request.headers.get("x-workos-org-id")
    if not workos_org_id:
        raise HTTPException(status_code=401, detail="Missing x-workos-org-id header.")

    workos_org_name = request.headers.get("x-workos-org-name", "")
    org = await get_or_create_organization(workos_org_id, workos_org_name)
    organization_id = org.get("organization_id")
    if not organization_id:
        raise HTTPException(status_code=404, detail="Organization not found.")
    # ... use organization_id for all queries
```

### API Client (Frontend → FastAPI)
`lib/api-client.ts` automatically forwards WorkOS session headers on every request.
Do not call `fetch()` directly — use `api.*` methods.

## 5. Common Operations

### Check if user is authenticated (server)
```typescript
import { withAuth } from "@workos-inc/authkit-nextjs";

const { user } = await withAuth({ ensureSignedIn: true });
// ensureSignedIn: true redirects to login if not authenticated
```

### Sign out
```typescript
import { signOut } from "@workos-inc/authkit-nextjs";

await signOut();
// Redirects to WorkOS-hosted logout, then back to app
```

### Read org ID in a client component
```typescript
"use client";
import { useAuth } from "@workos-inc/authkit-nextjs";

const { organizationId } = useAuth();
```

### Add a user to an organization (admin)
Done via WorkOS Dashboard or WorkOS API — not via OmniDrop's backend.
OmniDrop never manages WorkOS membership directly.

## 6. Error Handling & Monitoring

| Scenario | Behaviour |
|---|---|
| Missing `x-workos-org-id` header | FastAPI returns `401` |
| Org not found after lazy-provision | FastAPI returns `404` |
| Expired session token | WorkOS middleware redirects to login |
| Invalid session token | WorkOS middleware redirects to login |
| WorkOS API unreachable | `500` — log via Sentry `SENTRY_PYTHON_DSN` |

Session errors are handled entirely by WorkOS middleware before they reach FastAPI.
The backend should only ever see valid, verified session headers.

Log `organization_id` (not `workos_org_id`) in all structured log entries — the
internal UUID is what traces across Supabase and Sentry.

## 7. SOPs

### SOP 1 — New environment setup

1. Create a WorkOS application in the WorkOS Dashboard for the target environment
   (`omnidrop-dev` or `omnidrop-prod`).
2. Set the redirect URI to `https://app.omnidrop.dev/callback` (or prod equivalent).
3. Copy `WORKOS_API_KEY` and `WORKOS_CLIENT_ID` to the Render `omnidrop-secrets`
   Environment Group.
4. Set `NEXT_PUBLIC_WORKOS_CLIENT_ID` in the Next.js environment (same value as
   `WORKOS_CLIENT_ID`).
5. Set `NEXT_PUBLIC_APP_URL` to the public app URL so the redirect URI resolves correctly.
6. Test: load the app, confirm redirect to WorkOS login, complete login, confirm
   `/callback` completes and user lands on `/dashboard/ops`.

### SOP 2 — Promoting a user to C-Suite role

1. Open WorkOS Dashboard → **Organizations** → select the org.
2. Find the user under **Memberships**.
3. Change their role to `c-suite`.
4. Ask the user to log out and back in — the session must be refreshed for the new
   role to take effect in middleware routing.

### SOP 3 — Debugging "Missing x-workos-org-id header" in production

This error means the WorkOS session header is not being forwarded from Next.js to
FastAPI.

1. Confirm `authkitMiddleware` is running — check `middleware.ts` matcher config.
2. Confirm `lib/api-client.ts` is forwarding `x-workos-org-id` on all requests.
3. Check that the request is not hitting a public route bypass.
4. If the user was just provisioned, confirm `GET /api/v1/organizations/me` succeeded
   (check Sentry / logs for org lazy-provision errors).
5. Ask the user to log out and back in to refresh their session token.
