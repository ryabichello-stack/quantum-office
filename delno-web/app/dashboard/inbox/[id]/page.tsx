"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useRequireAuth } from "@/lib/auth";
import {
  apiConversationDetail,
  apiConversationMessages,
  type ConversationDetail,
  type KnowledgeSource,
  type MessageItem,
} from "@/lib/api";
import { ConversationHeader } from "@/components/ConversationHeader";
import { DelnoResultCard } from "@/components/DelnoResultCard";
import { VoicePlayback } from "@/components/VoicePlayback";

export default function InboxThreadPage() {
  const params = useParams();
  const conversationId = String(params.id || "");
  const { token } = useRequireAuth();
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const [items, setItems] = useState<MessageItem[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!token || !conversationId) return;
    setError("");
    Promise.all([
      apiConversationDetail(token, conversationId),
      apiConversationMessages(token, conversationId),
    ])
      .then(([conv, messages]) => {
        setDetail(conv);
        setItems(messages.items);
      })
      .catch(() => setError("Не удалось загрузить диалог"));
  }, [token, conversationId]);

  const summaryBlock = detail?.summary ? (
    <DelnoResultCard
      subtitle="Итог разговора"
      body={detail.summary}
      tags={detail.tags}
    />
  ) : null;

  return (
    <>
      <ConversationHeader detail={detail} />

      {error && <p className="status-error">{error}</p>}

      {items.length > 0 && (
        <div className="timeline-label">{formatDate(items[0]?.created_at)}</div>
      )}

      <VoicePlayback
        recordingUrl={detail?.recording_url}
        durationSec={detail?.recording_duration_sec}
      />

      {summaryBlock}

      {detail?.tags && detail.tags.length > 0 && !detail.summary && (
        <DelnoResultCard body="Краткий итог пока не сформирован." tags={detail.tags} />
      )}

      {items.map((msg) => (
        <div key={msg.id}>
          {msg.role === "assistant" ? (
            <DelnoResultCard
              body={msg.body}
              sources={
                Array.isArray((msg.meta as { sources?: KnowledgeSource[] } | null)?.sources)
                  ? (msg.meta as { sources: KnowledgeSource[] }).sources
                  : undefined
              }
            />
          ) : (
            <div className="msg-bubble user">
              <div className="msg-meta">{formatTime(msg.created_at)}</div>
              <div className="msg-body">{msg.body}</div>
            </div>
          )}
        </div>
      ))}

      {!error && items.length === 0 && detail && (
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
