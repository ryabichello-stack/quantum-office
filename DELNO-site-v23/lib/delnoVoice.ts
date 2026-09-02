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

let activeAudio: HTMLAudioElement | null = null;
let activeVoiceStop: (() => void) | null = null;

function claimVoiceSession(stop: () => void) {
  if (activeVoiceStop && activeVoiceStop !== stop) activeVoiceStop();
  activeVoiceStop = stop;
}

function releaseVoiceSession(stop: () => void) {
  if (activeVoiceStop === stop) activeVoiceStop = null;
}

export function orbAssetPath() {
  return `${getBasePath()}/widget/assets/crystal-orb-static.webp`;
}

function pauseOtherAudio(except?: HTMLAudioElement) {
  if (activeAudio && activeAudio !== except) {
    activeAudio.pause();
    activeAudio.removeAttribute("src");
  }
  window.speechSynthesis?.cancel();
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
    pauseOtherAudio(audio);
    activeAudio = audio;

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
        if (activeAudio === audio) activeAudio = null;
        callbacks.onEnd?.();
        resolve();
      };
      audio.onerror = () => {
        URL.revokeObjectURL(url);
        if (activeAudio === audio) activeAudio = null;
        callbacks.onError?.();
        reject(new Error("audio playback failed"));
      };
      void audio.play().catch(reject);
    });
    return true;
  } catch {
    if (activeAudio === audio) activeAudio = null;
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
  let processing = false;
  let turnId = 0;
  let abortTts: AbortController | null = null;
  let errorTimer: number | null = null;

  function clearErrorTimer() {
    if (errorTimer !== null) {
      window.clearTimeout(errorTimer);
      errorTimer = null;
    }
  }

  function stop() {
    turnId += 1;
    clearErrorTimer();
    recognition?.stop();
    recognition = null;
    abortTts?.abort();
    abortTts = null;
    processing = false;
    speaking = false;
    heard = false;
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.removeAttribute("src");
      if (activeAudio === audioRef.current) activeAudio = null;
    }
    window.speechSynthesis?.cancel();
    releaseVoiceSession(stop);
    setPhase("idle");
  }

  function showError(userText: string, assistantText: string) {
    clearErrorTimer();
    setPhase("error");
    onExchange?.(userText, assistantText);
    errorTimer = window.setTimeout(() => stop(), 2600);
  }

  async function answer(text: string) {
    const id = ++turnId;
    processing = true;
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

    if (id !== turnId) return;
    processing = false;
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
      onStart: () => {
        if (id === turnId) setPhase("speak");
      },
      onEnd: () => {
        if (id !== turnId) return;
        speaking = false;
        stop();
      },
      onError: () => {
        if (id !== turnId) return;
        speaking = false;
        showError(text, reply);
      },
      signal: abortTts.signal,
    });

    if (id !== turnId) return;

    if (!ok && !abortTts.signal.aborted) {
      speaking = false;
      showError(text, reply);
    }
  }

  function toggle() {
    if (recognition || speaking || processing) {
      stop();
      return;
    }

    claimVoiceSession(stop);

    const SpeechRecognition = getSpeechRecognition();
    if (!SpeechRecognition) {
      showError(
        "Голосовой режим",
        "Браузер не поддерживает распознавание речи. Используйте Chrome, Edge или Safari.",
      );
      return;
    }

    clearErrorTimer();
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
      showError(
        "Голосовой режим",
        "Не удалось получить доступ к микрофону. Разрешите микрофон в браузере и нажмите на шар ещё раз.",
      );
    };
    recognition.onend = () => {
      recognition = null;
      if (!heard && !speaking && !processing) stop();
    };

    try {
      recognition.start();
    } catch {
      showError(
        "Голосовой режим",
        "Не удалось запустить микрофон. Попробуйте ещё раз через секунду.",
      );
    }
  }

  async function askText(text: string) {
    if (recognition || speaking || processing) stop();
    claimVoiceSession(stop);
    await answer(text);
  }

  return { toggle, stop, askText, isActive: () => Boolean(recognition || speaking || processing) };
}
