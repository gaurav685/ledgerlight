import type { NextConfig } from "next";

// Phase 5 §5: real security headers -- these are baked into
// routes-manifest.json at `next build` time (confirmed directly), but
// they never depend on anything runtime-environment-specific, so
// that's fine. The API proxy itself is NOT done here -- see
// app/api/[...path]/route.ts's own docstring for why `rewrites()`
// (which has the identical build-time-freezing problem) was wrong for
// that job specifically.
//
// Phase 6A §2: Content-Security-Policy moved OUT of this static list
// into middleware.ts -- a real, found bug: a static `script-src
// 'self'` with no nonce/hash/'unsafe-inline' blocks Next.js's own
// required inline hydration scripts outright, so React never
// hydrates on any page in a real CSP-enforcing browser (confirmed
// directly: every form silently fell back to an unintercepted native
// HTML submission). middleware.ts's own per-request nonce is the real
// fix; see its own docstring.
const nextConfig: NextConfig = {
  // Phase 6A §2: a real ZAP baseline finding -- Next.js's own
  // "X-Powered-By: Next.js" header (on by default) is a real,
  // if minor, server-technology information leak. Disabled.
  poweredByHeader: false,
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "no-referrer" },
          { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" },
          // Phase 6A §2: another real ZAP baseline finding -- no
          // Permissions-Policy header was set at all. This app uses
          // none of these real browser features anywhere, so every
          // one is denied outright.
          {
            key: "Permissions-Policy",
            value:
              "camera=(), microphone=(), geolocation=(), payment=(), usb=(), " +
              "interest-cohort=()",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
