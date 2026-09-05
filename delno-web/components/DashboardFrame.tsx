"use client";

import { AppShell } from "@/components/AppShell";
import { useRequireAuth } from "@/lib/auth";

export function DashboardFrame({
  children,
  inboxSlot,
}: {
  children: React.ReactNode;
  inboxSlot?: React.ReactNode;
}) {
  const { me, loading } = useRequireAuth();

  if (loading) {
    return <div className="loading-screen">Загрузка…</div>;
  }

  return (
    <AppShell me={me} inboxSlot={inboxSlot}>
      {children}
    </AppShell>
  );
}
