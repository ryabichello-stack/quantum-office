"use client";

import { FormEvent, useCallback, useRef, useState } from "react";
import { Sparkles } from "lucide-react";
import { CrystalOrb } from "@/components/CrystalOrb";
import { ConfirmCard } from "@/components/ConfirmCard";
import {
  apiOperatorChat,
  apiOperatorConfirm,
  type KnowledgeSource,
  type PendingConfirmation,
} from "@/lib/api";
import { useOperatorVoice } from "@/lib/useOperatorVoice";

type ChatLine = {
  role: "user" | "assistant";
  text: string;
  sources?: KnowledgeSource[];
  pending?: PendingConfirmation | null;
};

const QUICK_CHIPS = [
  "Покажи текущие настройки",
  "Добавь в базу знаний: Часы работы — суббота 10:00–16:00",
  "Включи голос на сайте",
];

export function OperatorStage({ token }: { token: string }) {
  const [lines, setLines] = useState<ChatLine[]>([]);
  const [message, setMessage] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState("");
  const [activePending, setActivePending] = useState<PendingConfirmation | null>(null);
  const mountRef = useRef<HTMLDivElement>(null);

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
        const result = await apiOperatorChat(token, question, conversationId || undefined, modality);
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
        return result.reply;
      } catch {
        setError("Operator недоступен. Проверьте API и базу знаний.");
        return null;
      } finally {
        setSending(false);
      }
    },
    [token, conversationId, sending],
  );

  const { voiceActive, voicePhase, toggleVoice, audioRef } = useOperatorVoice(
    useCallback((text) => sendText(text, "voice").then((r) => r || ""), [sendText]),
    token,
  );

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
    } catch {
      setError("Не удалось подтвердить действие.");
    } finally {
      setConfirming(false);
    }
  }

  return (
    <div className="operator-stage" ref={mountRef} data-voice-active={voiceActive ? "true" : "false"}>
      <div className="page-head operator-head">
        <small>Operator · настройка на лету</small>
        <h1>Operator</h1>
        <p>Голос или текст — база знаний, часы, каналы. Изменения после подтверждения.</p>
      </div>

      <div className="operator-orb-wrap">
        <CrystalOrb voiceActive={voiceActive} voicePhase={voicePhase} onOrbClick={toggleVoice} />
        <p className="operator-phase">
          {voicePhase === "listen" && "Слушаю…"}
          {voicePhase === "think" && "Думаю…"}
          {voicePhase === "speak" && "Отвечаю…"}
          {voicePhase === "error" && "Ошибка микрофона"}
          {voicePhase === "idle" && "Нажмите на orb — говорите с DELNO"}
        </p>
      </div>

      <div className="operator-chips">
        {QUICK_CHIPS.map((chip) => (
          <button key={chip} type="button" disabled={sending} onClick={() => void sendText(chip)}>
            {chip.length > 42 ? `${chip.slice(0, 42)}…` : chip}
          </button>
        ))}
      </div>

      {lines.length === 0 && (
        <div className="delno-result">
          <div className="result-head">
            <span>
              <Sparkles /> DELNO
            </span>
          </div>
          <p style={{ margin: 0 }}>
            Спросите про услуги или скажите «добавь в базу знаний…», «включи голос», «покажи настройки».
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

      <form className="chat-form operator-form" onSubmit={onSubmit}>
        <input
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Ваш вопрос или команда настройки…"
          disabled={sending}
        />
        <button type="submit" className="btn-primary" disabled={sending}>
          {sending ? "…" : "Отправить"}
        </button>
      </form>

      <audio ref={audioRef} className="operator-audio" preload="none" playsInline />
    </div>
  );
}
