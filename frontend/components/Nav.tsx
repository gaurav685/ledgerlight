"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";

export function Nav() {
  const { identity, logout, loading } = useAuth();
  const router = useRouter();

  if (loading) {
    return null;
  }

  async function handleLogout() {
    await logout();
    router.push("/login");
  }

  return (
    <nav className="topnav" aria-label="Primary">
      <Link href="/companies">Companies</Link>
      {identity && (
        <>
          <Link href="/dossiers">Dossiers</Link>
          <Link href="/review">Review queue</Link>
          <Link href="/watchlists">Watchlists</Link>
          {identity.role === "tenant_admin" && <Link href="/admin">Admin</Link>}
        </>
      )}
      <span className="spacer" />
      {identity ? (
        <>
          <span aria-label="Current role">{identity.role}</span>
          <button type="button" className="btn secondary" onClick={handleLogout}>
            Log out
          </button>
        </>
      ) : (
        <Link href="/login">Log in</Link>
      )}
    </nav>
  );
}
