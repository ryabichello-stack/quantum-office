"use client";

import { useRequireAuth } from "@/lib/auth";
import { DashboardFrame } from "@/components/DashboardFrame";
import { HermesStage } from "@/components/HermesStage";

export default function HermesPage() {
  const { token } = useRequireAuth();

  if (!token) return null;

  return (
    <DashboardFrame>
      <HermesStage token={token} />
    </DashboardFrame>
  );
}
