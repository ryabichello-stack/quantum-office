"use client";

import {
  FormEvent,
  PointerEvent as ReactPointerEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import {
  AlertTriangle,
  ArrowUp,
  Camera,
  CheckCircle2,
  Mic,
  PanelRight,
  Paperclip,
  Sparkles,
  X,
} from "lucide-react";
import { CrystalOrb } from "@/components/CrystalOrb";
import { ConfirmCard } from "@/components/ConfirmCard";
import {
  apiOperatorChat,
  apiOperatorConfirm,
  type KnowledgeSource,
  type PendingConfirmation,
} from "@/lib/api";
import {
  apiBillingEnsure,
  apiBillingSummary,
  apiCallsList,
  apiChannelQrStart,
  apiHermesHealth,
  apiHermesSetup,
  type BillingSummary,
  type CallSessionItem,
  type HermesHealthStatus,
  type HermesSetupStatus,
} from "@/lib/hermesApi";
import {
  canAddMore,
  fileToOperatorAttachment,
  makePendingAttachment,
  type PendingHermesAttachment,
} from "@/lib/hermesAttachments";
import { useDictateToInput } from "@/lib/useDictateToInput";
import { useOperatorVoice } from "@/lib/useOperatorVoice";

type ChatLine = {
  role: "user" | "assistant";
  text: string;
  sources?: KnowledgeSource[];
  pending?: PendingConfirmation | null;
  previews?: { url: string; name: string }[];
};

const QUICK_PROMPTS = [
  { title: "Телефон секретаря", text: "Настрой телефон секретаря" },
  { title: "Сетап офиса", text: "Что ещё настроить в офисе?" },
  { title: "Здоровье", text: "Проверь здоровье офиса" },
  { title: "Звонки", text: "Какие звонки были сегодня?" },
  { title: "Баланс", text: "Покажи расход токенов и баланс" },
];

function HermesAvatar() {
  return (
    <span className="hx-avatar" aria-hidden>
      <Sparkles size={14} />
    </span>
  );
}

export function HermesStage({ token }: { token: string }) {
  const [lines, setLines] = useState<ChatLine[]>([]);
  const [message, setMessage] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState("");
  const [activePending, setActivePending] = useState<PendingConfirmation | null>(null);
  const [setup, setSetup] = useState<HermesSetupStatus | null>(null);
  const [health, setHealth] = useState<HermesHealthStatus | null>(null);
  const [calls, setCalls] = useState<CallSessionItem[]>([]);
  const [billing, setBilling] = useState<BillingSummary | null>(null);
  const [bootstrapped, setBootstrapped] = useState(false);
  const [qrBusy, setQrBusy] = useState(false);
  const [pendingFiles, setPendingFiles] = useState<PendingHermesAttachment[]>([]);
  const [cameraOpen, setCameraOpen] = useState(false);
  const [panelOpen, setPanelOpen] = useState(false);
  const mountRef = useRef<HTMLDivElement>(null);
  const threadRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const messageRef = useRef(message);
  messageRef.current = message;
  const pendingRef = useRef(pendingFiles);
  pendingRef.current = pendingFiles;

  const refreshPanels = useCallback(async () => {
    try {
      const [s, h, c, b] = await Promise.all([
        apiHermesSetup(token),
        apiHermesHealth(token),
        apiCallsList(token, 8).catch(() => ({ ok: true, items: [] as CallSessionItem[] })),
        apiBillingEnsure(token).catch(() => apiBillingSummary(token)),
      ]);
      setSetup(s);
      setHealth(h);
      setCalls(c.items || []);
      setBilling(b);
    } catch {
      /* panels are best-effort; chat still works */
    }
  }, [token]);

  async function startQr(channelType: string) {
    if (qrBusy) return;
    setQrBusy(true);
    try {
      const out = await apiChannelQrStart(token, channelType);
      setLines((prev) => [
        ...prev,
        { role: "assistant", text: out.message_ru || `QR-сессия ${channelType}: ${out.account_id}` },
      ]);
    } catch {
      setError("Не удалось стартовать QR-подключение канала.");
    } finally {
      setQrBusy(false);
    }
  }

  useEffect(() => {
    void refreshPanels();
  }, [refreshPanels]);

  const clearPending = useCallback((items: PendingHermesAttachment[]) => {
    for (const item of items) {
      if (item.previewUrl) URL.revokeObjectURL(item.previewUrl);
    }
  }, []);

  const addFiles = useCallback((files: FileList | File[]) => {
    const list = Array.from(files);
    if (!list.length) return;
    setError("");
    setPendingFiles((prev) => {
      const next = [...prev];
      for (const file of list) {
        if (!canAddMore(next.length)) {
          setError("Максимум 4 вложения за раз");
          break;
        }
        const made = makePendingAttachment(file);
        if ("error" in made) {
          setError(made.error);
          continue;
        }
        next.push(made);
      }
      return next;
    });
  }, []);

  const removePending = useCallback((id: string) => {
    setPendingFiles((prev) => {
      const target = prev.find((p) => p.id === id);
      if (target?.previewUrl) URL.revokeObjectURL(target.previewUrl);
      return prev.filter((p) => p.id !== id);
    });
  }, []);

  const sendText = useCallback(
    async (text: string, modality: "text" | "voice" = "text", withPending = false) => {
      const question = text.trim();
      const attachSource = withPending ? pendingRef.current : [];
      if ((!question && attachSource.length === 0) || sending) return null;
      setSending(true);
      setError("");
      setActivePending(null);
      const previews = attachSource
        .filter((a) => a.previewUrl)
        .map((a) => ({ url: a.previewUrl!, name: a.filename }));
      const label =
        question ||
        (attachSource.length
          ? attachSource.map((a) => (a.kind === "image" ? `🖼 ${a.filename}` : `📎 ${a.filename}`)).join(" ")
          : "");
      if (modality === "text") {
        setLines((prev) => [...prev, { role: "user", text: label, previews }]);
      }
      try {
        const attachments = await Promise.all(attachSource.map((a) => fileToOperatorAttachment(a.file)));
        if (withPending) {
          clearPending(attachSource);
          setPendingFiles([]);
        }
        const result = await apiOperatorChat(
          token,
          question,
          conversationId || undefined,
          modality,
          "hermes",
          attachments,
        );
        setConversationId(result.conversation_id);
        const pending = result.pending_confirmation || null;
        if (pending) setActivePending(pending);
        setLines((prev) => {
          const base =
            modality === "voice" && (prev.length === 0 || prev[prev.length - 1]?.text !== question)
              ? [...prev, { role: "user" as const, text: question || label }]
              : prev;
          return [
            ...base,
            {
              role: "assistant" as const,
              text: result.reply,
              sources: result.sources || [],
              pending,
            },
          ];
        });
        void refreshPanels();
        return result.reply;
      } catch {
        setError("Hermes недоступен. Проверьте API и соединение.");
        return null;
      } finally {
        setSending(false);
      }
    },
    [token, conversationId, sending, refreshPanels, clearPending],
  );

  const { voiceActive, voicePhase, toggleVoice, audioRef } = useOperatorVoice(
    useCallback((text) => sendText(text, "voice").then((r) => r || ""), [sendText]),
    token,
  );

  const {
    dictating,
    supported: dictateSupported,
    error: dictateError,
    start: startDictate,
    stop: stopDictate,
  } = useDictateToInput(
    useCallback((text) => {
      setMessage(text);
    }, []),
  );

  useEffect(() => {
    if (bootstrapped || !setup) return;
    setBootstrapped(true);
    if (!setup.setup_complete) {
      void sendText(
        "Я владелец офиса. Покажи статус сетапа и скажи, что сделать следующим шагом.",
        "text",
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- one-shot welcome
  }, [setup, bootstrapped]);

  useEffect(() => {
    const el = threadRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [lines, sending]);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "0px";
    el.style.height = `${Math.min(160, Math.max(24, el.scrollHeight))}px`;
  }, [message]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    stopDictate();
    const q = message.trim();
    if (!q && pendingFiles.length === 0) return;
    setMessage("");
    await sendText(q, "text", true);
  }

  function onPickFiles(e: React.ChangeEvent<HTMLInputElement>) {
    const files = e.target.files;
    if (files?.length) addFiles(files);
    e.target.value = "";
  }

  async function openDesktopCamera() {
    setError("");
    if (!navigator.mediaDevices?.getUserMedia) {
      cameraInputRef.current?.click();
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" } },
        audio: false,
      });
      streamRef.current = stream;
      setCameraOpen(true);
    } catch {
      cameraInputRef.current?.click();
    }
  }

  useEffect(() => {
    if (!cameraOpen) return;
    const video = videoRef.current;
    if (video && streamRef.current) {
      video.srcObject = streamRef.current;
      void video.play().catch(() => undefined);
    }
  }, [cameraOpen]);

  function closeCamera() {
    setCameraOpen(false);
    if (streamRef.current) {
      for (const track of streamRef.current.getTracks()) track.stop();
      streamRef.current = null;
    }
  }

  async function captureCameraShot() {
    const video = videoRef.current;
    if (!video) return;
    const w = video.videoWidth || 1280;
    const h = video.videoHeight || 720;
    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.drawImage(video, 0, 0, w, h);
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.9));
    closeCamera();
    if (!blob) {
      setError("Не удалось сделать снимок");
      return;
    }
    const file = new File([blob], `camera-${Date.now()}.jpg`, { type: "image/jpeg" });
    addFiles([file]);
  }

  useEffect(() => {
    return () => {
      clearPending(pendingRef.current);
      if (streamRef.current) {
        for (const track of streamRef.current.getTracks()) track.stop();
      }
    };
  }, [clearPending]);

  async function onConfirm() {
    if (!activePending || confirming) return;
    setConfirming(true);
    setError("");
    try {
      const result = await apiOperatorConfirm(token, activePending.tool_name, activePending.params);
      setActivePending(null);
      setLines((prev) => [
        ...prev,
        {
          role: "assistant",
          text: result.ok
            ? result.message || "Изменения применены."
            : result.message || "Не удалось применить изменения.",
        },
      ]);
      void refreshPanels();
    } catch {
      setError("Не удалось подтвердить действие.");
    } finally {
      setConfirming(false);
    }
  }

  function onMicDown(e: ReactPointerEvent<HTMLButtonElement>) {
    e.preventDefault();
    startDictate(messageRef.current);
  }

  function onMicUp() {
    stopDictate();
  }

  const progressPct = setup
    ? Math.round((100 * setup.progress.required_done) / Math.max(1, setup.progress.required_total))
    : 0;

  const statusHint = dictating
    ? "Диктовка… отпустите mic"
    : voicePhase === "listen"
      ? "Слушаю…"
      : voicePhase === "think"
        ? "Думаю…"
        : voicePhase === "speak"
          ? "Отвечаю голосом…"
          : voicePhase === "error"
            ? "Ошибка микрофона"
            : sending
              ? "Hermes печатает…"
              : dictateSupported
                ? "Напишите, приложите фото или удержите mic"
                : "Напишите, приложите фото или файл";

  const canSend = !sending && (Boolean(message.trim()) || pendingFiles.length > 0);

  return (
    <div
      className="operator-stage hermes-stage hx-app"
      ref={mountRef}
      data-voice-active={voiceActive ? "true" : "false"}
      data-panel={panelOpen ? "open" : "closed"}
    >
      <header className="hx-topbar">
        <div className="hx-brand">
          <HermesAvatar />
          <div>
            <strong>Hermes</strong>
            <small>{statusHint}</small>
          </div>
        </div>
        <div className="hx-top-actions">
          <button
            type="button"
            className={`hx-icon-btn${voiceActive ? " is-live" : ""}`}
            title="Голосовой диалог"
            aria-label="Голосовой диалог"
            onClick={toggleVoice}
          >
            <Mic size={18} />
          </button>
          <div className="hx-orb-mini" aria-hidden>
            <CrystalOrb voiceActive={voiceActive} voicePhase={voicePhase} onOrbClick={toggleVoice} />
          </div>
          <button
            type="button"
            className={`hx-icon-btn${panelOpen ? " is-on" : ""}`}
            title="Офис: сетап и здоровье"
            aria-label="Панель офиса"
            onClick={() => setPanelOpen((v) => !v)}
          >
            <PanelRight size={18} />
            {!setup?.setup_complete && <i className="hx-dot" />}
            {health && !health.healthy && <i className="hx-dot warn" />}
          </button>
        </div>
      </header>

      <div className="hx-body">
        <main className="hx-chat">
          <div className="hx-thread" ref={threadRef}>
            {lines.length === 0 && !sending && (
              <div className="hx-empty">
                <p className="hx-empty-kicker">DELNO · office agent</p>
                <h1 className="hx-empty-title">Hermes</h1>
                <p className="hx-empty-lead">
                  Как в Cursor или ChatGPT: пишите задачу, кидайте фото, снимайте камерой — Hermes
                  отвечает в этом же потоке.
                </p>
                <div className="hx-suggestions">
                  {QUICK_PROMPTS.map((item) => (
                    <button
                      key={item.title}
                      type="button"
                      disabled={sending}
                      onClick={() => void sendText(item.text)}
                    >
                      <strong>{item.title}</strong>
                      <span>{item.text}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {lines.map((line, idx) =>
              line.role === "user" ? (
                <article key={idx} className="hx-row hx-row-user">
                  <div className="hx-bubble hx-bubble-user">
                    {line.previews && line.previews.length > 0 && (
                      <div className="hx-previews">
                        {line.previews.map((p) => (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img key={p.url} src={p.url} alt={p.name} />
                        ))}
                      </div>
                    )}
                    <div className="hx-text">{line.text}</div>
                  </div>
                </article>
              ) : (
                <article key={idx} className="hx-row hx-row-assistant">
                  <HermesAvatar />
                  <div className="hx-assistant-col">
                    <div className="hx-bubble hx-bubble-assistant">
                      <div className="hx-text">{line.text}</div>
                      {line.sources && line.sources.length > 0 && (
                        <ul className="hx-sources">
                          {line.sources.map((s, i) => (
                            <li key={i}>{s.title || s.citation || s.document_id}</li>
                          ))}
                        </ul>
                      )}
                    </div>
                    {line.pending && activePending?.confirmation_id === line.pending.confirmation_id && (
                      <ConfirmCard
                        summary={line.pending.summary}
                        toolName={line.pending.tool_name}
                        busy={confirming}
                        onConfirm={() => void onConfirm()}
                        onCancel={() => setActivePending(null)}
                      />
                    )}
                  </div>
                </article>
              ),
            )}

            {sending && (
              <article className="hx-row hx-row-assistant">
                <HermesAvatar />
                <div className="hx-bubble hx-bubble-assistant hx-typing" aria-label="Печатает">
                  <span />
                  <span />
                  <span />
                </div>
              </article>
            )}
          </div>

          <div className="hx-composer-wrap">
            {(error || dictateError) && <p className="hx-error">{error || dictateError}</p>}

            {pendingFiles.length > 0 && (
              <div className="hx-attach-strip">
                {pendingFiles.map((item) => (
                  <div key={item.id} className="hx-attach-chip" data-kind={item.kind}>
                    {item.previewUrl ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={item.previewUrl} alt={item.filename} />
                    ) : (
                      <span>{item.filename}</span>
                    )}
                    <button
                      type="button"
                      aria-label="Убрать вложение"
                      onClick={() => removePending(item.id)}
                      disabled={sending}
                    >
                      <X size={14} />
                    </button>
                  </div>
                ))}
              </div>
            )}

            <form className="hx-composer" onSubmit={onSubmit}>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*,.pdf,.docx,.xlsx,.csv,.txt,.md,.html,.json"
                multiple
                hidden
                onChange={onPickFiles}
              />
              <input
                ref={cameraInputRef}
                type="file"
                accept="image/*"
                capture="environment"
                hidden
                onChange={onPickFiles}
              />
              <div className="hx-composer-tools">
                <button
                  type="button"
                  aria-label="Прикрепить"
                  title="Файл или фото"
                  disabled={sending}
                  onClick={() => fileInputRef.current?.click()}
                >
                  <Paperclip size={18} />
                </button>
                <button
                  type="button"
                  aria-label="Камера"
                  title="Снимок"
                  disabled={sending}
                  onClick={() => void openDesktopCamera()}
                >
                  <Camera size={18} />
                </button>
                <button
                  type="button"
                  className={dictating ? "is-live" : undefined}
                  aria-label="Диктовка"
                  title="Удерживайте для диктовки"
                  disabled={sending}
                  onPointerDown={onMicDown}
                  onPointerUp={onMicUp}
                  onPointerLeave={onMicUp}
                  onPointerCancel={onMicUp}
                  onContextMenu={(e) => e.preventDefault()}
                >
                  <Mic size={18} />
                </button>
              </div>
              <textarea
                ref={textareaRef}
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder="Сообщение Hermes…"
                disabled={sending}
                rows={1}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    if (canSend) {
                      stopDictate();
                      const q = message.trim();
                      setMessage("");
                      void sendText(q, "text", true);
                    }
                  }
                }}
              />
              <button type="submit" className="hx-send" disabled={!canSend} aria-label="Отправить">
                <ArrowUp size={18} strokeWidth={2.4} />
              </button>
            </form>
            <p className="hx-footnote">Enter — отправить · Shift+Enter — новая строка</p>
          </div>
        </main>

        <aside className="hx-panel" aria-hidden={!panelOpen}>
          <div className="hx-panel-inner">
            <header className="hx-panel-head">
              <strong>Офис</strong>
              <button type="button" className="hx-icon-btn" aria-label="Закрыть" onClick={() => setPanelOpen(false)}>
                <X size={16} />
              </button>
            </header>

            <section className="hx-card">
              <header>
                <span>Сетап</span>
                {setup?.setup_complete ? (
                  <CheckCircle2 size={15} className="hermes-ok" />
                ) : (
                  <span className="hx-pct">{progressPct}%</span>
                )}
              </header>
              {setup ? (
                <>
                  <div className="hermes-progress-bar" aria-hidden>
                    <i style={{ width: `${progressPct}%` }} />
                  </div>
                  <p>{setup.message_ru}</p>
                  <ul className="hermes-checklist">
                    {setup.steps.map((step) => {
                      const check = setup.checks[step.id];
                      const done = Boolean(check?.ok);
                      const optional = Boolean(check?.optional);
                      return (
                        <li key={step.id} data-done={done ? "1" : "0"} data-optional={optional ? "1" : "0"}>
                          <span className="hermes-check-dot" />
                          <div>
                            <strong>
                              {step.title}
                              {optional ? " · опц." : ""}
                            </strong>
                            <small>{done ? check?.detail || "готово" : step.hint}</small>
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                </>
              ) : (
                <p>Загружаю…</p>
              )}
            </section>

            <section className="hx-card">
              <header>
                <span>Здоровье</span>
                {health && !health.healthy && <AlertTriangle size={15} className="hermes-warn" />}
                {health?.healthy && <CheckCircle2 size={15} className="hermes-ok" />}
              </header>
              {health ? (
                <>
                  <p>{health.message_ru}</p>
                  {health.alerts.length > 0 && (
                    <ul className="hermes-alerts">
                      {health.alerts.slice(0, 5).map((a) => (
                        <li key={a.code} data-sev={a.severity}>
                          <strong>{a.message_ru}</strong>
                          {a.fix ? <small>{a.fix}</small> : null}
                        </li>
                      ))}
                    </ul>
                  )}
                </>
              ) : (
                <p>Проверяю…</p>
              )}
            </section>

            <section className="hx-card">
              <header>
                <span>Тариф</span>
              </header>
              {billing ? (
                <>
                  <p>{billing.message_ru}</p>
                  <ul className="hermes-calls">
                    <li>
                      <strong>
                        {billing.balance.token_credits.toFixed(2)} {billing.balance.currency}
                      </strong>
                      <small>
                        выдано {billing.balance.granted_credits.toFixed(2)} · потрачено{" "}
                        {billing.balance.spent_credits.toFixed(2)}
                      </small>
                    </li>
                  </ul>
                </>
              ) : (
                <p>Загружаю…</p>
              )}
            </section>

            <section className="hx-card">
              <header>
                <span>Каналы</span>
              </header>
              <p>Токен бота или QR. Instagram — тот же контур.</p>
              <div className="hx-channel-row">
                <button type="button" disabled={qrBusy} onClick={() => void startQr("telegram")}>
                  QR TG
                </button>
                <button type="button" disabled={qrBusy} onClick={() => void startQr("max")}>
                  QR MAX
                </button>
                <button type="button" disabled={qrBusy} onClick={() => void startQr("instagram")}>
                  QR IG
                </button>
              </div>
            </section>

            {calls.length > 0 && (
              <section className="hx-card">
                <header>
                  <span>Звонки</span>
                </header>
                <ul className="hermes-calls">
                  {calls.map((c) => (
                    <li key={c.id}>
                      <strong>
                        {c.direction} · {c.state}
                      </strong>
                      <small>
                        {(c.from_e164 || "—") + " → " + (c.to_e164 || "—")}
                      </small>
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </div>
        </aside>
      </div>

      {panelOpen && <button type="button" className="hx-backdrop" aria-label="Закрыть панель" onClick={() => setPanelOpen(false)} />}

      {cameraOpen && (
        <div className="hermes-camera-modal" role="dialog" aria-label="Камера">
          <div className="hermes-camera-card">
            <video ref={videoRef} playsInline muted autoPlay />
            <div className="hermes-camera-actions">
              <button type="button" className="btn-ghost" onClick={closeCamera}>
                Отмена
              </button>
              <button type="button" className="btn-primary" onClick={() => void captureCameraShot()}>
                Снять
              </button>
            </div>
          </div>
        </div>
      )}

      <audio ref={audioRef} className="operator-audio" preload="none" playsInline />
    </div>
  );
}
