"use client";

import { Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useRequireAuth } from "@/lib/auth";
import { apiConversationMessages, type MessageItem } from "@/lib/api";

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

  const firstUser = items.find((m) => m.role === "user");

  return (
    <>
      <div className="person">
        <div>
          <b>Диалог · {conversationId.slice(0, 8)}</b>
          <span>{firstUser?.body.slice(0, 60) || "Сообщения"}</span>
        </div>
        <div className="live-call">
          <i /> {items.length} сообщений
        </div>
      </div>

      {error && <p className="status-error">{error}</p>}

      {items.length > 0 && (
        <div className="timeline-label">
          {formatDate(items[0]?.created_at)}
        </div>
      )}

      {items.map((msg) => (
        <div key={msg.id}>
          {msg.role === "assistant" ? (
            <div className="delno-result">
              <div className="result-head">
                <span>
                  <Sparkles /> DELNO
                </span>
                <small>{msg.role}</small>
              </div>
              <p style={{ margin: 0 }}>{msg.body}</p>
              {Array.isArray((msg.meta as { sources?: { title?: string; citation?: string }[] } | null)?.sources) &&
                (msg.meta as { sources: { title?: string; citation?: string }[] }).sources.length > 0 && (
                  <ul className="msg-sources">
                    {(msg.meta as { sources: { title?: string; citation?: string }[] }).sources.map((s, i) => (
                      <li key={i}>{s.title || s.citation || "Источник KB"}</li>
                    ))}
                  </ul>
                )}
            </div>
          ) : (
            <div className="msg-bubble user">
              <div className="msg-meta">{msg.role} · {formatTime(msg.created_at)}</div>
              <div className="msg-body">{msg.body}</div>
            </div>
          )}
        </div>
      ))}

      {!error && items.length === 0 && (
        <p className="inbox-empty">Сообщений пока нет</p>
      )}
    </>
  );
}

function formatDate(iso: string | null | undefined) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString("ru-RU", { dateStyle: "long", timeStyle: "short" });
  } catch {
    return iso;
  }
}

function formatTime(iso: string | null) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString("ru-RU", { timeStyle: "short" });
  } catch {
    return iso;
  }
}
