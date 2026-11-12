"use client";

import { useCallback, useEffect, useRef, useState } from "react";

type SpeechRecognitionLike = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onresult: ((ev: SpeechRecognitionEventLike) => void) | null;
  onerror: ((ev: { error?: string }) => void) | null;
  onend: (() => void) | null;
};

type SpeechRecognitionEventLike = {
  resultIndex: number;
  results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }>;
};

const BENIGN_ERRORS = new Set(["aborted", "no-speech", "interrupted"]);

function getSpeechRecognitionCtor(): (new () => SpeechRecognitionLike) | null {
  if (typeof window === "undefined") return null;
  const w = window as Window & {
    SpeechRecognition?: new () => SpeechRecognitionLike;
    webkitSpeechRecognition?: new () => SpeechRecognitionLike;
  };
  return w.SpeechRecognition || w.webkitSpeechRecognition || null;
}

function errorMessage(code?: string): string {
  switch (code) {
    case "not-allowed":
    case "service-not-allowed":
      return "Нет доступа к микрофону — разрешите его в браузере.";
    case "audio-capture":
      return "Микрофон недоступен. Проверьте устройство.";
    case "network":
      return "Сеть недоступна для распознавания речи.";
    case "language-not-supported":
      return "Язык ru-RU не поддерживается в этом браузере.";
    default:
      return "Не удалось распознать речь. Нажмите mic ещё раз или напишите текстом.";
  }
}

/**
 * Click-to-toggle dictation into a text field (does not auto-send).
 * Hold mode is brittle on trackpads (pointerleave → abort → false errors).
 */
export function useDictateToInput(onPartialOrFinal: (text: string, isFinal: boolean) => void) {
  const [dictating, setDictating] = useState(false);
  const [supported, setSupported] = useState(true);
  const [error, setError] = useState("");
  const recRef = useRef<SpeechRecognitionLike | null>(null);
  const baseRef = useRef("");
  const activeRef = useRef(false);
  const onPartialRef = useRef(onPartialOrFinal);
  onPartialRef.current = onPartialOrFinal;

  useEffect(() => {
    setSupported(Boolean(getSpeechRecognitionCtor()));
    return () => {
      activeRef.current = false;
      try {
        recRef.current?.abort();
      } catch {
        /* ignore */
      }
    };
  }, []);

  const stop = useCallback(() => {
    activeRef.current = false;
    setDictating(false);
    try {
      recRef.current?.stop();
    } catch {
      /* ignore */
    }
  }, []);

  const start = useCallback((currentFieldValue: string) => {
    const Ctor = getSpeechRecognitionCtor();
    if (!Ctor) {
      setSupported(false);
      setError("Диктовка не поддерживается — откройте Chrome или Edge.");
      return;
    }
    activeRef.current = true;
    baseRef.current = currentFieldValue;
    setError("");
    try {
      recRef.current?.abort();
    } catch {
      /* ignore */
    }
    const rec = new Ctor();
    rec.lang = "ru-RU";
    // One utterance per session — more stable than continuous restart loops.
    rec.continuous = false;
    rec.interimResults = true;
    rec.onresult = (ev) => {
      let finalChunk = "";
      let interim = "";
      for (let i = ev.resultIndex; i < ev.results.length; i++) {
        const piece = ev.results[i][0]?.transcript || "";
        if (ev.results[i].isFinal) finalChunk += piece;
        else interim += piece;
      }
      if (finalChunk) {
        baseRef.current = [baseRef.current, finalChunk].map((s) => s.trim()).filter(Boolean).join(" ");
      }
      const merged = [baseRef.current, interim].map((s) => s.trim()).filter(Boolean).join(" ");
      onPartialRef.current(merged, Boolean(finalChunk) && !interim);
    };
    rec.onerror = (ev) => {
      const code = ev.error || "";
      if (BENIGN_ERRORS.has(code)) return;
      setError(errorMessage(code));
      activeRef.current = false;
      setDictating(false);
    };
    rec.onend = () => {
      if (activeRef.current) {
        // Pause between utterances: user toggles off to finish.
        try {
          rec.start();
          return;
        } catch {
          activeRef.current = false;
        }
      }
      setDictating(false);
    };
    recRef.current = rec;
    try {
      rec.start();
      setDictating(true);
    } catch {
      setError("Не удалось запустить диктовку");
      activeRef.current = false;
      setDictating(false);
    }
  }, []);

  const toggle = useCallback(
    (currentFieldValue: string) => {
      if (activeRef.current || dictating) {
        stop();
        return;
      }
      start(currentFieldValue);
    },
    [dictating, start, stop],
  );

  const clearError = useCallback(() => setError(""), []);

  return { dictating, supported, error, start, stop, toggle, clearError };
}
