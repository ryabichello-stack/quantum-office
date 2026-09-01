"use client";

import { FormEvent, useState } from "react";
import { Sparkles } from "lucide-react";
import { useRequireAuth } from "@/lib/auth";
import { apiOperatorChat, type KnowledgeSource } from "@/lib/api";
import { DashboardFrame } from "@/components/DashboardFrame";

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
      setLines((prev) => [...prev, { role: "assistant", text: result.reply, sources: result.sources || [] }]);
    } catch {
      setError("Operator недоступен. Проверьте API и базу знаний.");
    } finally {
      setSending(false);
    }
  }

  return (
    <DashboardFrame>
      <div className="page-head">
        <small>Operator · read-only KB</small>
        <h1>Operator</h1>
        <p>Ответы по базе знаний с указанием источников</p>
      </div>

      {lines.length === 0 && (
        <div className="delno-result">
          <div className="result-head">
            <span>
              <Sparkles /> DELNO
            </span>
          </div>
          <p style={{ margin: 0 }}>Спросите про услуги, тарифы или правила из базы знаний</p>
        </div>
      )}

      {lines.map((line, idx) =>
        line.role === "user" ? (
          <div key={idx} className="msg-bubble user">
            <div className="msg-body">{line.text}</div>
          </div>
        ) : (
          <div key={idx} className="delno-result">
            <div className="result-head">
              <span>
                <Sparkles /> DELNO
              </span>
            </div>
            <p style={{ margin: 0 }}>{line.text}</p>
            {line.sources && line.sources.length > 0 && (
              <ul className="msg-sources">
                {line.sources.map((s, i) => (
                  <li key={i}>{s.title || s.citation || s.document_id}</li>
                ))}
              </ul>
            )}
          </div>
        ),
      )}

      {error && <p className="status-error">{error}</p>}

      <form className="chat-form" onSubmit={onSubmit}>
        <input
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Ваш вопрос…"
          disabled={sending}
        />
        <button type="submit" className="btn-primary" disabled={sending}>
          {sending ? "…" : "Отправить"}
        </button>
      </form>
    </DashboardFrame>
  );
}
