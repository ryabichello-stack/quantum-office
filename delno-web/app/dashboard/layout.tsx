"use client";

import { AppShell } from "@/components/AppShell";
import { useRequireAuth } from "@/lib/auth";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { me, loading } = useRequireAuth();

  if (loading) {
    return (
      <div style={{ minHeight: "100vh", display: "grid", placeItems: "center", background: "#f4f6f8" }}>
        Загрузка…
      </div>
    );
  }

  return <AppShell me={me}>{children}</AppShell>;
}
