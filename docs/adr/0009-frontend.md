# ADR 0009: Frontend Architecture (Phase 5)

## Status
Accepted (Phase 5).

## Context
Phase 5 needed a real analyst-facing web UI over the real `/v1` API
built in §3 -- login, company search/overview, dossier
creation/viewing/export, review-queue decisions, watchlists/alerts,
and tenant admin. Several real design decisions were made along the
way; this records them.

## Decisions

### 1. Next.js App Router, every real page a Client Component

Every page fetches the real `/v1` API on mount, client-side -- never
hardcoded demo data, and never a server-rendered data fetch. This
keeps the real session cookie (httpOnly) and the real CSRF token
(deliberately NOT in a cookie -- see decision 3) both working the
same way regardless of whether a request originates from the
browser's own fetch or an SSR pass, by never doing the latter for
anything that needs either.

**Consequence**: no real SSR performance benefit for first paint;
accepted, since this is an internal analyst tool, not a
public-facing, SEO-sensitive site.

### 2. The real `/api/*` proxy is a Route Handler, never `rewrites()`

`next.config.ts`'s own `rewrites()` return value is baked into
`routes-manifest.json` at `next build` time -- confirmed directly,
the hard way: a working build-time `LEDGERLIGHT_API_ORIGIN` value
silently kept pointing at its build-time default when the same image
was later run with a different `-e` value at container start,
exactly the scenario Docker Compose's per-environment config needs.
Fixed with a real Route Handler (`app/api/[...path]/route.ts`) whose
function body runs fresh per request, reading `process.env` live.
Proven directly: the same built image, pointed at two differently
named `api` containers via `-e` at container start (no rebuild),
reached the correct one both times.

**Consequence**: one more file to maintain (forwarding every HTTP
method, headers minus `host`/`content-length`, the body, and the
real backend's response including `Set-Cookie`) instead of a
one-line config entry -- accepted; the alternative silently breaks
multi-environment deployment.

### 3. CSRF token in `sessionStorage`, never a second cookie

The real session cookie is httpOnly (never readable by JS, by
design -- an XSS payload cannot steal it). The real CSRF token
therefore cannot ALSO live in an httpOnly cookie (the browser would
never send it back as a header the backend could compare against
anything, and a non-httpOnly CSRF cookie readable by the page's own
JS provides no real protection beyond what a response-body value
already gives). `lib/api.ts` stores it in `sessionStorage` instead --
readable only by same-origin JS, cleared when the tab closes, and
attached as `X-CSRF-Token` on every real mutating request
(`lib/auth.tsx` sets it once at login).

**Consequence**: a real XSS vulnerability anywhere in this frontend
would still be able to read `sessionStorage` and forge authenticated
requests -- this is a structural limit of any JS-readable
double-submit-style CSRF token, not something this design choice
makes worse; the httpOnly session cookie itself stays safe from XSS
either way, which is the control that actually matters most.

### 4. Security headers duplicated in `next.config.ts`, not inherited from the API

The real backend (`ledgerlight.api.app`'s own
`_security_headers_middleware`) already sets
`X-Content-Type-Options`/`X-Frame-Options`/`Referrer-Policy`/
`Content-Security-Policy` on every API response -- but a page
request to `/login`, `/companies`, etc. never goes through the
backend at all (Next.js serves those directly), so `next.config.ts`'s
own `headers()` sets the same set again, plus
`Strict-Transport-Security` (meaningless on the API's own JSON
responses, real on an actual page load over TLS).

**Consequence**: two places to keep the same policy in sync if it
ever changes -- accepted; the alternative (routing every page
request through the backend first) adds real latency for no real
benefit.

### 5. pnpm with corepack installed to a user-writable directory

This project's own Windows dev host has no admin rights available in
this environment. `corepack` (shipped with Node) was installed to a
user-writable location rather than the default, admin-requiring
global install path, so `pnpm` itself needs no elevation. A committed
`pnpm-lock.yaml` keeps installs reproducible regardless.

**Consequence**: a fresh clone on a DIFFERENT machine without this
same corepack workaround may need a one-time admin-rights npm/pnpm
install instead -- documented in `docs/deploy/local-setup-windows.md`.
