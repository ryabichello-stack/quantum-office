"use client";

import { useEffect, useState } from "react";
import { AdminFrame } from "@/components/AdminFrame";
import { useRequirePlatformAdmin } from "@/lib/auth";
import { apiGetCmsPages, apiGetTenants } from "@/lib/api";

export default function TenantsPage() {
  const { token } = useRequirePlatformAdmin();
  const [tenants, setTenants] = useState<Array<{ id: string; slug: string; name: string }>>([]);
  const [pages, setPages] = useState<Array<{ slug: string; title: string; status: string }>>([]);

  useEffect(() => {
    if (!token) return;
    apiGetTenants(token).then(setTenants).catch(() => undefined);
    apiGetCmsPages(token).then(setPages).catch(() => undefined);
  }, [token]);

  return (
    <AdminFrame>
      <div className="page-head">
        <small>Platform</small>
        <h1>Клиенты и CMS</h1>
        <p>Tenants платформы и опубликованные CMS-страницы.</p>
      </div>

      <section className="settings-section panel-card">
        <h2>Tenants</h2>
        <table className="leads-table">
          <thead>
            <tr>
              <th>Slug</th>
              <th>Name</th>
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

      <section className="settings-section panel-card" style={{ marginTop: 16 }}>
        <h2>CMS pages</h2>
        <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, lineHeight: 1.7 }}>
          {pages.map((p) => (
            <li key={p.slug}>
              {p.slug} — {p.title} [{p.status}]
            </li>
          ))}
        </ul>
      </section>
    </AdminFrame>
  );
}
