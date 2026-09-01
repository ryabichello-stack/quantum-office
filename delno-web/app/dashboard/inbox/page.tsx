"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRequireAuth } from "@/lib/auth";
import { apiConversations, type ConversationItem } from "@/lib/api";
import { card, colors, table, td, th } from "@/lib/ui";

export default function InboxPage() {
  const { token } = useRequireAuth();
  const [items, setItems] = useState<ConversationItem[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!token) return;
    apiConversations(token)
      .then((data) => setItems(data.items))
      .catch(() => setError("Не удалось загрузить диалоги"));
  }, [token]);

  return (
    <>
      <h1 style={{ margin: "0 0 8px", fontSize: 28 }}>Диалоги</h1>
      <p style={{ margin: "0 0 24px", color: colors.muted }}>История разговоров Operator и каналов</p>
      <div style={card}>
        {error && <p style={{ color: colors.danger }}>{error}</p>}
        {!error && items.length === 0 && <p style={{ color: colors.muted }}>Диалогов пока нет</p>}
        {items.length > 0 && (
          <table style={table}>
            <thead>
              <tr>
                <th style={th}>Канал</th>
                <th style={th}>Статус</th>
                <th style={th}>Создан</th>
                <th style={th}></th>
              </tr>
            </thead>
            <tbody>
              {items.map((row) => (
                <tr key={row.id}>
                  <td style={td}>{row.channel}</td>
                  <td style={td}>{row.status}</td>
                  <td style={td}>{formatDate(row.created_at)}</td>
                  <td style={td}>
                    <Link href={`/dashboard/inbox/${row.id}`}>Открыть →</Link>
                  </td>
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
