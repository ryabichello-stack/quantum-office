"use client";

import { CrystalOrb } from "@/components/widget/CrystalOrb";
import "@/components/widget/crystal-widget.css";
import { useCrystalContrast } from "@/components/widget/useCrystalWidget";
import { useDelnoVoice } from "@/hooks/useDelnoVoice";
import { askDelnoWidget } from "@/lib/widgetApi";
import { Mic, Phone, Sparkles, Volume2 } from "lucide-react";
import { useCallback, useRef, useState } from "react";

const prompts = ["Сколько стоит?", "Как подключить номер?", "Что умеет DELNO?"];

export default function VoiceDemo({
  embed = false,
  variant = "default",
}: {
  embed?: boolean;
  variant?: "default" | "v15" | "v17";
}) {
  const isV15 = variant === "v15" || variant === "v17";
  const mountRef = useRef<HTMLDivElement>(null);
  const [question, setQuestion] = useState(
    isV15 ? "Выберите вопрос для демонстрации" : "Нажмите на кристалл и задайте вопрос",
  );
  const [answer, setAnswer] = useState(
    isV15
      ? "Расскажу о возможностях, тарифах и подключении. Можно выбрать вопрос или задать его голосом."
      : "Я отвечу по базе знаний DELNO — о тарифах, подключении и возможностях.",
  );
  const [promptBusy, setPromptBusy] = useState(false);

  const handleTranscript = useCallback(async (text: string) => {
    const { answer: reply, error } = await askDelnoWidget(text);
    if (error || !reply) {
      throw new Error(error || "empty");
    }
    return reply;
  }, []);

  const handleExchange = useCallback((userText: string, assistantText: string) => {
    if (userText) setQuestion(userText);
    setAnswer(assistantText);
    setPromptBusy(false);
  }, []);

  const handlePartial = useCallback((text: string) => {
    if (text) {
      setQuestion(text);
    } else {
      setQuestion("Говорите…");
      setAnswer("DELNO слушает ваш вопрос.");
    }
  }, []);

  const { voicePhase, voiceActive, toggleVoice, stopVoice, askText, audioRef } = useDelnoVoice({
    mountRef,
    onTranscript: handleTranscript,
    onExchange: handleExchange,
    onPartial: handlePartial,
  });
  useCrystalContrast(mountRef, { fixed: isV15 ? "light" : "dark" });

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

  const orbStageClass = [
    "voice-orb-stage",
    voiceActive ? "voice-live" : "",
    voiceActive ? `voice-${voicePhase}` : "",
    !isV15 && voiceActive ? `voice-${voicePhase}` : "",
    isV15 && voiceActive && voicePhase === "listen" ? "listening" : "",
    isV15 && voiceActive && voicePhase === "speak" ? "speaking" : "",
    isV15 && voiceActive && voicePhase === "think" ? "thinking" : "",
    isV15 && voicePhase === "error" ? "error" : "",
    isV15 && !voiceActive && !promptBusy ? "idle" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <section className={`voice-demo-section${embed ? " voice-demo-embed" : ""}`} id="demo">
      {!embed ? (
        <div className="voice-demo-copy">
          {isV15 ? (
            <>
              <div className="v2-kicker pale">Попробуйте сейчас</div>
              <h2>
                Услышьте своего
                <br />
                ИИ-сотрудника.
              </h2>
              <p>
                Выберите вопрос и послушайте ответ. Без регистрации и заявки. Или нажмите на микрофон и спросите о
                DELNO голосом.
              </p>
              <div className="demo-badges">
                <span>
                  <Mic aria-hidden /> Голос
                </span>
                <span>
                  <Sparkles aria-hidden /> ИИ-ответ
                </span>
                <span>
                  <Phone aria-hidden /> Без звонка
                </span>
              </div>
            </>
          ) : (
            <>
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
            </>
          )}
        </div>
      ) : (
        <div className="voice-demo-embed-label">
          <div className="v2-kicker pale">Живое демо</div>
          <h2>Задайте вопрос — как ваш клиент.</h2>
        </div>
      )}

      <div className={orbStageClass} ref={mountRef}>
        {isV15 ? (
          <div className="voice-orb-visual">
            <div className="voice-orb-halo" />
            <button
              type="button"
              className="voice-orb"
              aria-label="Задать вопрос DELNO голосом"
              aria-pressed={voiceActive}
              onClick={toggleVoice}
            >
              <span className="voice-orb-core">
                <Mic aria-hidden />
              </span>
            </button>
          </div>
        ) : (
          <div
            className="delno-crystal-mount delno-crystal-demo"
            ref={mountRef}
            data-contrast="dark"
            data-voice-active={voiceActive ? "true" : undefined}
            data-voice-phase={voicePhase !== "idle" ? voicePhase : undefined}
          >
            <CrystalOrb
              variant="demo"
              voiceActive={voiceActive}
              voicePhase={voicePhase}
              onOrbClick={toggleVoice}
            />
          </div>
        )}
        <b className="voice-demo-status" aria-live="polite" data-phase={voicePhase}>
          {label}
        </b>
        <small>
          {isV15
            ? voiceActive
              ? "Ещё раз — чтобы остановить."
              : "Нажмите один раз, чтобы начать. Ещё раз — чтобы остановить."
            : voiceActive && voicePhase === "listen"
              ? "Говорите — запись остановится сама."
              : "Нажмите на кристалл и задайте вопрос вслух."}
        </small>
      </div>

      <div className="voice-demo-dialog">
        <div className="demo-dialog-head">
          <span>
            <i /> {isV15 ? "Демо-помощник" : "DELNO"}
          </span>
          <Volume2 />
        </div>
        {isV15 && (
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
        )}
        <div className="demo-message user">
          <small>Вы</small>
          <p>{question}</p>
        </div>
        <div className="demo-message delno">
          <small>DELNO</small>
          <p>{answer}</p>
        </div>
        {!isV15 && (
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
        )}
        <p className="demo-disclaimer">
          {isV15
            ? "Демо на готовых сценариях о DELNO. Голос синтезирован ИИ. Виджет для сайта — в планах."
            : "Ответы из базы знаний DELNO. Голос — cedar, как в телефонии."}
        </p>
      </div>

      <audio ref={audioRef} className="voice-audio" preload="none" playsInline />
    </section>
  );
}
