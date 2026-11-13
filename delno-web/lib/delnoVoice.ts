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

const API_URL = process.env.NEXT_PUBLIC_DELNO_API_URL || "http://127.0.0.1:18020";

function ttsEndpoint(text: string, token?: string) {
  const base = `${API_URL}/v1/operator/tts?text=${encodeURIComponent(text.slice(0, 800))}`;
  return { url: base, token };
}

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
    token?: string;
  },
) {
  if (callbacks.signal?.aborted) return false;

  if (callbacks.token) {
    try {
      const { url } = ttsEndpoint(text, callbacks.token);
      const response = await fetch(url, {
        signal: callbacks.signal,
        headers: {
          Authorization: `Bearer ${callbacks.token}`,
          Accept: "audio/mpeg",
        },
      });
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

  const legacyUrl = process.env.NEXT_PUBLIC_DELNO_TTS_URL || "";
  if (legacyUrl) {
    try {
      const url = `${legacyUrl}${legacyUrl.includes("?") ? "&" : "?"}text=${encodeURIComponent(text.slice(0, 800))}`;
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
  authToken?: string;
};

export function createVoiceController(options: VoiceSessionOptions) {
  const { onTranscript, onExchange, setPhase, audioRef, authToken } = options;
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
      token: authToken,
    });
  }

  async function startServerListen() {
    if (!engaged || processing || speaking) return;
    if (!authToken || !navigator.mediaDevices?.getUserMedia) {
      showError("Голос", "Нужен микрофон и сессия для голосового режима.");
      return;
    }
    heard = false;
    setPhase("listen");
    resetListenTimer();
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : "audio/webm";
      const recorder = new MediaRecorder(stream, { mimeType: mime });
      const chunks: Blob[] = [];
      recorder.ondataavailable = (ev) => {
        if (ev.data.size) chunks.push(ev.data);
      };
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunks, { type: mime });
        if (!blob.size || !engaged) return;
        try {
          const form = new FormData();
          form.append("file", blob, "voice.webm");
          const res = await fetch(`${API_URL}/v1/operator/stt`, {
            method: "POST",
            headers: { Authorization: `Bearer ${authToken}` },
            body: form,
          });
          if (!res.ok) {
            // Silence / STT_EMPTY: keep the dialogue loop (ChatGPT-class), do not kill the session.
            let detail = "";
            try {
              const errBody = (await res.json()) as { detail?: string };
              detail = String(errBody.detail || "");
            } catch {
              /* ignore */
            }
            if (engaged && (res.status === 400 || detail === "STT_EMPTY")) {
              startMic();
              return;
            }
            showError("Голос", "Не удалось распознать речь.");
            return;
          }
          const data = (await res.json()) as { text?: string };
          const text = (data.text || "").trim();
          if (text && engaged && !processing && !speaking) {
            heard = true;
            void answer(text, true);
          } else if (engaged) {
            startMic();
          }
        } catch {
          showError("Голос", "Ошибка связи при распознавании.");
        }
      };
      recorder.start();
      // Auto-stop after silence window — continuous conversational turns.
      listenTimer = window.setTimeout(() => {
        if (recorder.state !== "inactive") recorder.stop();
      }, Math.max(2800, listenSilenceMs - 500));
    } catch {
      showError("Голос", "Нет доступа к микрофону.");
    }
  }

  function startMic() {
    if (!engaged || processing || speaking) return;
    const SpeechRecognition = getSpeechRecognition();
    if (!SpeechRecognition) {
      void startServerListen();
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
      if (engaged && !processing && !speaking && authToken) {
        void startServerListen();
      }
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
      void startServerListen();
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

  /** Push-to-talk: start listening while the user holds the mic. */
  function startHold() {
    if (engaged) return;
    engaged = true;
    if (audioRef.current) void unlockAudioElement(audioRef.current);
    startMic();
  }

  /**
   * Release hold — finalize any pending transcript as a task for Hermes.
   * Falls back to silence-stop if nothing was heard yet.
   */
  function endHold() {
    if (!engaged) return;
    // Force recognition end so onend flushes final transcript into answer()
    if (recognition) {
      try {
        recognition.stop();
      } catch {
        recognition.abort();
      }
    }
    // If nothing was heard, just stop the session
    window.setTimeout(() => {
      if (engaged && !processing && !speaking && !heard) stop();
    }, 120);
  }

  return { toggle, stop, startHold, endHold, isActive: () => engaged };
}
