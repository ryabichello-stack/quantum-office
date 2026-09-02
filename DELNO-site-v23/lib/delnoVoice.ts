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
  onerror: ((event: { error?: string }) => void) | null;
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
  listenSilenceMs?: number;
};

const DEFAULT_LISTEN_SILENCE_MS = 6500;

export function createVoiceController(options: VoiceSessionOptions) {
  const { onTranscript, onExchange, setPhase, audioRef } = options;
  const listenSilenceMs = options.listenSilenceMs ?? DEFAULT_LISTEN_SILENCE_MS;

  let engaged = false;
  let awaitingFollowUp = false;
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
  let promptMode = false;

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

  function stop() {
    turnId += 1;
    engaged = false;
    awaitingFollowUp = false;
    clearErrorTimer();
    clearMicRetryTimer();
    clearListenTimer();
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
    sessionResolve?.();
    sessionResolve = null;
  }

  function showError(userText: string, assistantText: string) {
    clearErrorTimer();
    setPhase("error");
    onExchange?.(userText, assistantText);
    errorTimer = window.setTimeout(() => stop(), 2600);
  }

  function armSilenceTimeout() {
    clearListenTimer();
    listenTimer = window.setTimeout(() => {
      if (engaged && !processing && !speaking) stop();
    }, listenSilenceMs);
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
      if (engaged && !processing && !speaking) startMic(false);
    }, 180);
  }

  function startMic(userInitiated: boolean) {
    if (!engaged || processing || speaking) return;

    const SpeechRecognition = getSpeechRecognition();
    if (!SpeechRecognition) {
      if (userInitiated || !awaitingFollowUp) {
        showError(
          "Голосовой режим",
          "Браузер не поддерживает распознавание речи. Используйте Chrome, Edge или Safari.",
        );
        return;
      }
      enterListenVisual();
      return;
    }

    clearErrorTimer();
    clearMicRetryTimer();
    heard = false;
    enterListenVisual();

    recognition?.stop();
    recognition = new SpeechRecognition();
    recognition.lang = "ru-RU";
    recognition.interimResults = false;
    recognition.continuous = false;

    recognition.onstart = () => {
      if (engaged) enterListenVisual();
    };

    recognition.onresult = (event) => {
      heard = true;
      clearListenTimer();
      clearMicRetryTimer();
      const transcript = event.results[0][0].transcript.trim();
      recognition?.stop();
      recognition = null;
      if (transcript) void answer(transcript);
      else scheduleMicRetry();
    };

    recognition.onerror = (event) => {
      recognition = null;
      if (!engaged || processing || speaking) return;
      const code = event?.error || "";
      const micBlocked =
        code === "not-allowed" || code === "service-not-allowed" || code === "audio-capture";

      if (micBlocked) {
        if (userInitiated || !awaitingFollowUp) {
          showError(
            "Голосовой режим",
            "Не удалось получить доступ к микрофону. Разрешите микрофон в браузере и нажмите на шар ещё раз.",
          );
          return;
        }
        enterListenVisual();
        return;
      }

      scheduleMicRetry();
    };

    recognition.onend = () => {
      recognition = null;
      if (!heard && !speaking && !processing && engaged) scheduleMicRetry();
    };

    try {
      recognition.start();
    } catch {
      if (!engaged) return;
      if (userInitiated || !awaitingFollowUp) {
        showError(
          "Голосовой режим",
          "Не удалось запустить микрофон. Попробуйте ещё раз через секунду.",
        );
        return;
      }
      enterListenVisual();
    }
  }

  function afterAnswerListen() {
    if (!engaged) return;
    awaitingFollowUp = true;
    speaking = false;
    processing = false;
    armSilenceTimeout();
    enterListenVisual();
    startMic(false);
  }

  async function answer(text: string) {
    const id = ++turnId;
    processing = true;
    clearListenTimer();
    clearMicRetryTimer();
    recognition?.stop();
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

    if (id !== turnId) return;
    processing = false;
    onExchange?.(text, reply);
    setPhase("speak");
    speaking = true;
    abortTts = new AbortController();

    let speakDone = false;
    const finishSpeak = () => {
      if (id !== turnId || speakDone) return;
      speakDone = true;
      speaking = false;
      if (!engaged && promptMode) engaged = true;
      if (engaged) afterAnswerListen();
      else stop();
    };

    const audio = audioRef.current;
    if (!audio) {
      finishSpeak();
      return;
    }

    const speakCap = window.setTimeout(finishSpeak, 15000);

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

  function toggle() {
    if (engaged) {
      clearErrorTimer();
      stop();
      return;
    }

    engaged = true;
    awaitingFollowUp = false;
    claimVoiceSession(stop);
    clearErrorTimer();
    armSilenceTimeout();
    startMic(true);
  }

  async function askText(text: string) {
    promptMode = true;
    if (engaged) {
      turnId += 1;
      clearListenTimer();
      clearMicRetryTimer();
      recognition?.stop();
      recognition = null;
      abortTts?.abort();
      abortTts = null;
      processing = false;
      speaking = false;
      heard = false;
    } else {
      engaged = true;
      claimVoiceSession(stop);
    }
    awaitingFollowUp = false;

    const sessionDone = new Promise<void>((resolve) => {
      sessionResolve = resolve;
    });

    await answer(text);

    if (engaged) await sessionDone;
    promptMode = false;
  }

  return {
    toggle,
    stop,
    askText,
    isActive: () => engaged,
  };
}
