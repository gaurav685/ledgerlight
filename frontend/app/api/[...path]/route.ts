import { NextRequest, NextResponse } from "next/server";

// Phase 5 §4/§5: the real API proxy. Deliberately a Route Handler,
// NOT a `next.config.ts` `rewrites()` entry -- confirmed directly
// that Next.js freezes `rewrites()`'s own return value into
// `routes-manifest.json` at `next build` time, so `BACKEND_ORIGIN`
// read there would be frozen at the IMAGE's build time, never able
// to pick up a real, different value from `docker run -e` /
// Compose's own environment at container start. A Route Handler
// function body runs fresh on every real request, so
// `process.env.LEDGERLIGHT_API_ORIGIN` here is read at real request
// time -- exactly once per build is wrong, once per request is right.
//
// Forwards every real header (except `host`, which must name this
// app's own origin, never the backend's) and the real request body,
// and returns the backend's real response -- status, headers
// (including `Set-Cookie`), and body -- completely transparently, so
// the real session cookie set by `/v1/auth/login` lands as this
// app's own first-party cookie with no extra handling here.

function backendOrigin(): string {
  return process.env.LEDGERLIGHT_API_ORIGIN ?? "http://127.0.0.1:8000";
}

async function proxy(request: NextRequest, pathSegments: string[]): Promise<NextResponse> {
  const path = pathSegments.join("/");
  const search = request.nextUrl.search;
  const targetUrl = `${backendOrigin()}/v1/${path}${search}`;

  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.delete("content-length");

  const hasBody = request.method !== "GET" && request.method !== "HEAD";
  const response = await fetch(targetUrl, {
    method: request.method,
    headers,
    body: hasBody ? await request.arrayBuffer() : undefined,
    redirect: "manual",
  });

  const responseHeaders = new Headers(response.headers);
  // `Set-Cookie` can appear multiple times -- `Headers` only exposes
  // the last one via `.get()`, so `fetch`'s own raw multi-value
  // handling (via `response.headers`) is passed straight through to
  // `NextResponse`'s own constructor, which preserves repeated keys.
  return new NextResponse(response.body, {
    status: response.status,
    headers: responseHeaders,
  });
}

type RouteParams = { params: Promise<{ path: string[] }> };

export async function GET(request: NextRequest, { params }: RouteParams) {
  return proxy(request, (await params).path);
}

export async function POST(request: NextRequest, { params }: RouteParams) {
  return proxy(request, (await params).path);
}

export async function PATCH(request: NextRequest, { params }: RouteParams) {
  return proxy(request, (await params).path);
}

export async function DELETE(request: NextRequest, { params }: RouteParams) {
  return proxy(request, (await params).path);
}

export async function PUT(request: NextRequest, { params }: RouteParams) {
  return proxy(request, (await params).path);
}
