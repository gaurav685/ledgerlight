"use client";

// Phase 5 §4: the one real HTTP client every page uses to reach the
// real `/v1` API, proxied through Next.js's own rewrite (see
// next.config.ts) so the browser never talks cross-origin. A
// deliberate, disclosed simplification: every data page in this app
// is a Client Component that fetches here on mount, never a Server
// Component doing the fetch -- the server side of this app never
// sees the real session cookie, so there is nothing to forward.

const CSRF_STORAGE_KEY = "ll_csrf_token";

export class ApiError extends Error {
  readonly status: number;
  readonly requestId: string | null;

  constructor(status: number, detail: string, requestId: string | null) {
    super(detail);
    this.status = status;
    this.requestId = requestId;
  }
}

function getStoredCsrfToken(): string | null {
  try {
    return sessionStorage.getItem(CSRF_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function setStoredCsrfToken(token: string | null): void {
  try {
    if (token === null) {
      sessionStorage.removeItem(CSRF_STORAGE_KEY);
    } else {
      sessionStorage.setItem(CSRF_STORAGE_KEY, token);
    }
  } catch {
    // Real private-browsing/storage-disabled gap -- the CSRF check will
    // then real-reject the next mutation with a 403, which is a correct
    // (if less convenient) outcome, never a silent bypass.
  }
}

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  // Only `/v1/auth/login` is exempt -- every other request either
  // doesn't mutate (GET) or needs the real CSRF header.
  skipCsrf?: boolean;
}

export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = options.method ?? "GET";
  const headers: Record<string, string> = {};
  let body: string | undefined;
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.body);
  }
  if (method !== "GET" && !options.skipCsrf) {
    const csrfToken = getStoredCsrfToken();
    if (csrfToken) {
      headers["X-CSRF-Token"] = csrfToken;
    }
  }

  const response = await fetch(`/api${path}`, {
    method,
    headers,
    body,
    credentials: "same-origin",
  });

  if (response.status === 204) {
    return undefined as T;
  }

  const requestId = response.headers.get("X-Request-ID");
  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (!response.ok) {
    const detail =
      payload && typeof payload === "object" && "detail" in payload
        ? String((payload as { detail: unknown }).detail)
        : `request failed with status ${response.status}`;
    throw new ApiError(response.status, detail, requestId);
  }

  return payload as T;
}
