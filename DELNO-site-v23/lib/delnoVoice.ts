import type { RefObject } from "react";
import { getBasePath, widgetTtsPath } from "./widgetApi";

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

let sharedAudioContext: AudioContext | null = null;

/** Unlock audio playback while we still have a user-gesture (orb click). */
export async function unlockAudioElement(audio: HTMLAudioElement) {
  try {
    const AudioCtx =
      typeof window !== "undefined"
        ? window.AudioContext ||
          (window as Window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
        : null;
    if (AudioCtx) {
      if (!sharedAudioContext) sharedAudioContext = new AudioCtx();
      if (sharedAudioContext.state === "suspended") await sharedAudioContext.resume();
    }
  } catch {
    /* ignore */
  }

  try {
    audio.muted = true;
    audio.src =
      "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAAB9AAACABAAZGF0YQAAAAA=";
    await Promise.race([
      audio.play(),
      new Promise<void>((_, reject) => window.setTimeout(() => reject(new Error("unlock timeout")), 1500)),
    ]);
    audio.pause();
    audio.removeAttribute("src");
    audio.load();
    audio.muted = false;
  } catch {
    audio.muted = false;
  }
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
      const cleanup = () => {
        URL.revokeObjectURL(url);
        if (activeAudio === audio) activeAudio = null;
      };
      audio.onplaying = () => callbacks.onStart?.();
      audio.onended = () => {
        cleanup();
        callbacks.onEnd?.();
        resolve();
      };
      audio.onerror = () => {
        cleanup();
        callbacks.onError?.();
        reject(new Error("audio playback failed"));
      };
      const tryPlay = async () => {
        try {
          await audio.play();
        } catch {
          audio.currentTime = 0;
          await audio.play();
        }
      };
      void tryPlay().catch((err) => {
        cleanup();
        reject(err);
      });
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
  listenSilenceMs?: number;
};

const DEFAULT_LISTEN_SILENCE_MS = 8000;

export function createVoiceController(options: VoiceSessionOptions) {
  const { onTranscript, onExchange, setPhase, audioRef } = options;
  const listenSilenceMs = options.listenSilenceMs ?? DEFAULT_LISTEN_SILENCE_MS;

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
  let sessionResolve: (() => void) | null = null;
  let pendingTranscript = "";

  function clearErrorTimer() {
    if (errorTimer !== null) {
      window.clearTimeout(errorTimer);
      errorTimer = null;
    }
  }

  function clearMicRetryTimer() {
    if (micRetryTimer !== null) {
      window.clearTimeout(micRetryTimer);
      micRetryTimer = null;
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

  function interruptTurn() {
    turnId += 1;
    pendingTranscript = "";
    clearListenTimer();
    clearMicRetryTimer();
    recognition?.abort();
    recognition = null;
    abortTts?.abort();
    abortTts = null;
    processing = false;
    speaking = false;
    heard = false;
  }

  function stop() {
    interruptTurn();
    engaged = false;
    clearErrorTimer();
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.removeAttribute("src");
      if (activeAudio === audioRef.current) activeAudio = null;
    }
    window.speechSynthesis?.cancel();
    releaseVoiceSession(stop);
    setPhase("idle");
    sessionResolve?.();
    sessionResolve = null;
  }

  function showError(userText: string, assistantText: string) {
    clearErrorTimer();
    setPhase("error");
    onExchange?.(userText, assistantText);
    errorTimer = window.setTimeout(() => stop(), 3000);
  }

  function enterListenVisual() {
    if (!engaged) return;
    setPhase("listen");
  }

  function scheduleMicRetry() {
    if (!engaged || processing || speaking) return;
    clearMicRetryTimer();
    micRetryTimer = window.setTimeout(() => {
      micRetryTimer = null;
      if (engaged && !processing && !speaking) startMic();
    }, 250);
  }

  function finalizeTranscript(raw: string) {
    const text = raw.trim();
    if (!text || !engaged || processing || speaking) return;
    pendingTranscript = "";
    heard = true;
    clearListenTimer();
    clearMicRetryTimer();
    recognition?.stop();
    recognition = null;
    void answer(text, { fromMic: true });
  }

  function startMic() {
    if (!engaged || processing || speaking) return;

    const SpeechRecognition = getSpeechRecognition();
    if (!SpeechRecognition) {
      showError(
        "Голосовой режим",
        "Браузер не поддерживает распознавание речи. Используйте Chrome, Edge или Safari.",
      );
      return;
    }

    clearErrorTimer();
    clearMicRetryTimer();
    heard = false;
    pendingTranscript = "";
    enterListenVisual();
    resetListenTimer();

    recognition?.abort();
    recognition = new SpeechRecognition();
    recognition.lang = "ru-RU";
    recognition.interimResults = true;
    recognition.continuous = true;

    recognition.onstart = () => {
      if (engaged) enterListenVisual();
    };

    recognition.onresult = (event) => {
      if (!engaged || processing || speaking) return;
      heard = true;
      resetListenTimer();

      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i];
        if (result.isFinal) {
          pendingTranscript = `${pendingTranscript} ${result[0].transcript}`.trim();
        }
      }
    };

    recognition.onerror = (event) => {
      recognition = null;
      if (!engaged || processing || speaking) return;
      const code = event?.error || "";

      if (code === "not-allowed" || code === "service-not-allowed" || code === "audio-capture") {
        showError(
          "Голосовой режим",
          "Не удалось получить доступ к микрофону. Разрешите микрофон в браузере и нажмите на шар ещё раз.",
        );
        return;
      }

      if (code === "no-speech" && pendingTranscript.trim()) {
        finalizeTranscript(pendingTranscript);
        return;
      }

      if (code !== "aborted") scheduleMicRetry();
    };

    recognition.onend = () => {
      recognition = null;
      if (pendingTranscript.trim() && engaged && !processing && !speaking) {
        finalizeTranscript(pendingTranscript);
        return;
      }
      if (!heard && engaged && !processing && !speaking) scheduleMicRetry();
    };

    try {
      recognition.start();
    } catch {
      scheduleMicRetry();
    }
  }

  function resumeListenAfterAnswer() {
    if (!engaged) return;
    speaking = false;
    processing = false;
    enterListenVisual();
    resetListenTimer();
    window.setTimeout(() => {
      if (engaged && !processing && !speaking) startMic();
    }, 200);
  }

  async function answer(
    text: string,
    options?: { fromMic?: boolean; resumeListen?: boolean },
  ) {
    const id = ++turnId;
    processing = true;
    clearListenTimer();
    clearMicRetryTimer();
    recognition?.abort();
    recognition = null;
    pendingTranscript = "";
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
    if (!reply.trim()) {
      processing = false;
      showError(text, "Не удалось получить ответ. Попробуйте переформулировать вопрос.");
      return;
    }

    processing = false;
    onExchange?.(text, reply);
    setPhase("speak");
    speaking = true;
    abortTts = new AbortController();

    let speakDone = false;
    const finishSpeak = () => {
      if (id !== turnId || speakDone) return;
      speakDone = true;
      if (engaged && options?.resumeListen !== false) resumeListenAfterAnswer();
      else stop();
    };

    const audio = audioRef.current;
    if (!audio) {
      finishSpeak();
      return;
    }

    // Brief gap only after mic capture — not for text prompts (keeps user-gesture chain).
    if (options?.fromMic) {
      await new Promise<void>((resolve) => window.setTimeout(resolve, 80));
      if (id !== turnId) return;
    }

    const speakCap = window.setTimeout(finishSpeak, 20000);

    await playDelnoTts(reply, audio, {
      onStart: () => {
        if (id === turnId) setPhase("speak");
      },
      onEnd: () => {
        window.clearTimeout(speakCap);
        finishSpeak();
      },
      onError: () => {
        window.clearTimeout(speakCap);
        finishSpeak();
      },
      signal: abortTts.signal,
    });

    if (id !== turnId || speakDone) return;
    if (!abortTts.signal.aborted) {
      window.clearTimeout(speakCap);
      finishSpeak();
    }
  }

  function beginSession() {
    if (engaged) {
      clearErrorTimer();
      stop();
      return;
    }

    engaged = true;
    claimVoiceSession(stop);
    clearErrorTimer();

    const audio = audioRef.current;
    if (audio) void unlockAudioElement(audio);

    resetListenTimer();
    startMic();
  }

  function toggle() {
    if (engaged) {
      clearErrorTimer();
      stop();
      return;
    }
    beginSession();
  }

  async function askText(text: string, options?: { resumeListen?: boolean }) {
    const trimmed = text.trim();
    if (!trimmed) return;

    interruptTurn();
    engaged = true;
    claimVoiceSession(stop);
    clearErrorTimer();
    setPhase("think");

    await answer(trimmed, { fromMic: false, resumeListen: options?.resumeListen });
  }

  return {
    toggle,
    stop,
    askText,
    isActive: () => engaged,
  };
}
