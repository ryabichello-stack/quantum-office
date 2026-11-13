"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/** Home of the cabinet is Hermes — one clear entry point. */
export default function DashboardOverviewPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/dashboard/hermes");
  }, [router]);
  return <div className="loading-screen">Открываю Hermes…</div>;
}
