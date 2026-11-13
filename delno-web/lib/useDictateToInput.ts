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
const API_URL = process.env.NEXT_PUBLIC_DELNO_API_URL || "http://127.0.0.1:18020";
const LISTENING_MARK = "…";

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
      return "Нет доступа к микрофону — разрешите его в настройках браузера.";
    case "audio-capture":
      return "Микрофон недоступен. Проверьте устройство.";
    case "network":
      return "Сеть недоступна для распознавания речи.";
    default:
      return "Не удалось распознать речь. Нажмите mic ещё раз.";
  }
}

function mergeField(base: string, chunk: string): string {
  return [base, chunk].map((s) => s.trim()).filter(Boolean).join(" ");
}

/**
 * Click-to-toggle dictation into the composer.
 * Prefer browser SpeechRecognition for live interim text in the field;
 * fall back to server Whisper (text appears after stop / with «…» while listening).
 */
export function useDictateToInput(
  onPartialOrFinal: (text: string, isFinal: boolean) => void,
  authToken?: string | null,
) {
  const [dictating, setDictating] = useState(false);
  const [supported, setSupported] = useState(true);
  const [error, setError] = useState("");
  const recRef = useRef<SpeechRecognitionLike | null>(null);
  const mediaRecRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const baseRef = useRef("");
  const activeRef = useRef(false);
  const modeRef = useRef<"browser" | "server">("browser");
  const onPartialRef = useRef(onPartialOrFinal);
  onPartialRef.current = onPartialOrFinal;
  const tokenRef = useRef(authToken);
  tokenRef.current = authToken;

  useEffect(() => {
    const hasBrowser = Boolean(getSpeechRecognitionCtor());
    const hasMedia = typeof window !== "undefined" && !!navigator.mediaDevices?.getUserMedia;
    setSupported(hasBrowser || hasMedia);
    return () => {
      activeRef.current = false;
      try {
        recRef.current?.abort();
      } catch {
        /* ignore */
      }
      try {
        mediaRecRef.current?.stop();
      } catch {
        /* ignore */
      }
      mediaStreamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  const stopBrowser = useCallback(() => {
    try {
      recRef.current?.stop();
    } catch {
      /* ignore */
    }
  }, []);

  const stopServer = useCallback(() => {
    try {
      if (mediaRecRef.current && mediaRecRef.current.state !== "inactive") {
        mediaRecRef.current.stop();
      }
    } catch {
      /* ignore */
    }
  }, []);

  const stop = useCallback(() => {
    activeRef.current = false;
    setDictating(false);
    if (modeRef.current === "server") stopServer();
    else stopBrowser();
  }, [stopBrowser, stopServer]);

  const startServer = useCallback(async (currentFieldValue: string) => {
    if (!tokenRef.current) {
      setError("Нет сессии для серверного распознавания.");
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      setSupported(false);
      setError("Микрофон недоступен в этом браузере.");
      return;
    }
    setError("");
    baseRef.current = currentFieldValue.replace(/\s*…\s*$/, "").trimEnd();
    activeRef.current = true;
    modeRef.current = "server";
    // Show listening marker in the field immediately.
    onPartialRef.current(mergeField(baseRef.current, LISTENING_MARK), false);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaStreamRef.current = stream;
      const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : "audio/webm";
      const recorder = new MediaRecorder(stream, { mimeType: mime });
      chunksRef.current = [];
      recorder.ondataavailable = (ev) => {
        if (ev.data.size) chunksRef.current.push(ev.data);
      };
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        mediaStreamRef.current = null;
        const blob = new Blob(chunksRef.current, { type: mime });
        chunksRef.current = [];
        if (!blob.size) {
          onPartialRef.current(baseRef.current, true);
          setDictating(false);
          activeRef.current = false;
          return;
        }
        try {
          const form = new FormData();
          form.append("file", blob, "dictate.webm");
          const res = await fetch(`${API_URL}/v1/operator/stt`, {
            method: "POST",
            headers: { Authorization: `Bearer ${tokenRef.current}` },
            body: form,
          });
          if (!res.ok) {
            setError("Сервер не распознал речь. Попробуйте ещё раз.");
            onPartialRef.current(baseRef.current, true);
            setDictating(false);
            activeRef.current = false;
            return;
          }
          const data = (await res.json()) as { text?: string };
          const text = (data.text || "").trim();
          if (text) {
            onPartialRef.current(mergeField(baseRef.current, text), true);
          } else {
            setError("Пустая расшифровка — говорите чуть дольше.");
            onPartialRef.current(baseRef.current, true);
          }
        } catch {
          setError("Ошибка связи при распознавании.");
          onPartialRef.current(baseRef.current, true);
        } finally {
          setDictating(false);
          activeRef.current = false;
        }
      };
      mediaRecRef.current = recorder;
      recorder.start();
      setDictating(true);
    } catch {
      setError("Нет доступа к микрофону — разрешите его в браузере.");
      onPartialRef.current(baseRef.current, true);
      activeRef.current = false;
      setDictating(false);
    }
  }, []);

  const startBrowser = useCallback(
    (currentFieldValue: string) => {
      const Ctor = getSpeechRecognitionCtor();
      if (!Ctor) {
        void startServer(currentFieldValue);
        return;
      }
      modeRef.current = "browser";
      activeRef.current = true;
      baseRef.current = currentFieldValue.replace(/\s*…\s*$/, "").trimEnd();
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
        if (finalChunk) {
          baseRef.current = mergeField(baseRef.current, finalChunk);
        }
        const merged = mergeField(baseRef.current, interim);
        onPartialRef.current(merged, Boolean(finalChunk) && !interim);
      };
      rec.onerror = (ev) => {
        const code = ev.error || "";
        if (BENIGN_ERRORS.has(code)) return;
        activeRef.current = false;
        setDictating(false);
        if (code === "not-allowed" || code === "service-not-allowed") {
          setError(errorMessage(code));
          return;
        }
        // Fall back to server Whisper; keep whatever text already landed in the field.
        void startServer(baseRef.current);
      };
      rec.onend = () => {
        if (activeRef.current && modeRef.current === "browser") {
          try {
            rec.start();
            return;
          } catch {
            activeRef.current = false;
          }
        }
        if (modeRef.current === "browser") setDictating(false);
      };
      recRef.current = rec;
      try {
        rec.start();
        setDictating(true);
      } catch {
        void startServer(currentFieldValue);
      }
    },
    [startServer],
  );

  const toggle = useCallback(
    (currentFieldValue: string) => {
      if (activeRef.current || dictating) {
        stop();
        return;
      }
      // Live text in the composer: browser STT first when the engine exists.
      if (getSpeechRecognitionCtor()) {
        startBrowser(currentFieldValue);
        return;
      }
      void startServer(currentFieldValue);
    },
    [dictating, startBrowser, startServer, stop],
  );

  const clearError = useCallback(() => setError(""), []);

  return { dictating, supported, error, start: startBrowser, stop, toggle, clearError };
}
