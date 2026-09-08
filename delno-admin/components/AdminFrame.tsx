"use client";

import { AdminShell } from "@/components/AdminShell";
import { useRequirePlatformAdmin } from "@/lib/auth";

export function AdminFrame({ children }: { children: React.ReactNode }) {
  const { ready } = useRequirePlatformAdmin();

  if (!ready) {
    return <div className="loading-screen">Загрузка…</div>;
  }

  return <AdminShell>{children}</AdminShell>;
}
