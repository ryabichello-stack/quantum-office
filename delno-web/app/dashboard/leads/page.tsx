"use client";

import { useEffect, useState } from "react";
import { useRequireAuth } from "@/lib/auth";
import { apiLeadsList, type LeadItem } from "@/lib/api";
import { DashboardFrame } from "@/components/DashboardFrame";

export default function LeadsPage() {
  const { token } = useRequireAuth();
  const [items, setItems] = useState<LeadItem[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!token) return;
    apiLeadsList(token)
      .then((data) => setItems(data.items))
      .catch(() => setError("Не удалось загрузить заявки"));
  }, [token]);

  return (
    <DashboardFrame>
      <div className="page-head">
        <small>Рабочее пространство</small>
        <h1>Заявки</h1>
        <p>Leads из сайта, виджета и других каналов</p>
      </div>
      <div className="panel-card">
        {error && <p className="status-error">{error}</p>}
        {!error && items.length === 0 && <p className="inbox-empty">Пока нет заявок</p>}
        {items.length > 0 && (
          <table className="leads-table">
            <thead>
              <tr>
                <th>Дата</th>
                <th>Имя</th>
                <th>Телефон</th>
                <th>Компания</th>
                <th>ИНН</th>
                <th>Источник</th>
              </tr>
            </thead>
            <tbody>
              {items.map((lead) => (
                <tr key={lead.id}>
                  <td>{formatDate(lead.created_at)}</td>
                  <td>
                    <b>{lead.name}</b>
                  </td>
                  <td>{lead.phone}</td>
                  <td>{lead.company || "—"}</td>
                  <td>
                    {lead.inn ? (
                      <span title={lead.party_enriched ? "Обогащено DaData" : undefined}>{lead.inn}</span>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td>
                    <span className="result-tags">
                      <span>{lead.source}</span>
                      {lead.party_enriched && <span>DaData</span>}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </DashboardFrame>
  );
}

function formatDate(iso: string | null) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("ru-RU", { dateStyle: "short", timeStyle: "short" });
  } catch {
    return iso;
  }
}
