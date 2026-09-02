import type { RefObject } from "react";
import { getBasePath, widgetTtsPath } from "./widgetApi";

export type VoicePhase = "idle" | "listen" | "think" | "speak" | "error";

type SpeechRecognitionResultEvent = {
  results: ArrayLike<ArrayLike<{ transcript: string }>>;
};

type SpeechRecognitionInstance = {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onstart: (() => void) | null;
  onresult: ((event: SpeechRecognitionResultEvent) => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
};

type SpeechRecognitionConstructor = new () => SpeechRecognitionInstance;

type SpeechWindow = Window & {
  SpeechRecognition?: SpeechRecognitionConstructor;
  webkitSpeechRecognition?: SpeechRecognitionConstructor;
};

export function orbAssetPath() {
  return `${getBasePath()}/widget/assets/crystal-orb-static.webp`;
}

export async function playDelnoTts(
  text: string,
  audio: HTMLAudioElement,
  callbacks: {
    onStart?: () => void;
    onEnd?: () => void;
    onError?: () => void;
    signal?: AbortSignal;
  },
) {
  const controller = new AbortController();
  const onAbort = () => controller.abort();
  callbacks.signal?.addEventListener("abort", onAbort);

  try {
    const response = await fetch(widgetTtsPath(text), { signal: controller.signal });
    if (!response.ok) throw new Error("tts failed");
    const blob = await response.blob();
    if (controller.signal.aborted) return false;

    const url = URL.createObjectURL(blob);
    audio.muted = false;
    audio.src = url;

    await new Promise<void>((resolve, reject) => {
      audio.onplaying = () => callbacks.onStart?.();
      audio.onended = () => {
        URL.revokeObjectURL(url);
        callbacks.onEnd?.();
        resolve();
      };
      audio.onerror = () => {
        URL.revokeObjectURL(url);
        callbacks.onError?.();
        reject(new Error("audio playback failed"));
      };
      void audio.play().catch(reject);
    });
    return true;
  } catch {
    callbacks.onError?.();
    return false;
  } finally {
    callbacks.signal?.removeEventListener("abort", onAbort);
  }
}

export function getSpeechRecognition() {
  if (typeof window === "undefined") return null;
  const speechWindow = window as SpeechWindow;
  return speechWindow.SpeechRecognition || speechWindow.webkitSpeechRecognition || null;
}

export type VoiceSessionOptions = {
  onTranscript: (text: string) => Promise<string>;
  onExchange?: (userText: string, assistantText: string) => void;
  setPhase: (phase: VoicePhase) => void;
  audioRef: RefObject<HTMLAudioElement | null>;
};

export function createVoiceController(options: VoiceSessionOptions) {
  const { onTranscript, onExchange, setPhase, audioRef } = options;
  let recognition: SpeechRecognitionInstance | null = null;
  let heard = false;
  let speaking = false;
  let abortTts: AbortController | null = null;

  function stop() {
    recognition?.stop();
    recognition = null;
    abortTts?.abort();
    abortTts = null;
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.removeAttribute("src");
    }
    window.speechSynthesis?.cancel();
    speaking = false;
    setPhase("idle");
  }

  async function answer(text: string) {
    setPhase("think");
    const reply = await onTranscript(text);
    onExchange?.(text, reply);
    setPhase("speak");
    speaking = true;
    abortTts = new AbortController();
    const audio = audioRef.current;
    if (!audio) {
      speaking = false;
      setPhase("idle");
      return;
    }
    const ok = await playDelnoTts(reply, audio, {
      onStart: () => setPhase("speak"),
      onEnd: () => {
        speaking = false;
        stop();
      },
      onError: () => {
        speaking = false;
        setPhase("error");
        window.setTimeout(() => stop(), 1200);
      },
      signal: abortTts.signal,
    });
    if (!ok && !abortTts.signal.aborted) {
      speaking = false;
      setPhase("error");
      window.setTimeout(() => stop(), 1200);
    }
  }

  function toggle() {
    if (recognition || speaking) {
      stop();
      return;
    }

    const SpeechRecognition = getSpeechRecognition();
    if (!SpeechRecognition) {
      setPhase("error");
      onExchange?.(
        "Голосовой режим",
        "Браузер не поддерживает распознавание речи. Используйте Chrome, Edge или Safari.",
      );
      window.setTimeout(() => stop(), 2400);
      return;
    }

    heard = false;
    setPhase("listen");
    recognition = new SpeechRecognition();
    recognition.lang = "ru-RU";
    recognition.interimResults = false;
    recognition.continuous = false;
    recognition.onstart = () => setPhase("listen");
    recognition.onresult = (event) => {
      heard = true;
      const transcript = event.results[0][0].transcript.trim();
      recognition = null;
      void answer(transcript);
    };
    recognition.onerror = () => {
      heard = true;
      recognition = null;
      setPhase("error");
      onExchange?.(
        "Голосовой режим",
        "Не удалось получить доступ к микрофону. Разрешите микрофон в браузере и нажмите на шар ещё раз.",
      );
      window.setTimeout(() => stop(), 2600);
    };
    recognition.onend = () => {
      recognition = null;
      if (!heard && !speaking) stop();
    };
    recognition.start();
  }

  return { toggle, stop, isActive: () => Boolean(recognition || speaking) };
}
