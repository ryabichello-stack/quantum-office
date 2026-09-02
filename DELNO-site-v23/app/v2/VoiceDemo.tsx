"use client";

import { CrystalOrb } from "@/components/widget/CrystalOrb";
import "@/components/widget/crystal-widget.css";
import { useDelnoVoice } from "@/hooks/useDelnoVoice";
import { askDelnoWidget } from "@/lib/widgetApi";
import { Sparkles, Volume2 } from "lucide-react";
import { useRef, useState } from "react";

const prompts = ["Сколько стоит?", "Как подключить номер?", "Что умеет DELNO?"];

export default function VoiceDemo() {
  const mountRef = useRef<HTMLDivElement>(null);
  const [question, setQuestion] = useState("Нажмите на кристалл и задайте вопрос");
  const [answer, setAnswer] = useState("Я отвечу по базе знаний DELNO — о тарифах, подключении и возможностях.");

  const { voiceActive, voicePhase, toggleVoice, audioRef } = useDelnoVoice({
    mountRef,
    onTranscript: async (text) => {
      const { answer: reply, error } = await askDelnoWidget(text);
      if (error || !reply) {
        return "Сейчас не удалось получить ответ. Попробуйте ещё раз.";
      }
      return reply;
    },
    onExchange: (userText, assistantText) => {
      setQuestion(userText);
      setAnswer(assistantText);
    },
  });

  async function answerPrompt(text: string) {
    setQuestion(text);
    const { answer: reply, error } = await askDelnoWidget(text);
    if (error || !reply) {
      setAnswer("Сейчас не удалось получить ответ. Попробуйте ещё раз.");
      return;
    }
    setAnswer(reply);
  }

  const label =
    voicePhase === "listen"
      ? "Слушаю…"
      : voicePhase === "think"
        ? "Думаю…"
        : voicePhase === "speak"
          ? "Отвечаю…"
          : voicePhase === "error"
            ? "Попробуйте ещё раз"
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
        <div
          className="delno-crystal-mount delno-crystal-demo"
          ref={mountRef}
          data-contrast="light"
        >
          <CrystalOrb
            variant="demo"
            voiceActive={voiceActive}
            voicePhase={voicePhase}
            onOrbClick={toggleVoice}
          />
        </div>
        <b>{label}</b>
        <small>Нажмите на кристалл, чтобы говорить. Ещё раз — чтобы остановить.</small>
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
            <button key={prompt} type="button" onClick={() => void answerPrompt(prompt)}>
              {prompt}
            </button>
          ))}
        </div>
        <p className="demo-disclaimer">Ответы из базы знаний DELNO. Голос — тот же, что в телефонии (OpenAI cedar).</p>
      </div>

      <audio ref={audioRef} className="voice-audio" preload="none" playsInline />
    </section>
  );
}
