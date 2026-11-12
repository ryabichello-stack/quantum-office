"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/** Legacy Operator route → Hermes. */
export default function OperatorRedirectPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/dashboard/hermes");
  }, [router]);
  return <div className="loading-screen">Открываю Hermes…</div>;
}
