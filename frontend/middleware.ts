import { NextResponse } from "next/server";

// Phase 6A §2: a real, previously-undiscovered production bug found
// while building the first real interactive Playwright e2e test
// against this frontend (every prior check was either a static
// render check or a direct API/curl test -- never a real click
// through a real browser enforcing the real CSP). `next.config.ts`'s
// own static `script-src 'self'` (with no `'unsafe-inline'`, no
// nonce, no hash) blocks Next.js's own required inline hydration
// bootstrap scripts outright -- confirmed directly via a real
// browser's own console: "Executing inline script violates ...
// script-src 'self'". The practical effect: React never hydrates on
// ANY page, in ANY real CSP-enforcing browser -- no onSubmit handler
// ever attaches, so every form in this app (login included) silently
// falls back to a native, unintercepted HTML GET submission (real
// credentials appearing in the URL as query parameters, confirmed
// directly). This is why the login form test failed outright, not a
// test-timing issue -- a longer wait never helps something that
// never happens.
//
// The CORRECT fix is Next.js's own documented per-request-nonce
// pattern (generate here, forward via an `x-nonce` request header,
// read it in the root layout via `headers()` so Next's own build
// output threads the same nonce onto its own internal scripts). This
// was actually implemented and tested directly -- confirmed, by
// inspecting the real rendered HTML, that it does NOT work in this
// exact Next.js 16.4.3 App Router setup: the CSP response header
// correctly carries a fresh nonce on every request, but Next's own
// inline bootstrap `<script>` tags still render with no `nonce`
// attribute at all, so they remain blocked regardless. This is a
// real, disclosed, open gap -- see docs/release/release-gates.md and
// docs/security/threat-model.md's own residual-risk entry for it.
//
// The PRAGMATIC fix deployed here instead: 'unsafe-inline' for
// script-src, with NO nonce source present (a nonce present would
// cause CSP-Level-2+ browsers to ignore 'unsafe-inline' entirely,
// which is exactly the broken state just described) -- this restores
// real interactivity (confirmed directly: the Playwright e2e suite
// passes against it). The real, disclosed cost: any future XSS
// injection point elsewhere in this app could execute an injected
// inline script under this policy. Every other CSP directive below
// stays restrictive.
export function middleware() {
  const cspHeader = `
    default-src 'self';
    script-src 'self' 'unsafe-inline';
    style-src 'self' 'unsafe-inline';
    img-src 'self' data:;
    connect-src 'self';
    font-src 'self';
    object-src 'none';
    base-uri 'self';
    form-action 'self';
    frame-ancestors 'none';
  `;
  const contentSecurityPolicyHeaderValue = cspHeader.replace(/\s{2,}/g, " ").trim();

  const response = NextResponse.next();
  response.headers.set("Content-Security-Policy", contentSecurityPolicyHeaderValue);
  return response;
}

export const config = {
  matcher: [
    // Every real page request except static assets and the API proxy
    // route -- the API proxy forwards the real backend's own CSP
    // header untouched; applying a second, different one here would
    // conflict.
    "/((?!api|_next/static|_next/image|favicon.ico).*)",
  ],
};
