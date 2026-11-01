"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { apiFetch, setStoredCsrfToken } from "./api";
import type { IdentityOut, LoginResponse } from "./types";

interface AuthState {
  identity: IdentityOut | null;
  loading: boolean;
  login: (tenantSlug: string, email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [identity, setIdentity] = useState<IdentityOut | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiFetch<IdentityOut>("/auth/me")
      .then(setIdentity)
      .catch(() => setIdentity(null))
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (tenantSlug: string, email: string, password: string) => {
    const response = await apiFetch<LoginResponse>("/auth/login", {
      method: "POST",
      skipCsrf: true,
      body: { tenant_slug: tenantSlug, email, password },
    });
    setStoredCsrfToken(response.csrf_token);
    setIdentity(response.identity);
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiFetch("/auth/logout", { method: "POST" });
    } catch {
      // A real, already-invalid session still needs the real local
      // state cleared below -- never block logout on the server call.
    }
    setStoredCsrfToken(null);
    setIdentity(null);
  }, []);

  return (
    <AuthContext.Provider value={{ identity, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (context === null) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
