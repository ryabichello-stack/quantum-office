import type { RefObject } from "react";

export type VoicePhase = "idle" | "listen" | "think" | "speak" | "error";

type SpeechRecognitionResultEvent = {
  results: {
    length: number;
    [index: number]: { isFinal: boolean; 0: { transcript: string }; length: number };
  };
  resultIndex: number;
};

type SpeechRecognitionInstance = {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onstart: (() => void) | null;
  onresult: ((event: SpeechRecognitionResultEvent) => void) | null;
  onerror: ((event: { error?: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
};

type SpeechRecognitionConstructor = new () => SpeechRecognitionInstance;

type SpeechWindow = Window & {
  SpeechRecognition?: SpeechRecognitionConstructor;
  webkitSpeechRecognition?: SpeechRecognitionConstructor;
};

const ORB_CDN =
  process.env.NEXT_PUBLIC_DELNO_ORB_URL ||
  "https://cdn.dlno.ru/widget/v1/assets/crystal-orb-static.webp";

const TTS_URL = process.env.NEXT_PUBLIC_DELNO_TTS_URL || "";

export function orbAssetPath() {
  return ORB_CDN;
}

export function getSpeechRecognition() {
  if (typeof window === "undefined") return null;
  const speechWindow = window as SpeechWindow;
  return speechWindow.SpeechRecognition || speechWindow.webkitSpeechRecognition || null;
}

export async function unlockAudioElement(audio: HTMLAudioElement) {
  try {
    audio.muted = true;
    audio.src =
      "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAAB9AAACABAAZGF0YQAAAAA=";
    await audio.play().catch(() => undefined);
    audio.pause();
    audio.removeAttribute("src");
    audio.load();
    audio.muted = false;
  } catch {
    audio.muted = false;
  }
}

function speakWithBrowser(text: string): Promise<void> {
  return new Promise((resolve, reject) => {
    if (typeof window === "undefined" || !window.speechSynthesis) {
      reject(new Error("no speech synthesis"));
      return;
    }
    window.speechSynthesis.cancel();
    const utter = new SpeechSynthesisUtterance(text);
    utter.lang = "ru-RU";
    utter.onend = () => resolve();
    utter.onerror = () => reject(new Error("speech synthesis failed"));
    window.speechSynthesis.speak(utter);
  });
}

export async function playOperatorTts(
  text: string,
  audio: HTMLAudioElement,
  callbacks: {
    onStart?: () => void;
    onEnd?: () => void;
    onError?: () => void;
    signal?: AbortSignal;
  },
) {
  if (callbacks.signal?.aborted) return false;

  if (TTS_URL) {
    try {
      const url = `${TTS_URL}${TTS_URL.includes("?") ? "&" : "?"}text=${encodeURIComponent(text.slice(0, 800))}`;
      const response = await fetch(url, { signal: callbacks.signal });
      if (response.ok) {
        const blob = await response.blob();
        const objectUrl = URL.createObjectURL(blob);
        audio.src = objectUrl;
        await new Promise<void>((resolve, reject) => {
          audio.onplaying = () => callbacks.onStart?.();
          audio.onended = () => {
            URL.revokeObjectURL(objectUrl);
            callbacks.onEnd?.();
            resolve();
          };
          audio.onerror = () => {
            URL.revokeObjectURL(objectUrl);
            reject(new Error("audio failed"));
          };
          void audio.play().catch(reject);
        });
        return true;
      }
    } catch {
      /* fallback below */
    }
  }

  try {
    callbacks.onStart?.();
    await speakWithBrowser(text);
    callbacks.onEnd?.();
    return true;
  } catch {
    callbacks.onError?.();
    return false;
  }
}

export type VoiceSessionOptions = {
  onTranscript: (text: string) => Promise<string>;
  onExchange?: (userText: string, assistantText: string) => void;
  setPhase: (phase: VoicePhase) => void;
  audioRef: RefObject<HTMLAudioElement | null>;
  listenSilenceMs?: number;
};

export function createVoiceController(options: VoiceSessionOptions) {
  const { onTranscript, onExchange, setPhase, audioRef } = options;
  const listenSilenceMs = options.listenSilenceMs ?? 8000;

  let engaged = false;
  let recognition: SpeechRecognitionInstance | null = null;
  let heard = false;
  let speaking = false;
  let processing = false;
  let turnId = 0;
  let abortTts: AbortController | null = null;
  let errorTimer: number | null = null;
  let listenTimer: number | null = null;
  let micRetryTimer: number | null = null;

  function clearErrorTimer() {
    if (errorTimer !== null) {
      window.clearTimeout(errorTimer);
      errorTimer = null;
    }
  }

  function clearListenTimer() {
    if (listenTimer !== null) {
      window.clearTimeout(listenTimer);
      listenTimer = null;
    }
  }

  function resetListenTimer() {
    clearListenTimer();
    listenTimer = window.setTimeout(() => {
      if (engaged && !processing && !speaking) stop();
    }, listenSilenceMs);
  }

  function stop() {
    turnId += 1;
    clearListenTimer();
    recognition?.abort();
    recognition = null;
    abortTts?.abort();
    abortTts = null;
    processing = false;
    speaking = false;
    heard = false;
    engaged = false;
    clearErrorTimer();
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.removeAttribute("src");
    }
    window.speechSynthesis?.cancel();
    setPhase("idle");
  }

  function showError(userText: string, assistantText: string) {
    clearErrorTimer();
    setPhase("error");
    onExchange?.(userText, assistantText);
    errorTimer = window.setTimeout(() => stop(), 3000);
  }

  async function answer(text: string, fromMic = false) {
    const id = ++turnId;
    processing = true;
    clearListenTimer();
    recognition?.abort();
    recognition = null;
    setPhase("think");

    let reply = "";
    try {
      reply = await onTranscript(text);
    } catch {
      processing = false;
      if (id !== turnId) return;
      showError(text, "Сейчас не удалось получить ответ. Попробуйте ещё раз.");
      return;
    }

    if (id !== turnId || !reply.trim()) {
      processing = false;
      showError(text, "Не удалось получить ответ.");
      return;
    }

    processing = false;
    onExchange?.(text, reply);
    speaking = true;
    abortTts = new AbortController();

    const audio = audioRef.current;
    if (!audio) {
      speaking = false;
      if (engaged) {
        setPhase("listen");
        startMic();
      } else {
        stop();
      }
      return;
    }

    if (fromMic) await new Promise((r) => window.setTimeout(r, 80));

    await playOperatorTts(reply, audio, {
      onStart: () => {
        if (id === turnId) setPhase("speak");
      },
      onEnd: () => {
        speaking = false;
        if (engaged) {
          setPhase("listen");
          startMic();
        } else {
          stop();
        }
      },
      onError: () => {
        speaking = false;
        if (engaged) {
          setPhase("listen");
          startMic();
        } else {
          stop();
        }
      },
      signal: abortTts.signal,
    });
  }

  function startMic() {
    if (!engaged || processing || speaking) return;
    const SpeechRecognition = getSpeechRecognition();
    if (!SpeechRecognition) {
      showError("Голос", "Браузер не поддерживает распознавание речи.");
      return;
    }

    heard = false;
    setPhase("listen");
    resetListenTimer();
    recognition?.abort();
    recognition = new SpeechRecognition();
    recognition.lang = "ru-RU";
    recognition.interimResults = true;
    recognition.continuous = true;

    let pending = "";
    recognition.onresult = (event) => {
      if (!engaged || processing || speaking) return;
      heard = true;
      resetListenTimer();
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        if (event.results[i].isFinal) {
          pending = `${pending} ${event.results[i][0].transcript}`.trim();
        }
      }
    };

    recognition.onerror = () => {
      recognition = null;
    };

    recognition.onend = () => {
      recognition = null;
      if (pending && engaged && !processing && !speaking) {
        void answer(pending, true);
        pending = "";
      }
    };

    try {
      recognition.start();
    } catch {
      /* ignore */
    }
  }

  function toggle() {
    if (engaged) {
      stop();
      return;
    }
    engaged = true;
    if (audioRef.current) void unlockAudioElement(audioRef.current);
    startMic();
  }

  return { toggle, stop, isActive: () => engaged };
}
