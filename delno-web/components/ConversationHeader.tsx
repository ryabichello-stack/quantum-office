"use client";

import type { ConversationDetail } from "@/lib/api";

export function ConversationHeader({ detail }: { detail: ConversationDetail | null }) {
  if (!detail) {
    return (
      <div className="person">
        <div>
          <b>Диалог</b>
          <span>Загрузка…</span>
        </div>
      </div>
    );
  }

  const name =
    detail.visitor_name ||
    detail.contact_ref ||
    (detail.channel_label?.includes("сайт") ? "Новый посетитель" : "Клиент");

  const badge =
    detail.call_status === "completed" || detail.recording_url
      ? "разговор завершён"
      : `${detail.message_count ?? 0} сообщений`;

  return (
    <div className="person">
      <div>
        <b>{name}</b>
        <span>{detail.subtitle || detail.channel_label}</span>
      </div>
      <div className="live-call">
        <i /> {badge}
      </div>
    </div>
  );
}
