---
name: omnidrop-frontend
description: Patterns, rules, and component conventions for building OmniDrop AI frontend features. Use when building any Next.js page, React component, API client call, WorkOS auth integration, Tremor chart, Shadcn UI element, or frontend route for the OmniDrop AI SaaS application.
---

# OmniDrop AI — Frontend Engineering Skill

## Stack (Non-Negotiable)

| Concern | Library | Notes |
|---|---|---|
| Framework | Next.js 15 App Router | TypeScript strict mode |
| Charts & metrics | `@tremor/react@^3` | ONLY option — never Chart.js, Recharts, Victory |
| UI primitives | Shadcn/UI | buttons, inputs, dialogs, tables, badges |
| Styling | Tailwind CSS v3 | no v4 — package is `@tremor/react@^3` which requires v3 |
| Auth | WorkOS AuthKit (`@workos-inc/authkit-nextjs`) | SSO, Magic Links, SAML |
| Error tracking | `@sentry/nextjs@^8` | init via `npx @sentry/wizard -i nextjs` |
| API calls | `lib/api-client.ts` typed wrapper | all FastAPI calls go through here |

---

## WorkOS Auth Patterns

### middleware.ts (runs on every request)
```typescript
import { authkitMiddleware } from '@workos-inc/authkit-nextjs';
export default authkitMiddleware();
export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'],
};
```

### Public routes (no auth required — add to WorkOS config)
- `/api/v1/webhooks/*` — authenticated by Hookdeck HMAC instead
- `/callback` — WorkOS OAuth callback

### Server component (protected page)
```typescript
import { withAuth } from '@workos-inc/authkit-nextjs';
export default withAuth(async function Page() { ... });
```

### Client component (protected)
```typescript
import { useAuth } from '@workos-inc/authkit-nextjs/client';
const { user } = useAuth();
```

### Callback route (`app/callback/route.ts`)
```typescript
import { handleAuth } from '@workos-inc/authkit-nextjs';
export const GET = handleAuth();
```

---

## API Client Pattern (`lib/api-client.ts`)

All calls to FastAPI go through this typed wrapper. Never use raw `fetch` directly in components.

```typescript
const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL;

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) throw new Error(`API error ${res.status}: ${path}`);
  return res.json() as Promise<T>;
}

export const api = {
  getJobs: () => apiFetch<Job[]>('/api/v1/jobs'),
  getInvoice: (id: string) => apiFetch<Invoice>(`/api/v1/invoices/${id}`),
  searchDocuments: (query: string) =>
    apiFetch<SearchResult[]>('/api/v1/search', {
      method: 'POST',
      body: JSON.stringify({ query }),
    }),
  addLocation: (data: LocationInput) =>
    apiFetch<Location>('/api/v1/settings/locations', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
};
```

---

## Tremor Component Patterns

### Dashboard KPI cards
```tsx
import { Metric, Text, Card } from '@tremor/react';
<Card>
  <Text>Documents Processed</Text>
  <Metric>1,284</Metric>
</Card>
```

### Time-series chart (intake volume)
```tsx
import { AreaChart } from '@tremor/react';
<AreaChart
  data={chartData}
  index="date"
  categories={['Invoices', 'Manuals']}
  colors={['blue', 'green']}
  yAxisWidth={40}
/>
```

### Ranked list (vendor spend)
```tsx
import { BarList } from '@tremor/react';
<BarList
  data={vendors.map(v => ({ name: v.name, value: v.total }))}
  color="blue"
/>
```

### Task status feed
```tsx
import { Badge, Table, TableRow, TableCell } from '@tremor/react';
// Use Badge color: "green" (completed), "yellow" (in_progress), "red" (failed)
```

---

## Route → Feature Mapping

| Route | Feature | Key components |
|---|---|---|
| `/dashboard` | Celery task feed + intake volume | AreaChart, BarChart, Badge (task status) |
| `/analytics` | C-Suite KPIs + vendor spend | Metric, BarList, CMD+K query bar |
| `/search` | RAG semantic search | Search input → POST /api/v1/search → ranked results |
| `/triage` | HITL split-screen review | PDF viewer (left) + extracted fields + confidence scores (right) |
| `/settings` | AccuLynx location key management | Form (location name + API key) + connection status per location |
| `/callback` | WorkOS OAuth handler | `handleAuth()` only — no UI |

---

## HITL Triage Layout (`/triage`)

Split-screen pattern for accountants to review AI extractions:

```tsx
<div className="grid grid-cols-2 h-screen gap-4 p-4">
  {/* Left: PDF viewer */}
  <div className="overflow-auto border rounded-lg">
    <iframe src={documentUrl} className="w-full h-full" />
  </div>
  {/* Right: Extracted fields */}
  <div className="overflow-auto space-y-4">
    {fields.map(field => (
      <Card key={field.key} className={field.confidence < 0.8 ? 'border-yellow-400' : ''}>
        <Text>{field.label}</Text>
        <div className="flex items-center gap-2">
          <input defaultValue={field.value} className="flex-1" />
          <Badge color={field.confidence > 0.9 ? 'green' : 'yellow'}>
            {Math.round(field.confidence * 100)}%
          </Badge>
        </div>
      </Card>
    ))}
  </div>
</div>
```

---

## Settings Page — AccuLynx Location Keys

Each roofing location has its own AccuLynx API key. Users register locations here.

```tsx
// Form submits to POST /api/v1/settings/locations
// { location_name: string, acculynx_api_key: string }
// Response includes connection_status: "connected" | "invalid_key" | "pending"
```

---

## Environment Variables (Frontend)

| Variable | Use | Rule |
|---|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase client | Browser-safe |
| `NEXT_PUBLIC_SUPABASE_KEY` | Supabase anon key | Browser-safe — NEVER service role key |
| `NEXT_PUBLIC_API_BASE_URL` | FastAPI URL | Browser-safe |
| `NEXT_PUBLIC_SENTRY_DSN` | Sentry browser | Browser-safe |
| `NEXT_PUBLIC_WORKOS_REDIRECT_URI` | WorkOS callback | Browser-safe |
| `WORKOS_API_KEY` | WorkOS server | SERVER ONLY — never `NEXT_PUBLIC_` prefix |
| `WORKOS_CLIENT_ID` | WorkOS OAuth | Used in both server + client config |
| `WORKOS_COOKIE_PASSWORD` | Session encryption | SERVER ONLY — 32+ chars |

**CRITICAL: `SUPABASE_SERVICE_ROLE_KEY` never appears in any frontend file.**

---

## Anti-Patterns

- Never `import { BarChart } from 'recharts'` — use Tremor
- Never raw `fetch()` in a component — use `lib/api-client.ts`
- Never `process.env.SUPABASE_SERVICE_ROLE_KEY` in any `/frontend/` file
- Never `client:load` equivalent patterns that block first paint
- Never hardcode `http://localhost:8000` — always `process.env.NEXT_PUBLIC_API_BASE_URL`
