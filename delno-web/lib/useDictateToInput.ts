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

function getSpeechRecognitionCtor(): (new () => SpeechRecognitionLike) | null {
  if (typeof window === "undefined") return null;
  const w = window as Window & {
    SpeechRecognition?: new () => SpeechRecognitionLike;
    webkitSpeechRecognition?: new () => SpeechRecognitionLike;
  };
  return w.SpeechRecognition || w.webkitSpeechRecognition || null;
}

/**
 * Hold-to-dictate into a text field (does not auto-send).
 */
export function useDictateToInput(onPartialOrFinal: (text: string, isFinal: boolean) => void) {
  const [dictating, setDictating] = useState(false);
  const [supported, setSupported] = useState(true);
  const [error, setError] = useState("");
  const recRef = useRef<SpeechRecognitionLike | null>(null);
  const baseRef = useRef("");
  const holdingRef = useRef(false);

  useEffect(() => {
    setSupported(Boolean(getSpeechRecognitionCtor()));
    return () => {
      try {
        recRef.current?.abort();
      } catch {
        /* ignore */
      }
    };
  }, []);

  const start = useCallback(
    (currentFieldValue: string) => {
      const Ctor = getSpeechRecognitionCtor();
      if (!Ctor) {
        setSupported(false);
        setError("Диктовка не поддерживается в этом браузере — используйте Chrome/Edge.");
        return;
      }
      holdingRef.current = true;
      baseRef.current = currentFieldValue;
      setError("");
      try {
        recRef.current?.abort();
      } catch {
        /* ignore */
      }
      const rec = new Ctor();
      rec.lang = "ru-RU";
      rec.continuous = true;
      rec.interimResults = true;
      rec.onresult = (ev) => {
        let finalChunk = "";
        let interim = "";
        for (let i = ev.resultIndex; i < ev.results.length; i++) {
          const piece = ev.results[i][0]?.transcript || "";
          if (ev.results[i].isFinal) finalChunk += piece;
          else interim += piece;
        }
        const merged = [baseRef.current, finalChunk, interim]
          .map((s) => s.trim())
          .filter(Boolean)
          .join(" ");
        if (finalChunk) {
          baseRef.current = [baseRef.current, finalChunk].map((s) => s.trim()).filter(Boolean).join(" ");
        }
        onPartialOrFinal(merged, Boolean(finalChunk) && !interim);
      };
      rec.onerror = (ev) => {
        if (ev.error === "aborted" || ev.error === "no-speech") return;
        setError(ev.error === "not-allowed" ? "Нет доступа к микрофону" : "Ошибка распознавания");
        setDictating(false);
        holdingRef.current = false;
      };
      rec.onend = () => {
        if (holdingRef.current) {
          try {
            rec.start();
            return;
          } catch {
            /* fall through */
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
        setDictating(false);
        holdingRef.current = false;
      }
    },
    [onPartialOrFinal],
  );

  const stop = useCallback(() => {
    holdingRef.current = false;
    setDictating(false);
    try {
      recRef.current?.stop();
    } catch {
      /* ignore */
    }
  }, []);

  return { dictating, supported, error, start, stop };
}
