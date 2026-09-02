"use client";

import { askDelnoWidget, widgetTtsPath } from "@/lib/widgetApi";
import { Mic, Phone, Sparkles, Square, Volume2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";

type DemoState = "idle" | "listening" | "thinking" | "speaking" | "error";

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

const prompts = ["Сколько стоит?", "Как подключить номер?", "Что умеет DELNO?"];

export default function VoiceDemo() {
  const [state, setState] = useState<DemoState>("idle");
  const [question, setQuestion] = useState("Нажмите на круг и задайте вопрос");
  const [answer, setAnswer] = useState("Я отвечу по базе знаний DELNO — о тарифах, подключении и возможностях.");
  const heardRef = useRef(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioUnlockedRef = useRef(false);
  const unlockUrlRef = useRef<string | null>(null);
  const audioUrlRef = useRef<string | null>(null);
  const recognitionRef = useRef<SpeechRecognitionInstance | null>(null);
  const requestRef = useRef<AbortController | null>(null);

  const stopAudio = () => {
    requestRef.current?.abort();
    requestRef.current = null;
    audioRef.current?.pause();
    window.speechSynthesis?.cancel();
    if (audioUrlRef.current) URL.revokeObjectURL(audioUrlRef.current);
    audioUrlRef.current = null;
  };

  const unlockAudio = () => {
    const audio = audioRef.current;
    if (!audio || audioUnlockedRef.current) return;
    const sampleRate = 8000;
    const samples = 800;
    const buffer = new ArrayBuffer(44 + samples * 2);
    const view = new DataView(buffer);
    const write = (offset: number, value: string) =>
      [...value].forEach((char, index) => view.setUint8(offset + index, char.charCodeAt(0)));
    write(0, "RIFF");
    view.setUint32(4, 36 + samples * 2, true);
    write(8, "WAVE");
    write(12, "fmt ");
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 1, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    write(36, "data");
    view.setUint32(40, samples * 2, true);
    const silentUrl = URL.createObjectURL(new Blob([buffer], { type: "audio/wav" }));
    unlockUrlRef.current = silentUrl;
    audio.muted = true;
    audio.src = silentUrl;
    const attempt = audio.play();
    if (attempt)
      void attempt
        .then(() => {
          audio.muted = false;
          audioUnlockedRef.current = true;
          window.setTimeout(() => {
            audio.pause();
            audio.currentTime = 0;
            if (unlockUrlRef.current) URL.revokeObjectURL(unlockUrlRef.current);
            unlockUrlRef.current = null;
          }, 120);
        })
        .catch(() => {
          audio.muted = false;
        });
  };

  const playWithDeviceVoice = (text: string) => {
    if (!("speechSynthesis" in window)) return false;
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "ru-RU";
    utterance.rate = 0.93;
    utterance.pitch = 1;
    const voices = window.speechSynthesis.getVoices();
    utterance.voice =
      voices.find(
        (voice) =>
          /ru-RU/i.test(voice.lang) &&
          /natural|enhanced|milena|alena|svetlana|irina/i.test(voice.name),
      ) ||
      voices.find((voice) => /ru/i.test(voice.lang)) ||
      null;
    utterance.onstart = () => setState("speaking");
    utterance.onend = () => setState("idle");
    utterance.onerror = () => setState("error");
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(utterance);
    return true;
  };

  const stopCurrent = () => {
    recognitionRef.current?.stop();
    recognitionRef.current = null;
    stopAudio();
    setState("idle");
  };

  useEffect(
    () => () => {
      recognitionRef.current?.stop();
      stopAudio();
    },
    [],
  );

  const speak = async (text: string) => {
    stopAudio();
    try {
      const controller = new AbortController();
      requestRef.current = controller;
      const response = await fetch(widgetTtsPath(text), { signal: controller.signal });
      if (!response.ok) throw new Error("voice unavailable");

      const audioBlob = await response.blob();
      if (controller.signal.aborted) return;
      requestRef.current = null;
      const url = URL.createObjectURL(audioBlob);
      const audio = audioRef.current;
      if (!audio) throw new Error("audio element unavailable");
      audioUrlRef.current = url;
      audio.muted = false;
      audio.src = url;
      audio.onplaying = () => setState("speaking");
      audio.onended = () => {
        stopAudio();
        setState("idle");
      };
      audio.onerror = () => {
        stopAudio();
        setState("error");
      };
      await audio.play();
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      stopAudio();
      if (!playWithDeviceVoice(text)) {
        setState("error");
        setQuestion("Ответ готов — нажмите ещё раз, чтобы прослушать");
      }
    }
  };

  const answerQuestion = async (text: string) => {
    stopCurrent();
    unlockAudio();
    setQuestion(text);
    setState("thinking");

    const { answer: reply, error } = await askDelnoWidget(text);
    if (error || !reply) {
      setAnswer("Сейчас не удалось получить ответ. Попробуйте ещё раз или задайте вопрос текстом в чате внизу страницы.");
      setState("error");
      return;
    }

    setAnswer(reply);
    void speak(reply);
  };

  const startListening = () => {
    if (state !== "idle" && state !== "error") {
      stopCurrent();
      return;
    }
    stopCurrent();
    unlockAudio();
    const speechWindow = window as SpeechWindow;
    const SpeechRecognition = speechWindow.SpeechRecognition || speechWindow.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setState("error");
      setQuestion("Браузер не поддерживает распознавание речи");
      setAnswer("Используйте Chrome, Edge или Safari — или задайте вопрос кнопками ниже.");
      return;
    }

    heardRef.current = false;
    const recognition = new SpeechRecognition();
    recognitionRef.current = recognition;
    recognition.lang = "ru-RU";
    recognition.interimResults = false;
    recognition.continuous = false;
    recognition.onstart = () => {
      setState("listening");
      setQuestion("Слушаю вас…");
    };
    recognition.onresult = (event: SpeechRecognitionResultEvent) => {
      heardRef.current = true;
      void answerQuestion(event.results[0][0].transcript);
    };
    recognition.onerror = () => {
      heardRef.current = true;
      recognitionRef.current = null;
      setState("error");
      setQuestion("Не удалось услышать вопрос");
      setAnswer("Разрешите доступ к микрофону и нажмите ещё раз. Или выберите готовый вопрос ниже.");
    };
    recognition.onend = () => {
      recognitionRef.current = null;
      if (!heardRef.current) setState("idle");
    };
    recognition.start();
  };

  const active = state === "listening" || state === "thinking" || state === "speaking";
  const label =
    state === "listening"
      ? "Слушаю… Нажмите, чтобы остановить"
      : state === "thinking"
        ? "Готовлю ответ…"
        : state === "speaking"
          ? "Отвечаю… Нажмите, чтобы остановить"
          : "Спросить вслух";

  return (
    <section className="voice-demo-section" id="demo">
      <div className="voice-demo-copy">
        <div className="v2-kicker pale">Попробуйте сейчас</div>
        <h2>
          Спросите
          <br />
          DELNO вслух.
        </h2>
        <p>
          Такого голосового помощника можно разместить на вашем сайте. Клиент нажимает, задаёт вопрос и сразу
          получает ответ по вашей базе знаний.
        </p>
        <div className="demo-badges">
          <span>
            <Mic /> Голос
          </span>
          <span>
            <Sparkles /> ИИ-ответ
          </span>
          <span>
            <Phone /> Без звонка
          </span>
        </div>
      </div>

      <div className={`voice-orb-stage ${state}`}>
        <div className="voice-orb-visual">
          <div className="voice-orb-halo" />
          <button
            className="voice-orb"
            onClick={startListening}
            aria-label={active ? "Остановить голосового помощника" : "Задать вопрос DELNO голосом"}
            aria-pressed={active}
          >
            <span className="voice-orb-core">{active ? <Square /> : <Mic />}</span>
          </button>
        </div>
        <b>{label}</b>
        <small>Нажмите один раз, чтобы начать. Ещё раз — чтобы остановить.</small>
      </div>

      <div className="voice-demo-dialog">
        <div className="demo-dialog-head">
          <span>
            <i /> DELNO
          </span>
          <Volume2 />
        </div>
        <div className="demo-message user">
          <small>Вы</small>
          <p>{question}</p>
        </div>
        <div className="demo-message delno">
          <small>DELNO</small>
          <p>{answer}</p>
        </div>
        <div className="demo-prompts">
          {prompts.map((prompt) => (
            <button key={prompt} onClick={() => void answerQuestion(prompt)}>
              {prompt}
            </button>
          ))}
        </div>
        <p className="demo-disclaimer">Ответы из базы знаний DELNO. Голос синтезирован ИИ.</p>
      </div>
      <audio ref={audioRef} className="voice-audio" preload="none" playsInline />
    </section>
  );
}
