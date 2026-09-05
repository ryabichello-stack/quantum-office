"use client";

import { useEffect, useRef, useState } from "react";
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

export function CrystalWidget() {
  const basePath = process.env.NEXT_PUBLIC_BASE_PATH || "";
  const apiPath = `${basePath}/api/widget/message`;

  const mountRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const chatBodyRef = useRef<HTMLDivElement>(null);

  const [textOpen, setTextOpen] = useState(false);
  const [input, setInput] = useState("");

  const { messages, busy, sendMessage, sendVoiceQuery, appendExchange } = useCrystalWidgetChat(apiPath);
  const { voiceActive, voicePhase, toggleVoice, audioRef } = useCrystalWidgetVoice({
    mountRef,
    sendVoiceQuery,
    appendExchange,
  });
  useCrystalContrast(mountRef);
  useAutoResizeTextarea(textareaRef, input);

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

  return (
    <div className="delno-crystal-mount delno-crystal-floating" ref={mountRef}>
      <input type="checkbox" id="delno-crystal-text" ref={textRef} defaultChecked={false} hidden aria-hidden />

      <CrystalOrb
        variant="widget"
        voiceActive={voiceActive}
        voicePhase={voicePhase}
        onOrbClick={toggleVoice}
        showChatButton
        onChatClick={() => setTextOpen(true)}
      />

      <section className={`panel${textOpen ? " is-open" : ""}`} id="chatPanel" aria-live="polite">
        <div className="head">
          <strong>DELNO</strong>
          <button type="button" className="close" aria-label="Закрыть чат" onClick={() => setTextOpen(false)}>
            ×
          </button>
        </div>

        <div className="chat-body" id="chatBody" ref={chatBodyRef}>
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
        </div>

        <form
          className="chat-form"
          id="chatForm"
          onSubmit={(e) => onChatSubmit(e, input, sendMessage, setInput)}
        >
          <textarea
            ref={textareaRef}
            className="chat-input"
            id="chatInput"
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
            id="sendBtn"
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
