"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { identity, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !identity) {
      router.replace("/login");
    }
  }, [identity, loading, router]);

  if (loading || !identity) {
    return null;
  }
  return <>{children}</>;
}
