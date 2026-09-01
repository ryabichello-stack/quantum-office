"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiGetCmsPages, apiGetTenants } from "@/lib/api";

export default function TenantsPage() {
  const [tenants, setTenants] = useState<Array<{ id: string; slug: string; name: string }>>([]);
  const [pages, setPages] = useState<Array<{ slug: string; title: string; status: string }>>([]);

  useEffect(() => {
    const token = localStorage.getItem("delno_token");
    if (!token) {
      window.location.href = "/login";
      return;
    }
    apiGetTenants(token).then(setTenants).catch(() => (window.location.href = "/login"));
    apiGetCmsPages(token).then(setPages).catch(() => undefined);
  }, []);

  return (
    <main style={{ maxWidth: 960, margin: "40px auto", padding: 24 }}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>Tenants</h1>
        <Link href="/login" style={{ color: "#93c5fd" }}>Logout</Link>
      </header>
      <section style={{ marginTop: 32 }}>
        <h2>Клиенты</h2>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th align="left">Slug</th>
              <th align="left">Name</th>
            </tr>
          </thead>
          <tbody>
            {tenants.map((t) => (
              <tr key={t.id}>
                <td>{t.slug}</td>
                <td>{t.name}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <section style={{ marginTop: 32 }}>
        <h2>CMS pages (platform)</h2>
        <ul>
          {pages.map((p) => (
            <li key={p.slug}>{p.slug} — {p.title} [{p.status}]</li>
          ))}
        </ul>
      </section>
    </main>
  );
}
