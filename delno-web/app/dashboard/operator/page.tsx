"use client";

import { FormEvent, useState } from "react";
import { useRequireAuth } from "@/lib/auth";
import { apiOperatorChat, type KnowledgeSource } from "@/lib/api";
import { buttonPrimary, card, colors, input } from "@/lib/ui";

type ChatLine = {
  role: "user" | "assistant";
  text: string;
  sources?: KnowledgeSource[];
};

export default function OperatorPage() {
  const { token } = useRequireAuth();
  const [lines, setLines] = useState<ChatLine[]>([]);
  const [message, setMessage] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token || !message.trim() || sending) return;
    const question = message.trim();
    setMessage("");
    setSending(true);
    setError("");
    setLines((prev) => [...prev, { role: "user", text: question }]);
    try {
      const result = await apiOperatorChat(token, question, conversationId || undefined);
      setConversationId(result.conversation_id);
      setLines((prev) => [
        ...prev,
        { role: "assistant", text: result.reply, sources: result.sources || [] },
      ]);
    } catch {
      setError("Operator недоступен. Проверьте API и базу знаний.");
    } finally {
      setSending(false);
    }
  }

  return (
    <>
      <h1 style={{ margin: "0 0 8px", fontSize: 28 }}>Operator</h1>
      <p style={{ margin: "0 0 24px", color: colors.muted }}>
        Read-only KB: ответы с указанием источников (`sources`)
      </p>
      <div style={{ ...card, minHeight: 420, display: "flex", flexDirection: "column", gap: 12 }}>
        <div style={{ flex: 1, display: "grid", gap: 10, maxHeight: 480, overflow: "auto" }}>
          {lines.length === 0 && (
            <p style={{ color: colors.muted }}>Спросите про услуги, тарифы или правила из базы знаний</p>
          )}
          {lines.map((line, idx) => (
            <div
              key={idx}
              style={{
                alignSelf: line.role === "user" ? "flex-end" : "flex-start",
                maxWidth: "85%",
                padding: 12,
                borderRadius: 12,
                background: line.role === "user" ? colors.accent : "#f8fafc",
                color: line.role === "user" ? "#fff" : colors.text,
              }}
            >
              <div style={{ whiteSpace: "pre-wrap" }}>{line.text}</div>
              {line.sources && line.sources.length > 0 && (
                <ul style={{ margin: "8px 0 0", paddingLeft: 16, fontSize: 11, opacity: 0.85 }}>
                  {line.sources.map((s, i) => (
                    <li key={i}>{s.title || s.citation || s.document_id}</li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
        {error && <p style={{ color: colors.danger, margin: 0 }}>{error}</p>}
        <form onSubmit={onSubmit} style={{ display: "flex", gap: 8 }}>
          <input
            style={input}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="Ваш вопрос…"
            disabled={sending}
          />
          <button type="submit" style={buttonPrimary} disabled={sending}>
            {sending ? "…" : "Отправить"}
          </button>
        </form>
      </div>
    </>
  );
}
