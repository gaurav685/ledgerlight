import type { NextConfig } from "next";

// Phase 5 §4: every /api/* request the browser makes is proxied,
// server-side, straight through to the real FastAPI backend -- same
// origin from the browser's own point of view, so the real session
// cookie Set by /api/auth/login is scoped to this app's own origin
// and is sent back automatically on every later /api/* request, with
// no CORS configuration needed anywhere.
const BACKEND_ORIGIN = process.env.LEDGERLIGHT_API_ORIGIN ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${BACKEND_ORIGIN}/v1/:path*` }];
  },
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
