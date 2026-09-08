"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { apiTenantMe, type TenantMe } from "@/lib/api";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("delno_token");
}

export function clearToken() {
  localStorage.removeItem("delno_token");
}

export function useRequireAuth() {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [me, setMe] = useState<TenantMe | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const t = getToken();
    if (!t) {
      router.replace("/");
      return;
    }
    setToken(t);
    apiTenantMe(t)
      .then(setMe)
      .catch(() => {
        clearToken();
        router.replace("/");
      })
      .finally(() => setLoading(false));
  }, [router]);

  return { token, me, loading };
}
