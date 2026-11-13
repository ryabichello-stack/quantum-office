"use client";

import { useCallback, useEffect, useRef, useState } from "react";

type SpeechRecognitionLike = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives?: number;
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
/** How often to push audio to Whisper for progressive text in the field. */
const WHISPER_TICK_MS = 1100;

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
 * Live text: browser SpeechRecognition interim (word/phrase) when available;
 * always also runs rolling Whisper ticks so text appears while speaking
 * even when Google STT is blocked / unavailable.
 */
export function useDictateToInput(
  onPartialOrFinal: (text: string, isFinal: boolean) => void,
  authToken?: string | null,
) {
  const [dictating, setDictating] = useState(false);
  const [supported, setSupported] = useState(true);
  const [error, setError] = useState("");
  /** 0..1 mic energy for live wave animation while dictating. */
  const [level, setLevel] = useState(0);
  const recRef = useRef<SpeechRecognitionLike | null>(null);
  const mediaRecRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const baseRef = useRef("");
  /** Live dictated portion (browser finals + interim, or Whisper progressive). */
  const liveRef = useRef("");
  const activeRef = useRef(false);
  const browserOkRef = useRef(false);
  const whisperBusyRef = useRef(false);
  const whisperTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const mimeRef = useRef("audio/webm");
  const audioCtxRef = useRef<AudioContext | null>(null);
  const levelRafRef = useRef<number | null>(null);
  const onPartialRef = useRef(onPartialOrFinal);
  onPartialRef.current = onPartialOrFinal;
  const tokenRef = useRef(authToken);
  tokenRef.current = authToken;

  const publish = useCallback((dictated: string, isFinal: boolean) => {
    liveRef.current = dictated;
    onPartialRef.current(mergeField(baseRef.current, dictated), isFinal);
  }, []);

  useEffect(() => {
    const hasBrowser = Boolean(getSpeechRecognitionCtor());
    const hasMedia = typeof window !== "undefined" && !!navigator.mediaDevices?.getUserMedia;
    setSupported(hasBrowser || hasMedia);
    return () => {
      activeRef.current = false;
      if (whisperTimerRef.current) clearInterval(whisperTimerRef.current);
      if (levelRafRef.current != null) cancelAnimationFrame(levelRafRef.current);
      try {
        audioCtxRef.current?.close();
      } catch {
        /* ignore */
      }
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

  const stopLevelMeter = useCallback(() => {
    if (levelRafRef.current != null) {
      cancelAnimationFrame(levelRafRef.current);
      levelRafRef.current = null;
    }
    setLevel(0);
    try {
      void audioCtxRef.current?.close();
    } catch {
      /* ignore */
    }
    audioCtxRef.current = null;
  }, []);

  const startLevelMeter = useCallback(
    (stream: MediaStream) => {
      stopLevelMeter();
      try {
        const AC =
          window.AudioContext ||
          (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
        if (!AC) return;
        const ctx = new AC();
        audioCtxRef.current = ctx;
        const source = ctx.createMediaStreamSource(stream);
        const analyser = ctx.createAnalyser();
        analyser.fftSize = 256;
        analyser.smoothingTimeConstant = 0.75;
        source.connect(analyser);
        const data = new Uint8Array(analyser.frequencyBinCount);
        const tick = () => {
          if (!activeRef.current) {
            setLevel(0);
            return;
          }
          analyser.getByteFrequencyData(data);
          let sum = 0;
          for (let i = 0; i < data.length; i++) sum += data[i];
          const avg = sum / (data.length * 255);
          // Soft floor so the mic still "breathes" while listening quietly.
          setLevel(Math.min(1, 0.12 + avg * 1.6));
          levelRafRef.current = requestAnimationFrame(tick);
        };
        void ctx.resume();
        levelRafRef.current = requestAnimationFrame(tick);
      } catch {
        /* visualizer optional */
      }
    },
    [stopLevelMeter],
  );

  const stopWhisperLoop = useCallback(() => {
    if (whisperTimerRef.current) {
      clearInterval(whisperTimerRef.current);
      whisperTimerRef.current = null;
    }
  }, []);

  const transcribeBlob = useCallback(async (blob: Blob): Promise<string> => {
    if (!tokenRef.current || !blob.size) return "";
    const form = new FormData();
    form.append("file", blob, "dictate.webm");
    const res = await fetch(`${API_URL}/v1/operator/stt`, {
      method: "POST",
      headers: { Authorization: `Bearer ${tokenRef.current}` },
      body: form,
    });
    if (!res.ok) return "";
    const data = (await res.json()) as { text?: string };
    return (data.text || "").trim();
  }, []);

  const whisperTick = useCallback(async () => {
    if (!activeRef.current || whisperBusyRef.current) return;
    // Prefer browser live text when SpeechRecognition is healthy.
    if (browserOkRef.current && liveRef.current.trim()) return;
    const chunks = chunksRef.current;
    if (!chunks.length) return;
    const blob = new Blob(chunks, { type: mimeRef.current });
    if (blob.size < 2500) return;
    whisperBusyRef.current = true;
    try {
      const text = await transcribeBlob(blob);
      if (!activeRef.current) return;
      if (text) publish(text, false);
    } catch {
      /* keep listening */
    } finally {
      whisperBusyRef.current = false;
    }
  }, [publish, transcribeBlob]);

  const stopBrowser = useCallback(() => {
    try {
      recRef.current?.stop();
    } catch {
      /* ignore */
    }
  }, []);

  const stopMedia = useCallback(() => {
    stopWhisperLoop();
    try {
      if (mediaRecRef.current && mediaRecRef.current.state !== "inactive") {
        mediaRecRef.current.stop();
      }
    } catch {
      /* ignore */
    }
  }, [stopWhisperLoop]);

  const stop = useCallback(() => {
    activeRef.current = false;
    setDictating(false);
    stopLevelMeter();
    stopBrowser();
    stopMedia();
  }, [stopBrowser, stopLevelMeter, stopMedia]);

  const startMediaAndWhisper = useCallback(
    async (currentFieldValue: string) => {
      if (!tokenRef.current) {
        setError("Нет сессии для распознавания речи.");
        return false;
      }
      if (!navigator.mediaDevices?.getUserMedia) {
        setSupported(false);
        setError("Микрофон недоступен в этом браузере.");
        return false;
      }
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaStreamRef.current = stream;
        const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
          ? "audio/webm;codecs=opus"
          : "audio/webm";
        mimeRef.current = mime;
        const recorder = new MediaRecorder(stream, { mimeType: mime });
        chunksRef.current = [];
        recorder.ondataavailable = (ev) => {
          if (ev.data?.size) chunksRef.current.push(ev.data);
        };
        recorder.onstop = async () => {
          stopWhisperLoop();
          stream.getTracks().forEach((t) => t.stop());
          mediaStreamRef.current = null;
          const blob = new Blob(chunksRef.current, { type: mime });
          chunksRef.current = [];
          // Final pass only if browser never delivered text.
          if (!browserOkRef.current || !liveRef.current.trim()) {
            try {
              const text = blob.size ? await transcribeBlob(blob) : "";
              if (text) publish(text, true);
              else if (!liveRef.current.trim()) {
                setError("Пустая расшифровка — говорите чуть дольше.");
                publish("", true);
              } else {
                publish(liveRef.current, true);
              }
            } catch {
              setError("Ошибка связи при распознавании.");
              publish(liveRef.current, true);
            }
          } else {
            publish(liveRef.current, true);
          }
          setDictating(false);
          activeRef.current = false;
        };
        mediaRecRef.current = recorder;
        startLevelMeter(stream);
        // timeslice → progressive blobs for rolling Whisper
        recorder.start(700);
        whisperTimerRef.current = setInterval(() => {
          void whisperTick();
        }, WHISPER_TICK_MS);
        // Kick first tick a bit earlier so text shows within ~1s of speech.
        window.setTimeout(() => void whisperTick(), 650);
        return true;
      } catch {
        setError("Нет доступа к микрофону — разрешите его в браузере.");
        return false;
      }
    },
    [publish, startLevelMeter, stopWhisperLoop, transcribeBlob, whisperTick],
  );

  const startBrowser = useCallback((currentFieldValue: string) => {
    const Ctor = getSpeechRecognitionCtor();
    if (!Ctor) return false;
    try {
      recRef.current?.abort();
    } catch {
      /* ignore */
    }
    const rec = new Ctor();
    rec.lang = "ru-RU";
    rec.continuous = true;
    rec.interimResults = true;
    if (typeof rec.maxAlternatives === "number") rec.maxAlternatives = 1;
    let finals = "";
    rec.onresult = (ev) => {
      browserOkRef.current = true;
      let interim = "";
      for (let i = ev.resultIndex; i < ev.results.length; i++) {
        const piece = ev.results[i][0]?.transcript || "";
        if (ev.results[i].isFinal) finals = mergeField(finals, piece);
        else interim += piece;
      }
      // Word/phrase blocks into the field immediately (finals + live interim).
      publish(mergeField(finals, interim), Boolean(finals) && !interim);
    };
    rec.onerror = (ev) => {
      const code = ev.error || "";
      if (BENIGN_ERRORS.has(code)) return;
      browserOkRef.current = false;
      if (code === "not-allowed" || code === "service-not-allowed") {
        setError(errorMessage(code));
        activeRef.current = false;
        setDictating(false);
        stopMedia();
        return;
      }
      // Keep rolling Whisper — do not kill dictation on Google STT network blips.
    };
    rec.onend = () => {
      if (activeRef.current) {
        try {
          rec.start();
        } catch {
          browserOkRef.current = false;
        }
      }
    };
    recRef.current = rec;
    try {
      rec.start();
      return true;
    } catch {
      return false;
    }
  }, [publish, stopMedia]);

  const start = useCallback(
    async (currentFieldValue: string) => {
      setError("");
      baseRef.current = currentFieldValue.trimEnd();
      liveRef.current = "";
      browserOkRef.current = false;
      activeRef.current = true;
      setDictating(true);
      // Do not put «…» into the field — wait for real words.
      const mediaOk = await startMediaAndWhisper(currentFieldValue);
      if (!mediaOk) {
        activeRef.current = false;
        setDictating(false);
        return;
      }
      // Parallel browser STT for true word-by-word when the engine works.
      startBrowser(currentFieldValue);
    },
    [startBrowser, startMediaAndWhisper],
  );

  const toggle = useCallback(
    (currentFieldValue: string) => {
      if (activeRef.current || dictating) {
        stop();
        return;
      }
      void start(currentFieldValue);
    },
    [dictating, start, stop],
  );

  const clearError = useCallback(() => setError(""), []);

  return { dictating, supported, error, level, start, stop, toggle, clearError };
}
