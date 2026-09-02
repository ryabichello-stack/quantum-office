"use client";

import { CrystalOrb } from "@/components/widget/CrystalOrb";
import "@/components/widget/crystal-widget.css";
import { useCrystalContrast } from "@/components/widget/useCrystalWidget";
import { useDelnoVoice } from "@/hooks/useDelnoVoice";
import { askDelnoWidget } from "@/lib/widgetApi";
import { Sparkles, Volume2 } from "lucide-react";
import { useCallback, useRef, useState } from "react";

const prompts = ["Сколько стоит?", "Как подключить номер?", "Что умеет DELNO?"];

export default function VoiceDemo() {
  const mountRef = useRef<HTMLDivElement>(null);
  const [question, setQuestion] = useState("Нажмите на кристалл и задайте вопрос");
  const [answer, setAnswer] = useState("Я отвечу по базе знаний DELNO — о тарифах, подключении и возможностях.");
  const [promptBusy, setPromptBusy] = useState(false);

  const handleTranscript = useCallback(async (text: string) => {
    const { answer: reply, error } = await askDelnoWidget(text);
    if (error || !reply) {
      throw new Error(error || "empty");
    }
    return reply;
  }, []);

  const handleExchange = useCallback((userText: string, assistantText: string) => {
    setQuestion(userText);
    setAnswer(assistantText);
    setPromptBusy(false);
  }, []);

  const { voicePhase, voiceActive, toggleVoice, stopVoice, askText, audioRef } = useDelnoVoice({
    mountRef,
    onTranscript: handleTranscript,
    onExchange: handleExchange,
  });
  useCrystalContrast(mountRef, { fixed: "dark" });

  async function handlePrompt(text: string) {
    if (promptBusy) return;
    setPromptBusy(true);
    setQuestion(text);
    setAnswer("Думаю…");
    stopVoice();
    try {
      await askText(text, { resumeListen: false });
    } catch {
      setAnswer("Сейчас не удалось получить ответ. Попробуйте ещё раз.");
    } finally {
      setPromptBusy(false);
    }
  }

  const label = voiceActive
    ? voicePhase === "listen"
      ? "Слушаю…"
      : voicePhase === "think"
        ? "Думаю…"
        : voicePhase === "speak"
          ? "Отвечаю…"
          : voicePhase === "error"
            ? "Попробуйте ещё раз"
            : "Слушаю…"
    : promptBusy
      ? "Думаю…"
      : "Спросить вслух";

  return (
    <section className="voice-demo-section" id="demo">
      <div className="voice-demo-copy">
        <div className="v2-kicker pale">Попробуйте сейчас</div>
        <h2>
          Спросите
          <br />
          DELNO вслух.
        </h2>
        <p>
          Такого голосового помощника можно разместить на вашем сайте. Клиент нажимает, задаёт вопрос и сразу
          получает ответ по вашей базе знаний.
        </p>
        <div className="demo-badges">
          <span>
            <Sparkles /> ИИ-ответ
          </span>
          <span>
            <Volume2 /> Голос как на звонке
          </span>
        </div>
      </div>

      <div className="voice-orb-stage">
        <div className="delno-crystal-mount delno-crystal-demo" ref={mountRef} data-contrast="dark">
          <CrystalOrb
            variant="demo"
            voiceActive={voiceActive}
            voicePhase={voicePhase}
            onOrbClick={toggleVoice}
          />
        </div>
        <b className="voice-demo-status" aria-live="polite" data-phase={voicePhase}>
          {label}
        </b>
        <small>Нажмите на кристалл, чтобы говорить. После ответа DELNO снова слушает. Ещё раз — чтобы остановить.</small>
      </div>

      <div className="voice-demo-dialog">
        <div className="demo-dialog-head">
          <span>
            <i /> DELNO
          </span>
          <Volume2 />
        </div>
        <div className="demo-message user">
          <small>Вы</small>
          <p>{question}</p>
        </div>
        <div className="demo-message delno">
          <small>DELNO</small>
          <p>{answer}</p>
        </div>
        <div className="demo-prompts">
          {prompts.map((prompt) => (
            <button
              key={prompt}
              type="button"
              disabled={promptBusy}
              onClick={() => handlePrompt(prompt)}
            >
              {prompt}
            </button>
          ))}
        </div>
        <p className="demo-disclaimer">Ответы из базы знаний DELNO. Голос — cedar, как в телефонии.</p>
      </div>

      <audio ref={audioRef} className="voice-audio" preload="none" playsInline />
    </section>
  );
}
