"use client";

import { useRequireAuth } from "@/lib/auth";
import { DashboardFrame } from "@/components/DashboardFrame";
import { OperatorStage } from "@/components/OperatorStage";

export default function OperatorPage() {
  const { token } = useRequireAuth();

  if (!token) return null;

  return (
    <DashboardFrame>
      <OperatorStage token={token} />
    </DashboardFrame>
  );
}
