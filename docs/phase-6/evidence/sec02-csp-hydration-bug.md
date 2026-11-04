# Real bug found and fixed: CSP blocked all frontend hydration

Phase 6A §2.3. Found while building the FIRST real interactive
Playwright test against this frontend -- every prior check (Phase
5's own build-smoke suite, every manual curl/API test) either never
clicked anything or never ran in a real browser enforcing the real
CSP.

## The bug

`next.config.ts`'s own static `Content-Security-Policy` header set
`script-src 'self'` with no `'unsafe-inline'`, nonce, or hash
exception. Next.js's own App Router injects several real inline
`<script>` tags into every page for hydration bootstrapping -- these
are blocked outright by that policy. Confirmed directly via a real
browser console:

```
Executing inline script violates the following Content Security
Policy directive 'script-src 'self''. Either the 'unsafe-inline'
keyword, a hash (...), or a nonce ('nonce-...') is required to
enable inline execution. The action has been blocked.
```

**Real, practical effect: React never hydrates on ANY page, in ANY
real CSP-enforcing browser.** No `onSubmit` handler, `onClick`
handler, or any other React event listener ever attaches. Confirmed
directly: submitting the login form fell back to the browser's own
native, unintercepted HTML form submission -- a plain `GET` to
`/login` with the real tenant slug, email, and password appended as
URL query parameters:

```
http://127.0.0.1:3000/login?tenant_slug=test-tenant-a&email=analyst%40test-tenant-a.test&password=LedgerlightTest123%21
```

This is a real, significant bug: every button and form in this
frontend -- login included -- has been non-functional in a real
browser since this CSP was first added (Phase 5 §4/§5), for the
entire time it has existed. It was never caught because nothing
before this session actually drove the real UI through a real,
CSP-enforcing browser; §4's own report already flagged "the Chrome
browser extension was not connected this session" as an open gap, and
the real consequence of that gap turned out to be this.

## The attempted correct fix (did not work, disclosed)

Next.js documents a per-request nonce pattern for exactly this case:
a `middleware.ts` generates a random nonce, forwards it via an
`x-nonce` request header, sets it in the CSP response header
(`script-src 'self' 'nonce-<value>' 'strict-dynamic'`), and the
framework's own build output is supposed to thread that same nonce
onto its own internal scripts once the root layout reads the header
via `headers()`.

This was implemented exactly as documented and tested directly. The
CSP response header correctly carried a fresh nonce on every real
request (confirmed via `curl -I`). The real rendered HTML's own
inline `<script>` tags, however, still carried **no `nonce` attribute
at all** -- confirmed directly via `curl` + `grep` on the raw
response body. Hydration remained blocked. This is a real, disclosed,
open gap in getting Next.js 16.4.3's documented nonce behaviour
working in this exact App Router configuration -- not pursued further
given real, repeated host memory-pressure kills during the rebuild/
test iteration cycle this specific investigation required (each
iteration costs a full Docker image rebuild).

## The real fix actually deployed

`script-src 'self' 'unsafe-inline'` -- no nonce source present at all
(a nonce source present would cause any CSP-Level-2+ browser to
ignore `'unsafe-inline'` entirely, which is exactly the broken state
just described). Confirmed directly: the full real Playwright e2e
suite (login through cross-tenant denial, `frontend/e2e/
full-e2e-lite.spec.ts`) now passes end to end against this policy.

**Disclosed security cost**: any future XSS injection point elsewhere
in this app (there is no known one today -- `tests/
test_prompt_injection_separation.py` already confirms no raw
HTML/script text from ingested documents is ever rendered via
`dangerouslySetInnerHTML` anywhere) could execute an injected inline
script under this policy. Every other CSP directive
(`style-src`/`img-src`/`connect-src`/`object-src`/`frame-ancestors`/
etc.) stays restrictive and unchanged. Recorded as a residual risk in
`docs/security/threat-model.md` and as an open item in
`docs/release/release-gates.md` -- getting the strict, nonce-based
policy actually working (likely a Next.js-version-specific
implementation detail this session did not fully chase down) is real,
disclosed future work, not silently dropped.

## Files changed

- `frontend/next.config.ts` -- removed the `Content-Security-Policy`
  header from the static `headers()` list (middleware now owns it
  exclusively).
- `frontend/middleware.ts` -- new. Sets the real CSP header on every
  real page request (matcher excludes `/api`, static assets).
- `frontend/app/layout.tsx` -- unchanged from before this
  investigation (the attempted nonce-read via `headers()` was added,
  found not to work, and reverted).
