"use client";

import { useRequireAuth } from "@/lib/auth";
import { DashboardFrame } from "@/components/DashboardFrame";
import { OnboardingChat } from "@/components/OnboardingChat";

export default function OnboardingPage() {
  const { token } = useRequireAuth();

  if (!token) return null;

  return (
    <DashboardFrame>
      <OnboardingChat token={token} />
    </DashboardFrame>
  );
}
