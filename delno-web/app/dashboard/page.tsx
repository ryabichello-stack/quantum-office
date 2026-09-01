"use client";

import { useEffect, useState } from "react";
import { apiTenantMe } from "@/lib/api";

export default function DashboardPage() {
  const [me, setMe] = useState<{ tenant_slug?: string; role?: string } | null>(null);

  useEffect(() => {
    const token = localStorage.getItem("delno_token");
    if (!token) {
      window.location.href = "/";
      return;
    }
    apiTenantMe(token).then(setMe).catch(() => (window.location.href = "/"));
  }, []);

  return (
    <main style={{ maxWidth: 960, margin: "40px auto", padding: 24 }}>
      <h1>Dashboard</h1>
      {me && (
        <p>
          Tenant: <b>{me.tenant_slug}</b> · role: {me.role}
        </p>
      )}
      <section style={{ marginTop: 32, display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(200px,1fr))", gap: 16 }}>
        {["Inbox", "Knowledge", "Channels", "Operator", "Settings"].map((item) => (
          <div key={item} style={{ padding: 20, borderRadius: 12, background: "#fff", border: "1px solid #e2e8f0" }}>
            <h3>{item}</h3>
            <p style={{ opacity: 0.6, fontSize: 14 }}>Coming in E2–E3</p>
          </div>
        ))}
      </section>
    </main>
  );
}
