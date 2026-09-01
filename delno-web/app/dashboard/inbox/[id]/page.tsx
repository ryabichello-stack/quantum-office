"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useRequireAuth } from "@/lib/auth";
import { apiConversationMessages, type MessageItem } from "@/lib/api";
import { card, colors } from "@/lib/ui";

export default function InboxThreadPage() {
  const params = useParams();
  const conversationId = String(params.id || "");
  const { token } = useRequireAuth();
  const [items, setItems] = useState<MessageItem[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!token || !conversationId) return;
    apiConversationMessages(token, conversationId)
      .then((data) => setItems(data.items))
      .catch(() => setError("Не удалось загрузить сообщения"));
  }, [token, conversationId]);

  return (
    <>
      <Link href="/dashboard/inbox" style={{ color: colors.muted, textDecoration: "none" }}>
        ← К списку диалогов
      </Link>
      <h1 style={{ margin: "12px 0 24px", fontSize: 24 }}>Диалог</h1>
      <div style={{ ...card, display: "grid", gap: 12 }}>
        {error && <p style={{ color: colors.danger }}>{error}</p>}
        {items.map((msg) => (
          <div
            key={msg.id}
            style={{
              padding: 12,
              borderRadius: 10,
              background: msg.role === "user" ? "#f1f5f9" : "#ecfdf5",
              border: `1px solid ${colors.border}`,
            }}
          >
            <div style={{ fontSize: 11, color: colors.muted, marginBottom: 6 }}>
              {msg.role} · {formatDate(msg.created_at)}
            </div>
            <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.5 }}>{msg.body}</div>
            {Array.isArray((msg.meta as { sources?: unknown[] } | null)?.sources) &&
              (msg.meta as { sources: { title?: string; citation?: string }[] }).sources.length > 0 && (
                <ul style={{ margin: "10px 0 0", paddingLeft: 18, fontSize: 12, color: colors.muted }}>
                  {(msg.meta as { sources: { title?: string; citation?: string }[] }).sources.map((s, i) => (
                    <li key={i}>{s.title || s.citation || "Источник KB"}</li>
                  ))}
                </ul>
              )}
          </div>
        ))}
      </div>
    </>
  );
}

function formatDate(iso: string | null) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString("ru-RU", { dateStyle: "short", timeStyle: "short" });
  } catch {
    return iso;
  }
}
