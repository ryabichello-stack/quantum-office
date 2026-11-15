"use client";

import { useEffect, useId, useRef, useState } from "react";
import { CrystalOrb } from "./CrystalOrb";
import {
  handleChatKeyDown,
  onChatSubmit,
  useAutoResizeTextarea,
  useCrystalContrast,
  useCrystalWidgetChat,
  useCrystalWidgetVoice,
} from "./useCrystalWidget";
import "./crystal-widget.css";

const QUICK_PROMPTS = [
  "Сколько стоит?",
  "Чем отличаетесь от чат-бота?",
  "Как подключить телефон?",
];

export function CrystalWidget() {
  const instanceId = useId().replace(/:/g, "");
  const basePath = process.env.NEXT_PUBLIC_BASE_PATH || "";
  const apiPath = `${basePath}/api/widget/message`;

  const mountRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const chatBodyRef = useRef<HTMLDivElement>(null);

  const [textOpen, setTextOpen] = useState(false);
  const [docked, setDocked] = useState(false);
  const [input, setInput] = useState("");

  const { messages, busy, sendMessage, sendVoiceQuery, appendExchange } = useCrystalWidgetChat(apiPath);
  const { voiceActive, voicePhase, toggleVoice, audioRef } = useCrystalWidgetVoice({
    mountRef,
    sendVoiceQuery,
    appendExchange,
  });
  useCrystalContrast(mountRef);
  useAutoResizeTextarea(textareaRef, input);

  useEffect(() => {
    let frame = 0;
    const updatePosition = () => {
      frame = 0;
      const mount = mountRef.current;
      const stage = document.getElementById("delno-widget-stage");
      if (!mount || !stage) {
        setDocked(false);
        return;
      }
      const rect = stage.getBoundingClientRect();
      const inView = rect.top < window.innerHeight * 0.72 && rect.bottom > window.innerHeight * 0.22;
      if (inView) {
        const visibleTop = Math.max(rect.top, window.innerHeight * 0.15);
        const visibleBottom = Math.min(rect.bottom, window.innerHeight * 0.85);
        const center = (visibleTop + visibleBottom) / 2;
        mount.style.setProperty("--widget-x", `${rect.left + rect.width / 2}px`);
        mount.style.setProperty("--widget-y", `${center}px`);
      }
      setDocked(inView);
    };
    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(updatePosition);
    };
    updatePosition();
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
    return () => {
      if (frame) cancelAnimationFrame(frame);
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
    };
  }, []);

  const textRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (textRef.current) textRef.current.checked = textOpen;
  }, [textOpen]);

  useEffect(() => {
    if (!textOpen) return;
    const t = window.setTimeout(() => textareaRef.current?.focus({ preventScroll: true }), 180);
    return () => window.clearTimeout(t);
  }, [textOpen]);

  useEffect(() => {
    const el = chatBodyRef.current;
    if (!el) return;
    requestAnimationFrame(() => {
      el.scrollTop = el.scrollHeight;
    });
  }, [messages, textOpen]);

  const showQuickPrompts =
    textOpen && messages.length === 1 && messages[0]?.role === "assistant" && !busy;

  return (
    <div className={`delno-crystal-mount delno-crystal-floating${docked ? " is-docked" : ""}`} ref={mountRef}>
      <input type="checkbox" className="widget-text-toggle" id={`${instanceId}-text`} ref={textRef} defaultChecked={false} hidden aria-hidden />

      <CrystalOrb
        variant="widget"
        voiceActive={voiceActive}
        voicePhase={voicePhase}
        onOrbClick={toggleVoice}
        showChatButton
        onChatClick={() => setTextOpen(true)}
      />

      <section className={`panel${textOpen ? " is-open" : ""}`} id={`${instanceId}-panel`} aria-live="polite">
        <div className="head">
          <strong>DELNO</strong>
          <button type="button" className="close" aria-label="Закрыть чат" onClick={() => setTextOpen(false)}>
            ×
          </button>
        </div>

        <div className="chat-body" id={`${instanceId}-body`} ref={chatBodyRef}>
          {messages.map((msg, idx) => (
            <div key={idx} className={`message-row ${msg.role}`}>
              <div className={`message${msg.typing ? " typing" : ""}`}>
                {msg.typing ? (
                  <>
                    <i />
                    <i />
                    <i />
                  </>
                ) : (
                  msg.text
                )}
              </div>
            </div>
          ))}
          {showQuickPrompts && (
            <div className="widget-quick-prompts" aria-label="Примеры вопросов">
              {QUICK_PROMPTS.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  disabled={busy}
                  onClick={() => sendMessage(prompt)}
                >
                  {prompt}
                </button>
              ))}
            </div>
          )}
        </div>

        <form
          className="chat-form"
          id={`${instanceId}-form`}
          onSubmit={(e) => onChatSubmit(e, input, sendMessage, setInput)}
        >
          <textarea
            ref={textareaRef}
            className="chat-input"
            id={`${instanceId}-input`}
            rows={1}
            maxLength={1200}
            autoComplete="off"
            enterKeyHint="send"
            placeholder="Введите сообщение…"
            aria-label="Сообщение"
            value={input}
            disabled={busy}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => handleChatKeyDown(e, () => sendMessage(input))}
          />
          <button
            className="send-btn"
            id={`${instanceId}-send`}
            type="submit"
            aria-label="Отправить"
            disabled={busy || !input.trim()}
          >
            <svg viewBox="0 0 24 24" width="17" height="17" fill="none" aria-hidden>
              <path
                d="M5 12 19 5l-4.8 14-2.8-5.2L5 12Z"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinejoin="round"
              />
              <path d="m11.4 13.8 3.2-3.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
            </svg>
          </button>
        </form>

        <div className="powered-by">
          <a
            href="https://dlno.ru/?utm_source=widget&utm_medium=branding&utm_campaign=powered_by_delno"
            target="_blank"
            rel="noopener noreferrer"
            aria-label="Перейти на сайт DELNO"
          >
            Работает на DELNO ↗
          </a>
        </div>
      </section>

      <audio ref={audioRef} className="voice-audio" preload="none" playsInline />
    </div>
  );
}
