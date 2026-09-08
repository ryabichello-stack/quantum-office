"use client";

import { useEffect, useState } from "react";
import { AdminShell } from "@/components/AdminShell";
import { useRequirePlatformAdmin } from "@/lib/auth";
import { apiGetCmsPages, apiGetTenants } from "@/lib/api";

export default function TenantsPage() {
  const { token, ready } = useRequirePlatformAdmin();
  const [tenants, setTenants] = useState<Array<{ id: string; slug: string; name: string }>>([]);
  const [pages, setPages] = useState<Array<{ slug: string; title: string; status: string }>>([]);

  useEffect(() => {
    if (!token) return;
    apiGetTenants(token).then(setTenants).catch(() => undefined);
    apiGetCmsPages(token).then(setPages).catch(() => undefined);
  }, [token]);

  if (!ready) {
    return (
      <main style={{ maxWidth: 960, margin: "40px auto", padding: 24 }}>
        <p>Загрузка…</p>
      </main>
    );
  }

  return (
    <AdminShell title="Клиенты">
      <section>
        <h2 style={{ fontSize: 18 }}>Tenants</h2>
        <table style={{ width: "100%", borderCollapse: "collapse", marginTop: 12 }}>
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
        <h2 style={{ fontSize: 18 }}>CMS pages (platform)</h2>
        <ul>
          {pages.map((p) => (
            <li key={p.slug}>
              {p.slug} — {p.title} [{p.status}]
            </li>
          ))}
        </ul>
      </section>
    </AdminShell>
  );
}
