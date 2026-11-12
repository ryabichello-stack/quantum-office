"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/** Onboarding lives inside Hermes now. */
export default function OnboardingRedirectPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/dashboard/hermes");
  }, [router]);
  return <div className="loading-screen">Открываю Hermes…</div>;
}
