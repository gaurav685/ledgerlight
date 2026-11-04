# Frontend architecture

Phase 5 §10. The real `frontend/` app this phase built -- what exists,
how it's wired together, and where the real design decisions (not
just "what") are recorded (`docs/adr/0009-frontend.md`).

## Stack

Next.js 16 App Router, React 19, TypeScript strict, ESLint, pnpm with
a committed lockfile. Every real page is a Client Component (`"use
client"`) -- there is no server-rendered data fetch anywhere in this
app; every page fetches the real `/v1` API on mount. See ADR 0009
decision 1 for why.

## Request path

```
Browser  --(same-origin fetch, cookie attached automatically)-->
  Next.js's own app/api/[...path]/route.ts (a real Route Handler,
  not next.config.ts's rewrites() -- see ADR 0009 decision 2)
    --(forwards method/headers/body, reads LEDGERLIGHT_API_ORIGIN
       fresh per request)-->
  the real FastAPI backend
```

Because the browser only ever talks to Next.js's own origin, the real
session cookie (httpOnly, `SameSite=Lax`) just works with no CORS
configuration anywhere -- the backend and the proxy are, from the
browser's point of view, the same origin.

## Identity and auth (`lib/auth.tsx`, `lib/api.ts`)

`AuthProvider` wraps the whole app (`app/layout.tsx`) and calls `GET
/v1/auth/me` once on mount to recover an existing real session (a
page refresh does not lose login state, since the cookie is already
there). `login()`/`logout()` call the real endpoints and update local
React state; `login()` also stores the real `csrf_token` the backend
returns, in `sessionStorage` (ADR 0009 decision 3) -- never in a
cookie. `lib/api.ts`'s own `apiFetch()` is the one real HTTP client
every page uses: it attaches `X-CSRF-Token` automatically on every
mutating call, throws a typed `ApiError` carrying the real backend
status/detail on failure, and exposes `skipCsrf` for the one real
call (`POST /auth/login`) that happens before any CSRF token exists
yet.

`components/RequireAuth.tsx` wraps every page that needs a real
session: it redirects to `/login` once loading finishes and no real
identity was recovered, and renders nothing while that check is still
in flight (never a flash of protected content before the redirect
fires).

## Pages (`app/`)

| Route | Real backend calls | Notes |
|---|---|---|
| `/login` | `POST /v1/auth/login` | The one page not wrapped in `RequireAuth` |
| `/companies` | `GET /v1/companies/search` | |
| `/companies/[id]` | `GET /v1/companies/{id}`, `.../scores`, `.../credibility` | Point-in-time `as_of` control; the permanent model-limitations banner (`docs/modelling/model-card.md`'s own text, read live) |
| `/companies/[id]/timeline` | `GET /v1/companies/{id}/timeline` | VERIFIED/CANDIDATE tier badges (`components/TierBadge.tsx`) |
| `/documents/[versionId]` | `GET /v1/documents/{id}/pages/{n}`, `.../signed-url` | Renders the real, immutable `raw_text` with the cited `char_start`/`char_end` span highlighted -- plain JSX text interpolation, never `dangerouslySetInnerHTML` (see `tests/test_prompt_injection_separation.py`'s own repo-wide check) |
| `/dossiers`, `/dossiers/[investigationId]` | `POST .../investigations`, `GET .../investigations`, `.../dossier`, `.../export` | Create-investigation form, status polling, 8-section dossier view, markdown/JSON export |
| `/review`, `/review/[taskId]` | `GET /v1/review/tasks`, `POST .../decision` | Queue list + decision form |
| `/watchlists` | `GET/POST/DELETE /v1/watchlists`, `.../alerts` | CRUD, alert rules, alert list |
| `/admin` | `GET/POST/PATCH/DELETE /v1/admin/users`, `/v1/api-keys`, `/v1/webhooks`, `/v1/admin/audit-log` | Users/roles, API keys, webhooks, audit log -- `tenant_admin` only (the backend's own RBAC is the real enforcement; the frontend never duplicates that check, it just gets a real 403 if it tries) |

## Components (`components/`)

- `Nav.tsx` -- the real top-level navigation, shown once `identity` is
  known.
- `Disclaimer.tsx` -- the permanent "not investment advice" notice
  (brief's own §4 requirement), rendered on every page that shows a
  score or dossier content.
- `TierBadge.tsx` -- VERIFIED/CANDIDATE visual tier, shared between
  the company timeline and dossier views.
- `RequireAuth.tsx` -- see above.

## Security headers

Set twice, deliberately (ADR 0009 decision 4): once by the real
backend (`ledgerlight.api.app`'s own middleware, for every API JSON
response) and once by `next.config.ts`'s own `headers()` (for every
real page request, which never reaches the backend at all).

## What this frontend does NOT do

- No server-side rendering or data fetching of any kind (decision 1).
- No real accessibility audit has been run against this UI yet (a
  real, open gap -- flagged in `docs/phase-5/progress.md`, carried
  from §4).
- No automated visual/interaction testing beyond the real build-smoke
  Playwright suite (`frontend/e2e/smoke.spec.ts`, §7) -- the full
  Playwright e2e suite against a live backend is a real, deferred §9
  item (`docs/release/release-gates.md`).
