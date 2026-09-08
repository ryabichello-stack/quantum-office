"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ADMIN_TOKEN_KEY, apiMe, type AdminUser } from "@/lib/api";

export function useRequirePlatformAdmin() {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<AdminUser | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem(ADMIN_TOKEN_KEY);
    if (!stored) {
      router.replace("/login");
      return;
    }
    apiMe(stored)
      .then((me) => {
        if (me.role !== "platform_admin") {
          localStorage.removeItem(ADMIN_TOKEN_KEY);
          router.replace("/login");
          return;
        }
        setToken(stored);
        setUser(me);
        setReady(true);
      })
      .catch(() => {
        localStorage.removeItem(ADMIN_TOKEN_KEY);
        router.replace("/login");
      });
  }, [router]);

  return { token, user, ready };
}
