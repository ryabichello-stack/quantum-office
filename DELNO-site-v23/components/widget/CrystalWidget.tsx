"use client";

import { useEffect, useRef, useState } from "react";
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
  const orbSrc = `${basePath}/widget/assets/crystal-orb-static.webp`;
  const apiPath = `${basePath}/api/widget/message`;

  const mountRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const chatBodyRef = useRef<HTMLDivElement>(null);

  const [textOpen, setTextOpen] = useState(false);
  const [input, setInput] = useState("");

  const { messages, busy, sendMessage, sendVoiceQuery, appendExchange } = useCrystalWidgetChat(apiPath);
  const { voiceActive, toggleVoice } = useCrystalWidgetVoice({
    mountRef,
    sendVoiceQuery,
    appendExchange,
  });
  useCrystalContrast(mountRef);
  useAutoResizeTextarea(textareaRef, input);

  const voiceRef = useRef<HTMLInputElement>(null);
  const textRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (voiceRef.current) voiceRef.current.checked = voiceActive;
  }, [voiceActive]);

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
    <div className="delno-crystal-mount" ref={mountRef}>
      <input type="checkbox" id="delno-crystal-voice" ref={voiceRef} defaultChecked={false} hidden aria-hidden />
      <input type="checkbox" id="delno-crystal-text" ref={textRef} defaultChecked={false} hidden aria-hidden />

      <div className="widget">
        <div className="state">
          <span className="listen">Слушаю…</span>
          <span className="think">Думаю…</span>
          <span className="speak">Отвечаю…</span>
        </div>

        <button
          type="button"
          className="chat"
          aria-label="Текстовый чат"
          onClick={() => setTextOpen(true)}
        >
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" aria-hidden>
            <path
              d="M5.5 6.2h13a2.3 2.3 0 0 1 2.3 2.3v6.2a2.3 2.3 0 0 1-2.3 2.3H11l-4.5 2.8V17H5.5a2.3 2.3 0 0 1-2.3-2.3V8.5a2.3 2.3 0 0 1 2.3-2.3Z"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinejoin="round"
            />
          </svg>
        </button>

        <div className="orb-anchor">
          <button
            type="button"
            className="orb-hit"
            aria-label={voiceActive ? "Остановить голосовой режим" : "Говорить с DELNO"}
            aria-pressed={voiceActive}
            onClick={toggleVoice}
          />

          <div className="motion">
            <span className="ground" />

            <div className="rings" aria-hidden="true">
              <i className="sharp r1" />
              <i className="soft r2" />
              <i className="sharp r3" />
            </div>

            <span className="active-halo" />

            <div className="breath">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img className="orb-img" src={orbSrc} alt="" />
              <span className="fire-path">
                <span className="fire fire-idle" />
                <span className="fire fire-active" />
              </span>
            </div>

            <span className="icon mic">
              <svg viewBox="0 0 24 24" width="17" height="17" fill="none" aria-hidden>
                <path
                  d="M12 15.1a3.6 3.6 0 0 0 3.6-3.6V7.2a3.6 3.6 0 1 0-7.2 0v4.3a3.6 3.6 0 0 0 3.6 3.6Z"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                />
                <path
                  d="M6.8 11.3a5.2 5.2 0 0 0 10.4 0M12 16.5v3M9.5 19.5h5"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                />
              </svg>
            </span>

            <span className="icon dots">
              <i />
              <i />
              <i />
            </span>
            <span className="icon wave">
              <i />
              <i />
              <i />
              <i />
              <i />
            </span>
          </div>
        </div>
      </div>

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
    </div>
  );
}
