"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { Paperclip, Sparkles } from "lucide-react";
import {
  apiConversationMessages,
  apiOnboardingStart,
  apiOnboardingStatus,
  apiOperatorChat,
  type MessageItem,
  type OnboardingStatus,
} from "@/lib/api";

type ChatLine = {
  id?: string;
  role: "user" | "assistant";
  text: string;
};

function mapMessages(items: MessageItem[]): ChatLine[] {
  return items
    .filter((m) => m.role === "user" || m.role === "assistant")
    .map((m) => ({
      id: m.id,
      role: m.role as "user" | "assistant",
      text: m.body,
    }));
}

export function OnboardingChat({ token }: { token: string }) {
  const [lines, setLines] = useState<ChatLine[]>([]);
  const [message, setMessage] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [onboardingStatus, setOnboardingStatus] = useState<OnboardingStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const threadRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = useCallback(() => {
    const el = threadRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function boot() {
      setLoading(true);
      setError("");
      try {
        const [start, status] = await Promise.all([apiOnboardingStart(token), apiOnboardingStatus(token)]);
        if (cancelled) return;
        setOnboardingStatus(status);
        setConversationId(start.conversation_id);
        const history = await apiConversationMessages(token, start.conversation_id);
        if (cancelled) return;
        const mapped = mapMessages(history.items);
        setLines(mapped.length > 0 ? mapped : [{ role: "assistant", text: start.reply }]);
      } catch {
        if (!cancelled) setError("Не удалось начать onboarding. Проверьте API.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void boot();
    return () => {
      cancelled = true;
    };
  }, [token]);

  useEffect(() => {
    scrollToBottom();
  }, [lines, scrollToBottom]);

  const sendText = useCallback(
    async (text: string) => {
      const question = text.trim();
      if (!question || sending || !conversationId) return;
      setSending(true);
      setError("");
      setLines((prev) => [...prev, { role: "user", text: question }]);
      try {
        const result = await apiOperatorChat(token, question, conversationId, "text", "onboarding");
        setConversationId(result.conversation_id);
        setLines((prev) => [...prev, { role: "assistant", text: result.reply }]);
        const status = await apiOnboardingStatus(token);
        setOnboardingStatus(status);
      } catch {
        setError("DELNO временно недоступен. Попробуйте ещё раз.");
      } finally {
        setSending(false);
      }
    },
    [token, conversationId, sending],
  );

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const q = message.trim();
    if (!q) return;
    setMessage("");
    await sendText(q);
  }

  const statusLabel =
    onboardingStatus?.status === "published"
      ? "Готово — DELNO отвечает клиентам"
      : onboardingStatus?.status === "summary_ready"
        ? "Сводка готова — подтвердите"
        : "Сбор знаний";

  return (
    <div className="onboarding-stage">
      <div className="page-head onboarding-head">
        <small>Настройка DELNO</small>
        <h1>Расскажите о бизнесе</h1>
        <p>
          Один диалог — текст, ссылка на сайт или документы. DELNO сам соберёт знания и покажет, что понял.
        </p>
        {!loading && onboardingStatus && (
          <span className={`onboarding-badge status-${onboardingStatus.status || "in_progress"}`}>{statusLabel}</span>
        )}
      </div>

      {loading ? (
        <p className="login-status">Загрузка диалога…</p>
      ) : (
        <>
          <div className="onboarding-thread operator-thread" ref={threadRef}>
            {lines.map((line, idx) =>
              line.role === "user" ? (
                <div key={line.id || idx} className="msg-bubble user">
                  <div className="msg-body">{line.text}</div>
                </div>
              ) : (
                <div key={line.id || idx} className="delno-result">
                  <div className="result-head">
                    <span>
                      <Sparkles /> DELNO
                    </span>
                  </div>
                  <p style={{ margin: 0, whiteSpace: "pre-wrap" }}>{line.text}</p>
                </div>
              ),
            )}
            {sending && (
              <div className="delno-result onboarding-typing">
                <div className="result-head">
                  <span>
                    <Sparkles /> DELNO
                  </span>
                </div>
                <p style={{ margin: 0 }}>Думаю…</p>
              </div>
            )}
          </div>

          {error && <p className="status-error">{error}</p>}

          <form className="onboarding-form chat-form" onSubmit={onSubmit}>
            <div className="onboarding-compose">
              <button
                type="button"
                className="onboarding-attach"
                disabled
                title="Загрузка файлов — в следующем обновлении"
                aria-label="Прикрепить файл (скоро)"
              >
                <Paperclip size={18} />
              </button>
              <textarea
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder="Расскажите о компании, вставьте URL сайта или опишите услуги…"
                disabled={sending || onboardingStatus?.status === "published"}
                rows={3}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    const q = message.trim();
                    if (q && !sending) {
                      setMessage("");
                      void sendText(q);
                    }
                  }
                }}
              />
            </div>
            <button
              type="submit"
              className="btn-primary"
              disabled={sending || !message.trim() || onboardingStatus?.status === "published"}
            >
              {sending ? "…" : "Отправить"}
            </button>
          </form>
        </>
      )}
    </div>
  );
}
