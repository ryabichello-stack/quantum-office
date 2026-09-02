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
  /** How long to wait in listen mode without speech before ending the session. */
  listenSilenceMs?: number;
};

const DEFAULT_LISTEN_SILENCE_MS = 6500;

export function createVoiceController(options: VoiceSessionOptions) {
  const { onTranscript, onExchange, setPhase, audioRef } = options;
  const listenSilenceMs = options.listenSilenceMs ?? DEFAULT_LISTEN_SILENCE_MS;
  let recognition: SpeechRecognitionInstance | null = null;
  let heard = false;
  let speaking = false;
  let processing = false;
  let sessionActive = false;
  let awaitingFollowUp = false;
  let turnId = 0;
  let abortTts: AbortController | null = null;
  let errorTimer: number | null = null;
  let listenTimer: number | null = null;
  let listenPoll: number | null = null;
  let listenDeadline = 0;

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
    if (listenPoll !== null) {
      window.clearInterval(listenPoll);
      listenPoll = null;
    }
  }

  function clearListenWindow() {
    clearListenTimer();
    listenDeadline = 0;
  }

  function beginListenWindow() {
    clearListenTimer();
    listenDeadline = Date.now() + listenSilenceMs;
    listenTimer = window.setTimeout(() => {
      if (sessionActive && !processing && !speaking) stop();
    }, listenSilenceMs);
    listenPoll = window.setInterval(() => {
      if (!sessionActive || processing || speaking) return;
      if (listenDeadline && Date.now() >= listenDeadline) stop();
    }, 400);
  }

  function stop() {
    turnId += 1;
    sessionActive = false;
    awaitingFollowUp = false;
    clearErrorTimer();
    clearListenWindow();
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
    sessionActive = false;
    awaitingFollowUp = false;
    setPhase("error");
    onExchange?.(userText, assistantText);
    errorTimer = window.setTimeout(() => stop(), 2600);
  }

  function enterListenMode() {
    if (!sessionActive) return;
    setPhase("listen");
  }

  function afterAnswerListen() {
    if (!sessionActive) return;
    awaitingFollowUp = true;
    speaking = false;
    processing = false;
    beginListenWindow();
    enterListenMode();
    startListening();
  }

  function resumeListening() {
    if (!sessionActive || processing || speaking) return;
    if (listenDeadline && Date.now() >= listenDeadline) {
      stop();
      return;
    }
    startListening();
  }

  function startListening() {
    if (!sessionActive || processing || speaking) return;

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

    recognition?.stop();
    recognition = new SpeechRecognition();
    recognition.lang = "ru-RU";
    recognition.interimResults = false;
    recognition.continuous = false;
    recognition.onstart = () => {
      if (sessionActive) setPhase("listen");
    };
    recognition.onresult = (event) => {
      heard = true;
      const transcript = event.results[0][0].transcript.trim();
      recognition?.stop();
      recognition = null;
      if (transcript) {
        clearListenWindow();
        void answer(transcript);
      } else {
        resumeListening();
      }
    };
    recognition.onerror = (event) => {
      recognition = null;
      if (!sessionActive || processing || speaking) return;
      const code = event?.error || "";
      if (code === "not-allowed" || code === "service-not-allowed" || code === "audio-capture") {
        if (awaitingFollowUp && listenDeadline && Date.now() < listenDeadline) {
          enterListenMode();
          return;
        }
        showError(
          "Голосовой режим",
          "Не удалось получить доступ к микрофону. Разрешите микрофон в браузере и нажмите на шар ещё раз.",
        );
        return;
      }
      resumeListening();
    };
    recognition.onend = () => {
      recognition = null;
      if (!heard && !speaking && !processing && sessionActive) resumeListening();
    };

    try {
      recognition.start();
    } catch {
      if (!sessionActive) return;
      if (awaitingFollowUp && listenDeadline && Date.now() < listenDeadline) {
        enterListenMode();
        return;
      }
      showError(
        "Голосовой режим",
        "Не удалось запустить микрофон. Попробуйте ещё раз через секунду.",
      );
    }
  }

  async function answer(text: string) {
    const id = ++turnId;
    processing = true;
    clearListenWindow();
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

    const finishSpeak = () => {
      if (id !== turnId) return;
      speaking = false;
      if (sessionActive) afterAnswerListen();
      else stop();
    };

    const audio = audioRef.current;
    if (!audio) {
      finishSpeak();
      return;
    }

    const speakCap = window.setTimeout(finishSpeak, 15000);

    const ok = await playDelnoTts(reply, audio, {
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

    if (id !== turnId) return;

    if (!ok && !abortTts.signal.aborted) {
      window.clearTimeout(speakCap);
      finishSpeak();
    }
  }

  function toggle() {
    if (sessionActive) {
      stop();
      return;
    }

    sessionActive = true;
    awaitingFollowUp = false;
    claimVoiceSession(stop);
    clearErrorTimer();
    beginListenWindow();
    startListening();
  }

  async function askText(text: string) {
    if (sessionActive) {
      turnId += 1;
      clearListenWindow();
      recognition?.stop();
      recognition = null;
      abortTts?.abort();
      abortTts = null;
      processing = false;
      speaking = false;
      heard = false;
    } else {
      sessionActive = true;
      claimVoiceSession(stop);
    }
    await answer(text);
  }

  return {
    toggle,
    stop,
    askText,
    isActive: () => sessionActive || Boolean(recognition || speaking || processing),
  };
}
