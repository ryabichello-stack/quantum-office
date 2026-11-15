"use client";

import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import {
  initialDictate,
  reduceDictate,
  type DictateEvent,
  type DictateSnapshot,
} from "@/lib/hermesUiStates";
import { isBenignSttError, sttErrorMessage } from "@/lib/sttErrors";

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

const API_URL = process.env.NEXT_PUBLIC_DELNO_API_URL || "http://127.0.0.1:18020";

function getSpeechRecognitionCtor(): (new () => SpeechRecognitionLike) | null {
  if (typeof window === "undefined") return null;
  const w = window as Window & {
    SpeechRecognition?: new () => SpeechRecognitionLike;
    webkitSpeechRecognition?: new () => SpeechRecognitionLike;
  };
  return w.SpeechRecognition || w.webkitSpeechRecognition || null;
}

function mergeField(base: string, chunk: string): string {
  return [base, chunk].map((s) => s.trim()).filter(Boolean).join(" ");
}

function pickMime(): string {
  if (typeof MediaRecorder === "undefined") return "";
  const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"];
  for (const candidate of candidates) {
    try {
      if (MediaRecorder.isTypeSupported(candidate)) return candidate;
    } catch {
      /* ignore */
    }
  }
  return "";
}

function micFailure(err: unknown): string {
  const name =
    err && typeof err === "object" && "name" in err ? String((err as { name?: string }).name || "") : "";
  return sttErrorMessage(name || "audio-capture");
}

/**
 * Click once to record, click «Стоп» to transcribe into the composer.
 * Streaming text is shown only when the browser SpeechRecognition engine
 * actually emits partials. Server Whisper is one-shot: while it runs the UI
 * stays on «Распознаю…» and does not invent interim words.
 * The transcript is written into the field for editing. Nothing is sent.
 */
export function useDictateToInput(
  onPartialOrFinal: (text: string, isFinal: boolean) => void,
  authToken?: string | null,
) {
  const snapRef = useRef<DictateSnapshot>(initialDictate());
  const [snap, dispatch] = useReducer(reduceDictate, undefined, initialDictate);
  const send = useCallback((event: DictateEvent) => {
    snapRef.current = reduceDictate(snapRef.current, event);
    dispatch(event);
  }, []);

  const [supported, setSupported] = useState(true);
  const recRef = useRef<SpeechRecognitionLike | null>(null);
  const mediaRecRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const baseRef = useRef("");
  const liveRef = useRef("");
  const activeRef = useRef(false);
  const discardRef = useRef(false);
  const stoppingRef = useRef(false);
  const genRef = useRef(0);
  const mimeRef = useRef("audio/webm");
  const audioCtxRef = useRef<AudioContext | null>(null);
  const levelRafRef = useRef<number | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const onPartialRef = useRef(onPartialOrFinal);
  onPartialRef.current = onPartialOrFinal;
  const tokenRef = useRef(authToken);
  tokenRef.current = authToken;
  const sendRef = useRef(send);
  sendRef.current = send;

  const publish = useCallback((dictated: string, isFinal: boolean) => {
    liveRef.current = dictated;
    onPartialRef.current(mergeField(baseRef.current, dictated), isFinal);
  }, []);

  const stopTimer = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const stopLevelMeter = useCallback(() => {
    if (levelRafRef.current != null) {
      cancelAnimationFrame(levelRafRef.current);
      levelRafRef.current = null;
    }
    const ctx = audioCtxRef.current;
    audioCtxRef.current = null;
    if (ctx) {
      try {
        void ctx.close();
      } catch {
        /* ignore */
      }
    }
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
        analyser.fftSize = 512;
        analyser.smoothingTimeConstant = 0.65;
        source.connect(analyser);
        const data = new Uint8Array(analyser.fftSize);
        const tick = () => {
          if (!activeRef.current) return;
          analyser.getByteTimeDomainData(data);
          let sum = 0;
          for (let i = 0; i < data.length; i++) {
            const v = (data[i] - 128) / 128;
            sum += v * v;
          }
          const rms = Math.sqrt(sum / data.length);
          sendRef.current({ type: "level", level: Math.min(1, rms * 3.2) });
          levelRafRef.current = requestAnimationFrame(tick);
        };
        void ctx.resume();
        levelRafRef.current = requestAnimationFrame(tick);
      } catch {
        /* visualizer is optional; recording still works */
      }
    },
    [stopLevelMeter],
  );

  const startTimer = useCallback(() => {
    stopTimer();
    const started = Date.now();
    sendRef.current({ type: "tick", elapsedMs: 0 });
    timerRef.current = setInterval(() => {
      if (!activeRef.current) return;
      sendRef.current({ type: "tick", elapsedMs: Date.now() - started });
    }, 250);
  }, [stopTimer]);

  const transcribeBlob = useCallback(async (blob: Blob): Promise<{ text: string; error: string }> => {
    if (!tokenRef.current) return { text: "", error: sttErrorMessage("no-session") };
    if (blob.size < 400) return { text: "", error: sttErrorMessage("STT_EMPTY") };
    const mime = blob.type || mimeRef.current || "audio/webm";
    const filename = mime.includes("mp4") ? "dictate.m4a" : "dictate.webm";
    const form = new FormData();
    form.append("file", blob, filename);
    let res: Response;
    try {
      res = await fetch(`${API_URL}/v1/operator/stt`, {
        method: "POST",
        headers: { Authorization: `Bearer ${tokenRef.current}` },
        body: form,
      });
    } catch {
      return { text: "", error: sttErrorMessage("network") };
    }
    if (!res.ok) {
      let code = "STT_FAILED";
      try {
        const data = (await res.json()) as { detail?: unknown };
        if (typeof data.detail === "string" && data.detail.trim()) code = data.detail.trim();
      } catch {
        code = "STT_FAILED";
      }
      return { text: "", error: sttErrorMessage(code) };
    }
    try {
      const data = (await res.json()) as { text?: string };
      const text = (data.text || "").trim();
      if (!text) return { text: "", error: sttErrorMessage("STT_EMPTY") };
      return { text, error: "" };
    } catch {
      return { text: "", error: sttErrorMessage("STT_FAILED") };
    }
  }, []);

  const stopBrowser = useCallback((): Promise<void> => {
    return new Promise((resolve) => {
      const rec = recRef.current;
      if (!rec) {
        resolve();
        return;
      }
      let settled = false;
      const finish = () => {
        if (settled) return;
        settled = true;
        resolve();
      };
      rec.onend = () => finish();
      try {
        rec.stop();
      } catch {
        finish();
      }
      window.setTimeout(finish, 700);
    });
  }, []);

  const collectBlob = useCallback((): Promise<Blob> => {
    return new Promise((resolve) => {
      const rec = mediaRecRef.current;
      const stream = mediaStreamRef.current;
      const mime = mimeRef.current;
      const finish = () => {
        stream?.getTracks().forEach((t) => t.stop());
        mediaStreamRef.current = null;
        mediaRecRef.current = null;
        const blob = new Blob(chunksRef.current, { type: mime || "audio/webm" });
        chunksRef.current = [];
        resolve(blob);
      };
      if (!rec || rec.state === "inactive") {
        finish();
        return;
      }
      rec.onstop = () => finish();
      try {
        rec.stop();
      } catch {
        finish();
      }
    });
  }, []);

  const startBrowser = useCallback(() => {
    const Ctor = getSpeechRecognitionCtor();
    if (!Ctor) return;
    try {
      recRef.current?.abort();
    } catch {
      /* ignore */
    }
    try {
      const rec = new Ctor();
      rec.lang = "ru-RU";
      rec.continuous = true;
      rec.interimResults = true;
      if (typeof rec.maxAlternatives === "number") rec.maxAlternatives = 1;
      let finals = "";
      rec.onresult = (ev) => {
        const phase = snapRef.current.phase;
        // Keep the last words that arrive while recognition is shutting down.
        if (phase !== "recording" && phase !== "transcribing") return;
        let interim = "";
        for (let i = ev.resultIndex; i < ev.results.length; i++) {
          const piece = ev.results[i][0]?.transcript || "";
          if (ev.results[i].isFinal) finals = mergeField(finals, piece);
          else interim += piece;
        }
        const dictated = mergeField(finals, interim).trim();
        if (!dictated) return;
        liveRef.current = dictated;
        const text = mergeField(baseRef.current, dictated);
        publish(dictated, false);
        sendRef.current({ type: "partial", text });
      };
      rec.onerror = (ev) => {
        const code = ev.error || "";
        if (isBenignSttError(code) || code === "no-speech") return;
        // Keep recording. Batch recognition still runs after «Стоп».
      };
      rec.onend = () => {
        if (!activeRef.current) return;
        try {
          rec.start();
        } catch {
          /* streaming dropped; the recording continues */
        }
      };
      recRef.current = rec;
      rec.start();
    } catch {
      recRef.current = null;
    }
  }, [publish]);

  useEffect(() => {
    const hasBrowser = Boolean(getSpeechRecognitionCtor());
    const hasMedia = typeof navigator !== "undefined" && !!navigator.mediaDevices?.getUserMedia;
    setSupported(hasBrowser || hasMedia);
    return () => {
      activeRef.current = false;
      genRef.current += 1;
      if (timerRef.current) clearInterval(timerRef.current);
      if (levelRafRef.current != null) cancelAnimationFrame(levelRafRef.current);
      try {
        void audioCtxRef.current?.close();
      } catch {
        /* ignore */
      }
      try {
        recRef.current?.abort();
      } catch {
        /* ignore */
      }
      try {
        if (mediaRecRef.current && mediaRecRef.current.state !== "inactive") mediaRecRef.current.stop();
      } catch {
        /* ignore */
      }
      mediaStreamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  const stop = useCallback(
    async (opts?: { discard?: boolean }) => {
      if (opts?.discard) discardRef.current = true;
      if (snapRef.current.phase === "transcribing") return;
      if (snapRef.current.phase !== "recording" && !activeRef.current) return;
      if (stoppingRef.current) return;
      stoppingRef.current = true;
      const gen = genRef.current;
      activeRef.current = false;
      const hadRecorder = Boolean(mediaRecRef.current);
      stopTimer();
      stopLevelMeter();
      if (!hadRecorder) {
        try {
          recRef.current?.abort();
        } catch {
          /* ignore */
        }
        mediaStreamRef.current?.getTracks().forEach((t) => t.stop());
        mediaStreamRef.current = null;
        send({ type: "cancel" });
        stoppingRef.current = false;
        return;
      }
      send({ type: "stop" });
      try {
        await stopBrowser();
        const blob = await collectBlob();
        if (gen !== genRef.current) return;
        if (discardRef.current) {
          send({ type: "cancel" });
          return;
        }
        const live = liveRef.current.trim();
        if (live) {
          const text = mergeField(baseRef.current, live);
          publish(live, true);
          send({ type: "recognized", text });
          return;
        }
        const result = await transcribeBlob(blob);
        if (gen !== genRef.current || discardRef.current) {
          send({ type: "cancel" });
          return;
        }
        if (result.text) {
          const text = mergeField(baseRef.current, result.text);
          publish(result.text, true);
          send({ type: "recognized", text });
        } else {
          send({ type: "fail", message: result.error || sttErrorMessage("STT_EMPTY") });
        }
      } catch {
        if (gen === genRef.current && !discardRef.current) {
          send({ type: "fail", message: sttErrorMessage("network") });
        }
      } finally {
        stoppingRef.current = false;
      }
    },
    [collectBlob, publish, send, stopBrowser, stopLevelMeter, stopTimer, transcribeBlob],
  );

  const start = useCallback(
    async (currentFieldValue: string) => {
      if (snapRef.current.phase !== "idle") return;
      const gen = ++genRef.current;
      discardRef.current = false;
      stoppingRef.current = false;
      baseRef.current = currentFieldValue.trimEnd();
      liveRef.current = "";
      activeRef.current = true;
      send({ type: "start" });

      if (!navigator.mediaDevices?.getUserMedia) {
        activeRef.current = false;
        setSupported(false);
        send({ type: "fail", message: sttErrorMessage("unsupported") });
        return;
      }

      let stream: MediaStream;
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      } catch (err) {
        activeRef.current = false;
        if (gen !== genRef.current) return;
        send({ type: "fail", message: micFailure(err) });
        return;
      }
      if (!activeRef.current || gen !== genRef.current) {
        stream.getTracks().forEach((t) => t.stop());
        return;
      }

      mediaStreamRef.current = stream;
      startLevelMeter(stream);
      startTimer();
      const mime = pickMime();
      mimeRef.current = mime || "audio/webm";
      try {
        const recorder = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
        chunksRef.current = [];
        recorder.ondataavailable = (ev) => {
          if (ev.data?.size) chunksRef.current.push(ev.data);
        };
        mediaRecRef.current = recorder;
        recorder.start(500);
      } catch {
        activeRef.current = false;
        stopTimer();
        stopLevelMeter();
        stream.getTracks().forEach((t) => t.stop());
        mediaStreamRef.current = null;
        if (gen === genRef.current) send({ type: "fail", message: sttErrorMessage("audio-capture") });
        return;
      }
      startBrowser();
    },
    [send, startBrowser, startLevelMeter, startTimer, stopLevelMeter, stopTimer],
  );

  const toggle = useCallback(
    (currentFieldValue: string) => {
      if (snapRef.current.phase === "recording") {
        void stop();
        return;
      }
      if (snapRef.current.phase === "transcribing") return;
      void start(currentFieldValue);
    },
    [start, stop],
  );

  const clearError = useCallback(() => send({ type: "dismiss-error" }), [send]);

  return {
    phase: snap.phase,
    dictating: snap.phase === "recording",
    transcribing: snap.phase === "transcribing",
    supported,
    error: snap.error,
    level: snap.level,
    elapsedMs: snap.elapsedMs,
    /** Real streaming partials only — never a guessed transcript. */
    streaming: snap.streaming,
    start,
    stop,
    toggle,
    clearError,
  };
}
