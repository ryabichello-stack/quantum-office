"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRequireAuth } from "@/lib/auth";
import { apiLeadsList, type LeadItem } from "@/lib/api";
import { DashboardFrame } from "@/components/DashboardFrame";
import { CabinetCard, CabinetEmpty, CabinetPage } from "@/components/CabinetPage";

export default function LeadsPage() {
  const { token } = useRequireAuth();
  const [items, setItems] = useState<LeadItem[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    apiLeadsList(token)
      .then((data) => setItems(data.items))
      .catch(() => setError("Не удалось загрузить заявки"))
      .finally(() => setLoading(false));
  }, [token]);

  return (
    <DashboardFrame>
      <CabinetPage
        kicker="Входящие"
        title="Заявки"
        lead="Реальные обращения с сайта и каналов. Не тестовые заглушки."
        actions={
          <Link href="/dashboard/hermes" className="hx-chip-link">
            Спросить Hermes
          </Link>
        }
      >
        <CabinetCard title={loading ? "Загрузка…" : `${items.length} заявок`}>
          {error ? <p className="hx-inline-error">{error}</p> : null}
          {!error && !loading && items.length === 0 ? (
            <CabinetEmpty
              title="Заявок пока нет"
              lead="Когда посетитель оставит контакты на сайте — они появятся здесь."
              action={
                <Link href="/dashboard/hermes" className="hx-chip-link">
                  Настроить сайт через Hermes
                </Link>
              }
            />
          ) : null}
          {items.length > 0 ? (
            <div className="hx-table-wrap">
              <table className="hx-table">
                <thead>
                  <tr>
                    <th>Когда</th>
                    <th>Кто</th>
                    <th>Контакт</th>
                    <th>Компания</th>
                    <th>Откуда</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((lead) => (
                    <tr key={lead.id}>
                      <td>{formatDate(lead.created_at)}</td>
                      <td>
                        <strong>{lead.name}</strong>
                        {lead.email ? <small className="hx-td-sub">{lead.email}</small> : null}
                      </td>
                      <td>{lead.phone || "—"}</td>
                      <td>
                        {lead.company || "—"}
                        {lead.inn ? <small className="hx-td-sub">ИНН {lead.inn}</small> : null}
                      </td>
                      <td>
                        <span className="hx-tag">{lead.source || "сайт"}</span>
                        {lead.party_enriched ? <span className="hx-tag soft">DaData</span> : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </CabinetCard>
      </CabinetPage>
    </DashboardFrame>
  );
}

function formatDate(iso: string | null) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("ru-RU", {
      timeZone: "Europe/Moscow",
      dateStyle: "short",
      timeStyle: "short",
    });
  } catch {
    return iso;
  }
}
