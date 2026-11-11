"use client";

import {
  FormEvent,
  PointerEvent as ReactPointerEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { AlertTriangle, CheckCircle2, Mic, Sparkles } from "lucide-react";
import { CrystalOrb } from "@/components/CrystalOrb";
import { ConfirmCard } from "@/components/ConfirmCard";
import {
  apiOperatorChat,
  apiOperatorConfirm,
  type KnowledgeSource,
  type PendingConfirmation,
} from "@/lib/api";
import {
  apiCallsList,
  apiHermesHealth,
  apiHermesSetup,
  type CallSessionItem,
  type HermesHealthStatus,
  type HermesSetupStatus,
} from "@/lib/hermesApi";
import { useOperatorVoice } from "@/lib/useOperatorVoice";

type ChatLine = {
  role: "user" | "assistant";
  text: string;
  sources?: KnowledgeSource[];
  pending?: PendingConfirmation | null;
};

const QUICK_CHIPS = [
  "Что ещё настроить в офисе?",
  "Проверь здоровье офиса",
  "Какие звонки были сегодня?",
  "Покажи текущие настройки",
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
  const [holdingMic, setHoldingMic] = useState(false);
  const [bootstrapped, setBootstrapped] = useState(false);
  const mountRef = useRef<HTMLDivElement>(null);

  const refreshPanels = useCallback(async () => {
    try {
      const [s, h, c] = await Promise.all([
        apiHermesSetup(token),
        apiHermesHealth(token),
        apiCallsList(token, 8).catch(() => ({ ok: true, items: [] as CallSessionItem[] })),
      ]);
      setSetup(s);
      setHealth(h);
      setCalls(c.items || []);
    } catch {
      /* panels are best-effort; chat still works */
    }
  }, [token]);

  useEffect(() => {
    void refreshPanels();
  }, [refreshPanels]);

  const sendText = useCallback(
    async (text: string, modality: "text" | "voice" = "text") => {
      const question = text.trim();
      if (!question || sending) return null;
      setSending(true);
      setError("");
      setActivePending(null);
      if (modality === "text") {
        setLines((prev) => [...prev, { role: "user", text: question }]);
      }
      try {
        const result = await apiOperatorChat(
          token,
          question,
          conversationId || undefined,
          modality,
          "hermes",
        );
        setConversationId(result.conversation_id);
        const pending = result.pending_confirmation || null;
        if (pending) setActivePending(pending);
        setLines((prev) => {
          const base =
            modality === "voice" && (prev.length === 0 || prev[prev.length - 1]?.text !== question)
              ? [...prev, { role: "user" as const, text: question }]
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
    [token, conversationId, sending, refreshPanels],
  );

  const { voiceActive, voicePhase, toggleVoice, startHoldVoice, endHoldVoice, audioRef } =
    useOperatorVoice(
      useCallback((text) => sendText(text, "voice").then((r) => r || ""), [sendText]),
      token,
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

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const q = message.trim();
    if (!q) return;
    setMessage("");
    await sendText(q, "text");
  }

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
    setHoldingMic(true);
    startHoldVoice();
  }

  function onMicUp() {
    if (!holdingMic) return;
    setHoldingMic(false);
    endHoldVoice();
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
          Настройте офис как клиент DELNO: голосом или текстом. Hermes сам ведёт сетап, следит за
          здоровьем компонентов и ставит задания на звонки и каналы.
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
          <div className="operator-orb-wrap">
            <CrystalOrb voiceActive={voiceActive} voicePhase={voicePhase} onOrbClick={toggleVoice} />
            <p className="operator-phase">
              {voicePhase === "listen" && (holdingMic ? "Держите — слушаю задание…" : "Слушаю…")}
              {voicePhase === "think" && "Думаю…"}
              {voicePhase === "speak" && "Отвечаю…"}
              {voicePhase === "error" && "Ошибка микрофона"}
              {voicePhase === "idle" && "Нажмите orb или удерживайте mic — говорите задание Hermes"}
            </p>
          </div>

          <div className="operator-chips">
            {QUICK_CHIPS.map((chip) => (
              <button key={chip} type="button" disabled={sending} onClick={() => void sendText(chip)}>
                {chip}
              </button>
            ))}
          </div>

          {lines.length === 0 && (
            <div className="delno-result">
              <div className="result-head">
                <span>
                  <Sparkles /> Hermes
                </span>
              </div>
              <p style={{ margin: 0 }}>
                Скажите голосом: «привяжи номер», «проверь здоровье», «перезвони клиенту…» — как в
                чате с ассистентом.
              </p>
            </div>
          )}

          <div className="operator-thread">
            {lines.map((line, idx) =>
              line.role === "user" ? (
                <div key={idx} className="msg-bubble user">
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
                    <p style={{ margin: 0 }}>{line.text}</p>
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

          {error && <p className="status-error">{error}</p>}

          <form className="chat-form operator-form hermes-form" onSubmit={onSubmit}>
            <button
              type="button"
              className={`hermes-mic-btn${holdingMic || voiceActive ? " active" : ""}`}
              aria-label="Удерживайте для голосового задания"
              title="Удерживайте — говорите задание"
              disabled={sending}
              onPointerDown={onMicDown}
              onPointerUp={onMicUp}
              onPointerLeave={onMicUp}
              onPointerCancel={onMicUp}
              onContextMenu={(e) => e.preventDefault()}
            >
              <Mic size={18} />
            </button>
            <input
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="Задание Hermes текстом или удерживайте mic…"
              disabled={sending}
            />
            <button type="submit" className="btn-primary" disabled={sending}>
              {sending ? "…" : "Отправить"}
            </button>
          </form>
        </div>
      </div>

      <audio ref={audioRef} className="operator-audio" preload="none" playsInline />
    </div>
  );
}
