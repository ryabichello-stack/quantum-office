"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { FileText, Paperclip, Sparkles } from "lucide-react";
import {
  apiConversationMessages,
  apiOnboardingStart,
  apiOnboardingStatus,
  apiOnboardingUpload,
  apiOnboardingUploads,
  apiOperatorChat,
  type MessageItem,
  type OnboardingStatus,
  type OnboardingUploadItem,
} from "@/lib/api";

type ChatLine = {
  id?: string;
  role: "user" | "assistant";
  text: string;
};

const ACCEPT =
  ".pdf,.docx,.xlsx,.csv,.txt,.md,.html,.htm,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv,text/plain";

function mapMessages(items: MessageItem[]): ChatLine[] {
  return items
    .filter((m) => m.role === "user" || m.role === "assistant")
    .map((m) => ({
      id: m.id,
      role: m.role as "user" | "assistant",
      text: m.body,
    }));
}

function uploadStatusLabel(status: string) {
  if (status === "parsed") return "Обработан";
  if (status === "pending") return "Загружен";
  if (status === "empty") return "Мало текста";
  return "Ошибка";
}

export function OnboardingChat({ token }: { token: string }) {
  const [lines, setLines] = useState<ChatLine[]>([]);
  const [uploads, setUploads] = useState<OnboardingUploadItem[]>([]);
  const [message, setMessage] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [onboardingStatus, setOnboardingStatus] = useState<OnboardingStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const threadRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const scrollToBottom = useCallback(() => {
    const el = threadRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, []);

  const refreshUploads = useCallback(
    async (convId: string) => {
      try {
        const result = await apiOnboardingUploads(token, convId);
        setUploads(result.items);
      } catch {
        /* optional */
      }
    },
    [token],
  );

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
        const [history, uploadList] = await Promise.all([
          apiConversationMessages(token, start.conversation_id),
          apiOnboardingUploads(token, start.conversation_id),
        ]);
        if (cancelled) return;
        const mapped = mapMessages(history.items);
        setLines(mapped.length > 0 ? mapped : [{ role: "assistant", text: start.reply }]);
        setUploads(uploadList.items);
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
      if (!question || sending || uploading || !conversationId) return;
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
    [token, conversationId, sending, uploading],
  );

  const uploadFile = useCallback(
    async (file: File) => {
      if (!conversationId || uploading || sending) return;
      setUploading(true);
      setError("");
      try {
        const result = await apiOnboardingUpload(token, file, conversationId);
        if (!result.ok) {
          setError(result.reply || "Не удалось загрузить файл.");
          if (result.reply) {
            setLines((prev) => [
              ...prev,
              { role: "user", text: `📎 ${file.name}` },
              { role: "assistant", text: result.reply || "Не удалось обработать файл." },
            ]);
          }
          return;
        }
        const history = await apiConversationMessages(token, conversationId);
        setLines(mapMessages(history.items));
        await refreshUploads(conversationId);
        const status = await apiOnboardingStatus(token);
        setOnboardingStatus(status);
      } catch {
        setError("Не удалось загрузить файл. Проверьте формат (PDF, DOCX, XLSX, CSV, TXT).");
      } finally {
        setUploading(false);
        if (fileInputRef.current) fileInputRef.current.value = "";
      }
    },
    [token, conversationId, uploading, sending, refreshUploads],
  );

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const q = message.trim();
    if (!q) return;
    setMessage("");
    await sendText(q);
  }

  function onPickFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) void uploadFile(file);
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (file) void uploadFile(file);
  }

  const busy = sending || uploading;
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
          {uploads.length > 0 && (
            <div className="onboarding-files">
              {uploads.map((item) => (
                <div key={item.upload_id} className={`onboarding-file-chip status-${item.parse_status}`}>
                  <FileText size={16} />
                  <span className="onboarding-file-name">{item.file_name}</span>
                  <span className="onboarding-file-status">{uploadStatusLabel(item.parse_status)}</span>
                </div>
              ))}
            </div>
          )}

          <div
            className="onboarding-thread operator-thread"
            ref={threadRef}
            onDragOver={(e) => e.preventDefault()}
            onDrop={onDrop}
          >
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
            {busy && (
              <div className="delno-result onboarding-typing">
                <div className="result-head">
                  <span>
                    <Sparkles /> DELNO
                  </span>
                </div>
                <p style={{ margin: 0 }}>{uploading ? "Читаю файл…" : "Думаю…"}</p>
              </div>
            )}
          </div>

          {error && <p className="status-error">{error}</p>}

          <form className="onboarding-form chat-form" onSubmit={onSubmit}>
            <input
              ref={fileInputRef}
              type="file"
              accept={ACCEPT}
              className="onboarding-file-input"
              onChange={onPickFile}
            />
            <div className="onboarding-compose">
              <button
                type="button"
                className="onboarding-attach"
                disabled={busy || onboardingStatus?.status === "published"}
                title="Загрузить PDF, DOCX, XLSX, CSV, TXT"
                aria-label="Прикрепить файл"
                onClick={() => fileInputRef.current?.click()}
              >
                <Paperclip size={18} />
              </button>
              <textarea
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder="Расскажите о компании, вставьте URL сайта или перетащите файл…"
                disabled={busy || onboardingStatus?.status === "published"}
                rows={3}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    const q = message.trim();
                    if (q && !busy) {
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
              disabled={busy || !message.trim() || onboardingStatus?.status === "published"}
            >
              {busy ? "…" : "Отправить"}
            </button>
          </form>
        </>
      )}
    </div>
  );
}
