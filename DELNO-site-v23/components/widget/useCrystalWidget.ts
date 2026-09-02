"use client";

import { useDelnoVoice, type VoicePhase } from "@/hooks/useDelnoVoice";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

type ChatMessage = { role: "user" | "assistant"; text: string; typing?: boolean };

export type { VoicePhase };

type WidgetAnswer = {
  message?: string;
  conversation_id?: string;
  next_step?: string;
};

const SITE_KEY = process.env.NEXT_PUBLIC_DELNO_WIDGET_SITE_KEY || "demo_dlno";

function cryptoSafeId() {
  try {
    if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
  } catch {
    /* ignore */
  }
  return `w_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`;
}

function isLikelyName(text: string) {
  const s = text.trim();
  if (!s || s.length > 48) return false;
  if (/[?!.:,;]/.test(s)) return false;
  return s.split(/\s+/).length <= 4;
}

function personalizedGreeting(name: string) {
  const first = name.trim().split(/\s+/)[0];
  return first
    ? `Приятно познакомиться, ${first}. Что ещё хотите уточнить?`
    : "Приятно познакомиться. Что ещё хотите уточнить?";
}

export function useCrystalWidgetChat(apiPath: string) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    { role: "assistant", text: "Здравствуйте. Чем могу помочь?" },
  ]);
  const [busy, setBusy] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const sessionIdRef = useRef<string | null>(null);
  const visitorIdRef = useRef("");
  const nameRef = useRef("");
  const askedNameRef = useRef(false);
  const awaitingNameRef = useRef(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    visitorIdRef.current = localStorage.getItem("delno_widget_visitor") || cryptoSafeId();
    localStorage.setItem("delno_widget_visitor", visitorIdRef.current);
    nameRef.current = localStorage.getItem("delno_widget_name") || "";
    askedNameRef.current = localStorage.getItem("delno_widget_asked_name") === "1";
    const storedSession = localStorage.getItem("delno_widget_session");
    if (storedSession) {
      sessionIdRef.current = storedSession;
      setSessionId(storedSession);
    }
  }, []);

  const persistSession = useCallback((id: string) => {
    sessionIdRef.current = id;
    setSessionId(id);
    localStorage.setItem("delno_widget_session", id);
  }, []);

  const requestAnswer = useCallback(
    async (value: string): Promise<{ answer: string | null; payload: WidgetAnswer | null; error?: string }> => {
      try {
        const res = await fetch(apiPath, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            site_key: SITE_KEY,
            session_id: sessionIdRef.current,
            visitor_id: visitorIdRef.current,
            message: value,
            visitor: {
              name: nameRef.current || null,
              page_url: typeof window !== "undefined" ? window.location.href : null,
              referrer: typeof document !== "undefined" ? document.referrer || null : null,
            },
            channel: "web",
          }),
        });
        const raw = await res.text();
        if (!res.ok) {
          let detail = raw.slice(0, 200);
          try {
            const parsed = JSON.parse(raw) as { error?: string; detail?: string };
            detail = parsed.detail || parsed.error || detail;
          } catch {
            /* ignore */
          }
          return { answer: null, payload: null, error: detail || `HTTP ${res.status}` };
        }
        const payload = JSON.parse(raw) as WidgetAnswer;
        if (payload.conversation_id) persistSession(payload.conversation_id);
        return { answer: payload.message || null, payload };
      } catch (err) {
        const message = err instanceof Error ? err.message : "fetch failed";
        console.warn("DELNO widget:", err);
        return { answer: null, payload: null, error: message };
      }
    },
    [apiPath, persistSession],
  );

  const maybeAskName = useCallback(async (payload: WidgetAnswer | null, messageLength: number) => {
    const backendRequestsName = payload?.next_step === "ask_name";
    if (!nameRef.current && (!askedNameRef.current || backendRequestsName) && messageLength >= 8) {
      await new Promise((r) => setTimeout(r, 260));
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: "Кстати, как я могу к вам обращаться?" },
      ]);
      awaitingNameRef.current = true;
      askedNameRef.current = true;
      localStorage.setItem("delno_widget_asked_name", "1");
    }
  }, []);

  const sendMessage = useCallback(
    async (raw: string) => {
      const value = raw.trim();
      if (!value || busy) return;

      setMessages((prev) => [...prev, { role: "user", text: value }]);
      setBusy(true);

      if (awaitingNameRef.current && isLikelyName(value)) {
        await new Promise((r) => setTimeout(r, 430));
        nameRef.current = value;
        localStorage.setItem("delno_widget_name", value);
        awaitingNameRef.current = false;
        const greeting = personalizedGreeting(value);
        setMessages((prev) => [...prev, { role: "assistant", text: greeting }]);
        setBusy(false);
        return;
      }

      setMessages((prev) => [...prev, { role: "assistant", text: "", typing: true }]);

      const { answer, payload, error } = await requestAnswer(value);
      await new Promise((r) => setTimeout(r, payload ? 120 : 320));

      const reply =
        answer ||
        (error
          ? "Сейчас не удалось получить ответ. Попробуйте ещё раз или напишите вопрос чуть иначе."
          : value.length < 8
            ? "Да, могу помочь. Уточните, пожалуйста, вопрос чуть подробнее."
            : "Понял ваш вопрос. Я могу ответить по базе знаний компании и, если нужно, передать обращение сотруднику.");

      setMessages((prev) => {
        const withoutTyping = prev.filter((m) => !m.typing);
        return [...withoutTyping, { role: "assistant", text: reply }];
      });

      await maybeAskName(payload, value.length);
      setBusy(false);
    },
    [busy, maybeAskName, requestAnswer],
  );

  const sendVoiceQuery = useCallback(
    async (raw: string): Promise<string> => {
      const value = raw.trim();
      if (!value) return "Не удалось распознать вопрос. Попробуйте ещё раз.";

      const { answer, error } = await requestAnswer(value);
      return (
        answer ||
        (error
          ? "Сейчас не удалось получить ответ. Попробуйте ещё раз."
          : "Понял ваш вопрос. Могу ответить по базе знаний компании или передать обращение сотруднику.")
      );
    },
    [requestAnswer],
  );

  const appendExchange = useCallback((userText: string, assistantText: string) => {
    setMessages((prev) => [
      ...prev,
      { role: "user", text: userText },
      { role: "assistant", text: assistantText },
    ]);
  }, []);

  return { messages, busy, sendMessage, sendVoiceQuery, appendExchange, sessionId };
}

export function useCrystalWidgetVoice(options: {
  mountRef: React.RefObject<HTMLElement | null>;
  sendVoiceQuery: (text: string) => Promise<string>;
  appendExchange: (userText: string, assistantText: string) => void;
}) {
  return useDelnoVoice({
    mountRef: options.mountRef,
    onTranscript: options.sendVoiceQuery,
    onExchange: options.appendExchange,
  });
}

export function useCrystalContrast(mountRef: React.RefObject<HTMLElement | null>) {
  useEffect(() => {
    const root = mountRef.current;
    if (!root) return;

    function parseColor(str: string) {
      const m = String(str).match(/rgba?\(([^)]+)\)/i);
      if (!m) return null;
      const p = m[1].split(",").map((v) => parseFloat(v.trim()));
      return { r: p[0] || 0, g: p[1] || 0, b: p[2] || 0, a: p.length > 3 ? p[3] : 1 };
    }
    function lum(c: { r: number; g: number; b: number }) {
      return 0.2126 * c.r + 0.7152 * c.g + 0.0722 * c.b;
    }

    function detect() {
      if (!root) return;
      const els = document.elementsFromPoint(window.innerWidth / 2, window.innerHeight - 60);
      let c: { r: number; g: number; b: number; a: number } | null = null;
      for (const el of els) {
        if (el instanceof Element && (el.closest(".widget") || el.closest(".panel"))) continue;
        let n: Element | null = el;
        while (n && n !== document.documentElement) {
          const pc = parseColor(getComputedStyle(n).backgroundColor);
          if (pc && pc.a > 0.55) {
            c = pc;
            break;
          }
          n = n.parentElement;
        }
        if (c) break;
      }
      if (!c) c = parseColor(getComputedStyle(document.body).backgroundColor) || { r: 255, g: 255, b: 255, a: 1 };
      root.setAttribute("data-contrast", lum(c) < 145 ? "light" : "dark");
    }

    detect();
    window.addEventListener("resize", detect, { passive: true });
    window.addEventListener("scroll", detect, { passive: true });
    return () => {
      window.removeEventListener("resize", detect);
      window.removeEventListener("scroll", detect);
    };
  }, [mountRef]);
}

export function useAutoResizeTextarea(
  ref: React.RefObject<HTMLTextAreaElement | null>,
  value: string,
) {
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 104)}px`;
  }, [ref, value]);
}

export function handleChatKeyDown(
  e: React.KeyboardEvent<HTMLTextAreaElement>,
  onSend: () => void,
) {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    onSend();
  }
}

export function onChatSubmit(
  e: FormEvent,
  input: string,
  sendMessage: (text: string) => void,
  setInput: (v: string) => void,
) {
  e.preventDefault();
  if (!input.trim()) return;
  sendMessage(input);
  setInput("");
}
