"use client";

import {
  FormEvent,
  PointerEvent as ReactPointerEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { AlertTriangle, Camera, CheckCircle2, Mic, Paperclip, Sparkles, X } from "lucide-react";
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

const QUICK_CHIPS = [
  "Настрой телефон секретаря",
  "Что ещё настроить в офисе?",
  "Проверь здоровье офиса",
  "Какие звонки были сегодня?",
  "Покажи расход токенов и баланс",
];

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
  const mountRef = useRef<HTMLDivElement>(null);
  const threadRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
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

  const addFiles = useCallback(
    (files: FileList | File[]) => {
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
    },
    [],
  );

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
    return () => {
      /* keep stream until closeCamera */
    };
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

  return (
    <div className="operator-stage hermes-stage" ref={mountRef} data-voice-active={voiceActive ? "true" : "false"}>
      <div className="page-head operator-head">
        <small>Hermes · руководитель офиса</small>
        <h1>Hermes</h1>
        <p>
          Настройте офис как клиент DELNO: голосом, текстом, фото или файлом. Можно снять кадр с
          камеры прямо в чате — Hermes читает изображения.
        </p>
      </div>

      <div className="hermes-layout">
        <aside className="hermes-side">
          <section className="hermes-panel">
            <header>
              <span>Сетап офиса</span>
              {setup?.setup_complete ? (
                <CheckCircle2 size={16} className="hermes-ok" />
              ) : (
                <span className="hermes-progress-label">{progressPct}%</span>
              )}
            </header>
            {setup ? (
              <>
                <div className="hermes-progress-bar" aria-hidden>
                  <i style={{ width: `${progressPct}%` }} />
                </div>
                <p className="hermes-panel-msg">{setup.message_ru}</p>
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
              <p className="hermes-panel-msg">Загружаю чеклист…</p>
            )}
          </section>

          <section className="hermes-panel">
            <header>
              <span>Здоровье</span>
              {health && !health.healthy && <AlertTriangle size={16} className="hermes-warn" />}
              {health?.healthy && <CheckCircle2 size={16} className="hermes-ok" />}
            </header>
            {health ? (
              <>
                <p className="hermes-panel-msg">{health.message_ru}</p>
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
              <p className="hermes-panel-msg">Проверяю компоненты…</p>
            )}
          </section>

          <section className="hermes-panel">
            <header>
              <span>Тариф / токены</span>
            </header>
            {billing ? (
              <>
                <p className="hermes-panel-msg">{billing.message_ru}</p>
                <ul className="hermes-calls">
                  <li>
                    <strong>
                      Баланс {billing.balance.token_credits.toFixed(2)} {billing.balance.currency}
                    </strong>
                    <small>
                      выдано {billing.balance.granted_credits.toFixed(2)} · потрачено{" "}
                      {billing.balance.spent_credits.toFixed(2)}
                    </small>
                  </li>
                  <li>
                    <strong>LLM</strong>
                    <small>
                      {String(billing.tariff.llm_input_per_1k)} / {String(billing.tariff.llm_output_per_1k)} за 1k
                      in/out
                    </small>
                  </li>
                </ul>
              </>
            ) : (
              <p className="hermes-panel-msg">Загружаю тариф…</p>
            )}
          </section>

          <section className="hermes-panel">
            <header>
              <span>Каналы</span>
            </header>
            <p className="hermes-panel-msg">
              Два режима: токен бота (Settings) или QR/web-login. Instagram — тот же QR-контур.
            </p>
            <div className="operator-chips">
              <button type="button" disabled={qrBusy} onClick={() => void startQr("telegram")}>
                QR Telegram
              </button>
              <button type="button" disabled={qrBusy} onClick={() => void startQr("max")}>
                QR MAX
              </button>
              <button type="button" disabled={qrBusy} onClick={() => void startQr("instagram")}>
                QR Instagram
              </button>
            </div>
          </section>

          {calls.length > 0 && (
            <section className="hermes-panel">
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
        </aside>

        <div className="hermes-main">
          <div className="hermes-chat-shell">
            <div className="hermes-chat-toolbar">
              <div className="operator-orb-wrap hermes-orb-compact">
                <CrystalOrb voiceActive={voiceActive} voicePhase={voicePhase} onOrbClick={toggleVoice} />
              </div>
              <p className="operator-phase hermes-phase">
                {dictating && "Диктовка в поле… отпустите mic и нажмите Отправить"}
                {!dictating && voicePhase === "listen" && "Слушаю разговор…"}
                {!dictating && voicePhase === "think" && "Думаю…"}
                {!dictating && voicePhase === "speak" && "Отвечаю голосом…"}
                {!dictating && voicePhase === "error" && "Ошибка микрофона"}
                {!dictating && voicePhase === "idle" && (
                  dictateSupported
                    ? "Mic — диктовка. 📎 файл/фото. 📷 камера. Orb — голосовой диалог."
                    : "📎 файл/фото, 📷 камера, или текст. Chrome — для диктовки."
                )}
              </p>
            </div>

            <div className="operator-chips">
              {QUICK_CHIPS.map((chip) => (
                <button key={chip} type="button" disabled={sending} onClick={() => void sendText(chip)}>
                  {chip}
                </button>
              ))}
            </div>

            <div className="operator-thread hermes-thread" ref={threadRef}>
              {lines.length === 0 && (
                <div className="delno-result">
                  <div className="result-head">
                    <span>
                      <Sparkles /> Hermes
                    </span>
                  </div>
                  <p style={{ margin: 0 }}>
                    Прикрепите фото/файл, снимите кадр с камеры или надиктуйте задание — Hermes
                    читает изображения и документы.
                  </p>
                </div>
              )}
              {lines.map((line, idx) =>
                line.role === "user" ? (
                  <div key={idx} className="msg-bubble user">
                    {line.previews && line.previews.length > 0 && (
                      <div className="hermes-msg-previews">
                        {line.previews.map((p) => (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img key={p.url} src={p.url} alt={p.name} />
                        ))}
                      </div>
                    )}
                    <div className="msg-body">{line.text}</div>
                  </div>
                ) : (
                  <div key={idx}>
                    <div className="delno-result">
                      <div className="result-head">
                        <span>
                          <Sparkles /> Hermes
                        </span>
                      </div>
                      <p style={{ margin: 0, whiteSpace: "pre-wrap" }}>{line.text}</p>
                      {line.sources && line.sources.length > 0 && (
                        <ul className="msg-sources">
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
                ),
              )}
            </div>

            {(error || dictateError) && <p className="status-error">{error || dictateError}</p>}

            {pendingFiles.length > 0 && (
              <div className="hermes-attach-strip">
                {pendingFiles.map((item) => (
                  <div key={item.id} className="hermes-attach-chip" data-kind={item.kind}>
                    {item.previewUrl ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={item.previewUrl} alt={item.filename} />
                    ) : (
                      <span className="hermes-attach-file">{item.filename}</span>
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

            <form className="chat-form operator-form hermes-form" onSubmit={onSubmit}>
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
              <button
                type="button"
                className="hermes-mic-btn"
                aria-label="Прикрепить файл или фото"
                title="Файл или фото из галереи"
                disabled={sending}
                onClick={() => fileInputRef.current?.click()}
              >
                <Paperclip size={18} />
              </button>
              <button
                type="button"
                className="hermes-mic-btn"
                aria-label="Снять фото камерой"
                title="Снимок с камеры"
                disabled={sending}
                onClick={() => void openDesktopCamera()}
              >
                <Camera size={18} />
              </button>
              <button
                type="button"
                className={`hermes-mic-btn${dictating ? " active" : ""}`}
                aria-label="Удерживайте для диктовки в поле"
                title="Удерживайте — диктовка в поле ввода"
                disabled={sending}
                onPointerDown={onMicDown}
                onPointerUp={onMicUp}
                onPointerLeave={onMicUp}
                onPointerCancel={onMicUp}
                onContextMenu={(e) => e.preventDefault()}
              >
                <Mic size={18} />
              </button>
              <textarea
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder="Текст, диктовка, фото или файл…"
                disabled={sending}
                rows={dictating || message.length > 80 ? 3 : 2}
              />
              <button
                type="submit"
                className="btn-primary"
                disabled={sending || (!message.trim() && pendingFiles.length === 0)}
              >
                {sending ? "…" : "Отправить"}
              </button>
            </form>
          </div>
        </div>
      </div>

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
