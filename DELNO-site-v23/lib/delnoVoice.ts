import type { RefObject } from "react";
import { prepareTtsText } from "./ttsText";
import { getBasePath, widgetRealtimePath, widgetTtsPath } from "./widgetApi";

export type VoicePhase = "idle" | "listen" | "think" | "speak" | "error";

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

function speakWithBrowser(text: string): Promise<boolean> {
  if (typeof window === "undefined" || !window.speechSynthesis) return Promise.resolve(false);

  return new Promise((resolve) => {
    window.speechSynthesis.cancel();
    const utter = new SpeechSynthesisUtterance(prepareTtsText(text).slice(0, 500));
    utter.lang = "ru-RU";
    utter.rate = 1.02;
    let settled = false;
    const done = (ok: boolean) => {
      if (settled) return;
      settled = true;
      resolve(ok);
    };
    utter.onend = () => done(true);
    utter.onerror = () => done(false);
    window.speechSynthesis.speak(utter);
    window.setTimeout(() => done(false), 12000);
  });
}

/** @deprecated Realtime path handles mic directly; kept for compatibility. */
export function getSpeechRecognition() {
  return null;
}

export type VoiceSessionOptions = {
  onTranscript: (text: string) => Promise<string>;
  onExchange?: (userText: string, assistantText: string) => void;
  onPartial?: (text: string) => void;
  setPhase: (phase: VoicePhase) => void;
  audioRef: RefObject<HTMLAudioElement | null>;
  listenSilenceMs?: number;
};

type RealtimeEvent = {
  type: string;
  transcript?: string;
  delta?: string;
  error?: { message?: string };
};

function sanitizeRealtimeAnswerSdp(raw: string): string {
  const lines = raw.replace(/\r\n/g, "\n").replace(/\r/g, "\n").split("\n");
  const fixed: string[] = [];
  for (const line of lines) {
    if (!line) continue;
    if (line.startsWith("a=candidate:") && line.includes(" ufrag ")) {
      fixed.push(line.split(" ufrag ")[0]);
    } else {
      fixed.push(line);
    }
  }
  return `${fixed.join("\r\n")}\r\n`;
}

function canUseRealtime() {
  return (
    typeof window !== "undefined" &&
    typeof RTCPeerConnection !== "undefined" &&
    !!navigator.mediaDevices?.getUserMedia
  );
}

export function createVoiceController(options: VoiceSessionOptions) {
  const { onTranscript, onExchange, onPartial, setPhase, audioRef } = options;

  let engaged = false;
  let pc: RTCPeerConnection | null = null;
  let micStream: MediaStream | null = null;
  let dataChannel: RTCDataChannel | null = null;
  let lastUserText = "";
  let errorTimer: number | null = null;
  let turnId = 0;
  let abortTts: AbortController | null = null;
  let processing = false;
  let speaking = false;

  function clearErrorTimer() {
    if (errorTimer !== null) {
      window.clearTimeout(errorTimer);
      errorTimer = null;
    }
  }

  function showError(userText: string, assistantText: string) {
    clearErrorTimer();
    setPhase("error");
    onExchange?.(userText, assistantText);
    errorTimer = window.setTimeout(() => stop(), 5000);
  }

  function teardownRealtime() {
    try {
      dataChannel?.close();
    } catch {
      /* ignore */
    }
    try {
      pc?.close();
    } catch {
      /* ignore */
    }
    micStream?.getTracks().forEach((track) => track.stop());
    dataChannel = null;
    pc = null;
    micStream = null;
    const audio = audioRef.current;
    if (audio) {
      audio.pause();
      audio.srcObject = null;
      audio.removeAttribute("src");
      if (activeAudio === audio) activeAudio = null;
    }
  }

  async function processVoiceTurn(userText: string) {
    if (!engaged || processing || speaking || !userText.trim()) return;

    processing = true;
    const id = turnId;
    setPhase("think");
    onPartial?.(userText);

    let reply = "";
    try {
      reply = await onTranscript(userText);
    } catch {
      if (id !== turnId || !engaged) {
        processing = false;
        return;
      }
      processing = false;
      showError(userText, "Сейчас не удалось получить ответ. Попробуйте ещё раз.");
      return;
    }

    if (id !== turnId || !engaged) {
      processing = false;
      return;
    }
    if (!reply.trim()) {
      processing = false;
      showError(userText, "Не удалось получить ответ. Попробуйте переформулировать вопрос.");
      return;
    }

    await speakReply(userText, reply, { resumeListen: true });
    processing = false;
    lastUserText = "";
    if (engaged) onPartial?.("Говорите…");
  }

  function handleRealtimeEvent(event: RealtimeEvent) {
    if (!engaged) return;

    switch (event.type) {
      case "session.created":
        setPhase("listen");
        onPartial?.("Говорите…");
        break;
      case "input_audio_buffer.speech_started":
        if (!processing && !speaking) {
          setPhase("listen");
          onPartial?.("Слушаю…");
        }
        break;
      case "conversation.item.input_audio_transcription.delta": {
        const partial = (event.delta || event.transcript || "").trim();
        if (partial && !processing && !speaking) onPartial?.(partial);
        break;
      }
      case "conversation.item.input_audio_transcription.completed": {
        const userText = (event.transcript || "").trim();
        if (!userText || processing || speaking) break;
        lastUserText = userText;
        void processVoiceTurn(userText);
        break;
      }
      case "error":
        showError(
          lastUserText || "Голосовой режим",
          event.error?.message || "Ошибка голосового соединения. Попробуйте ещё раз.",
        );
        break;
      default:
        break;
    }
  }

  async function connectRealtime() {
    if (!canUseRealtime()) {
      throw new Error("webrtc unavailable");
    }

    setPhase("listen");
    onPartial?.("Подключаюсь…");

    const audio = audioRef.current;
    if (audio) await unlockAudioElement(audio);

    const connection = new RTCPeerConnection();
    pc = connection;

    // Transcription-only Realtime: answers play via site TTS + delno-api KB agent.
    connection.ontrack = (trackEvent) => {
      trackEvent.receiver.track.enabled = false;
    };

    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true },
    });
    if (!engaged) {
      stream.getTracks().forEach((track) => track.stop());
      throw new Error("cancelled");
    }
    micStream = stream;
    stream.getTracks().forEach((track) => connection.addTrack(track, stream));

    const channel = connection.createDataChannel("oai-events");
    dataChannel = channel;
    channel.onmessage = (messageEvent) => {
      try {
        handleRealtimeEvent(JSON.parse(String(messageEvent.data)) as RealtimeEvent);
      } catch {
        /* ignore malformed events */
      }
    };

    const offer = await connection.createOffer();
    await connection.setLocalDescription(offer);

    const response = await fetch(widgetRealtimePath(), {
      method: "POST",
      headers: { "Content-Type": "application/sdp" },
      body: offer.sdp || "",
      signal: AbortSignal.timeout(65000),
    });

    if (!response.ok) {
      const detail = (await response.text()).slice(0, 200);
      throw new Error(detail || `HTTP ${response.status}`);
    }

    const answerSdp = sanitizeRealtimeAnswerSdp(await response.text());
    await connection.setRemoteDescription({ type: "answer", sdp: answerSdp });

    setPhase("listen");
    onPartial?.("Говорите…");
  }

  function stop() {
    engaged = false;
    turnId += 1;
    processing = false;
    speaking = false;
    abortTts?.abort();
    abortTts = null;
    clearErrorTimer();
    teardownRealtime();
    window.speechSynthesis?.cancel();
    releaseVoiceSession(stop);
    setPhase("idle");
  }

  async function beginSession() {
    if (engaged) {
      stop();
      return;
    }

    engaged = true;
    claimVoiceSession(stop);
    clearErrorTimer();
    lastUserText = "";

    try {
      await connectRealtime();
    } catch (err) {
      engaged = false;
      teardownRealtime();
      releaseVoiceSession(stop);
      setPhase("error");
      const detail =
        err instanceof Error && err.message.includes("Permission")
          ? "Разрешите микрофон для сайта и нажмите на кристалл ещё раз."
          : err instanceof Error && err.message.trim()
            ? `Не удалось подключить голос Realtime: ${err.message.trim().slice(0, 180)}`
            : "Не удалось подключить голос Realtime. Используйте кнопки с вопросами ниже.";
      onExchange?.("Голосовой режим", detail);
      clearErrorTimer();
      errorTimer = window.setTimeout(() => setPhase("idle"), 5000);
    }
  }

  async function speakReply(
    userText: string,
    reply: string,
    opts?: { resumeListen?: boolean },
  ) {
    const id = turnId;
    onExchange?.(userText, reply);
    speaking = true;
    setPhase("speak");
    abortTts = new AbortController();

    let finished = false;
    const finishSpeak = () => {
      if (id !== turnId || finished) return;
      finished = true;
      speaking = false;
      if (opts?.resumeListen !== false && engaged) {
        setPhase("listen");
      } else {
        stop();
      }
    };

    const audio = audioRef.current;
    if (!audio) {
      void speakWithBrowser(reply).finally(finishSpeak);
      return;
    }

    void unlockAudioElement(audio);
    const cap = window.setTimeout(finishSpeak, 20000);

    let played = false;
    try {
      played = (await playDelnoTts(reply, audio, {
        onStart: () => {
          if (id === turnId) setPhase("speak");
        },
        onEnd: () => {
          window.clearTimeout(cap);
          finishSpeak();
        },
        onError: () => window.clearTimeout(cap),
        signal: abortTts.signal,
      })) as boolean;
    } catch {
      played = false;
    }

    if (!played && id === turnId && !finished) {
      await speakWithBrowser(reply);
      window.clearTimeout(cap);
      finishSpeak();
    }
  }

  async function askText(text: string, opts?: { resumeListen?: boolean }) {
    const trimmed = text.trim();
    if (!trimmed) return;

    stop();
    engaged = true;
    claimVoiceSession(stop);
    clearErrorTimer();
    processing = true;
    setPhase("think");

    const id = ++turnId;
    let reply = "";
    try {
      reply = await onTranscript(trimmed);
    } catch {
      if (id !== turnId) return;
      showError(trimmed, "Сейчас не удалось получить ответ. Попробуйте ещё раз.");
      return;
    }

    if (id !== turnId) return;
    if (!reply.trim()) {
      showError(trimmed, "Не удалось получить ответ. Попробуйте переформулировать вопрос.");
      return;
    }

    processing = false;
    await speakReply(trimmed, reply, { resumeListen: opts?.resumeListen ?? false });
  }

  return {
    toggle: () => void beginSession(),
    stop,
    askText,
    isActive: () => engaged,
  };
}
