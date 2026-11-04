import type { NextConfig } from "next";

// Phase 5 §5: real security headers -- these are baked into
// routes-manifest.json at `next build` time (confirmed directly), but
// they never depend on anything runtime-environment-specific, so
// that's fine. The API proxy itself is NOT done here -- see
// app/api/[...path]/route.ts's own docstring for why `rewrites()`
// (which has the identical build-time-freezing problem) was wrong for
// that job specifically.
const nextConfig: NextConfig = {
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "no-referrer" },
          {
            key: "Content-Security-Policy",
            value:
              "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; " +
              "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'",
          },
          { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" },
        ],
      },
    ];
  },
};

export default nextConfig;
