"use client";

import { useEffect, useState } from "react";
import { useRequireAuth } from "@/lib/auth";
import { apiLeadsList, type LeadItem } from "@/lib/api";
import { card, colors, table, td, th } from "@/lib/ui";

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
    <>
      <h1 style={{ margin: "0 0 8px", fontSize: 28 }}>Заявки</h1>
      <p style={{ margin: "0 0 24px", color: colors.muted }}>Leads из сайта, виджета и других каналов</p>
      <div style={card}>
        {error && <p style={{ color: colors.danger }}>{error}</p>}
        {!error && items.length === 0 && <p style={{ color: colors.muted }}>Пока нет заявок</p>}
        {items.length > 0 && (
          <table style={table}>
            <thead>
              <tr>
                <th style={th}>Дата</th>
                <th style={th}>Имя</th>
                <th style={th}>Телефон</th>
                <th style={th}>Компания</th>
                <th style={th}>ИНН</th>
                <th style={th}>Источник</th>
              </tr>
            </thead>
            <tbody>
              {items.map((lead) => (
                <tr key={lead.id}>
                  <td style={td}>{formatDate(lead.created_at)}</td>
                  <td style={td}>{lead.name}</td>
                  <td style={td}>{lead.phone}</td>
                  <td style={td}>{lead.company || "—"}</td>
                  <td style={td}>
                    {lead.inn ? (
                      <span title={lead.party_enriched ? "Обогащено DaData" : undefined}>{lead.inn}</span>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td style={td}>{lead.source}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
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
