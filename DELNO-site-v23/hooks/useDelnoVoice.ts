"use client";

import { createVoiceController, type VoicePhase } from "@/lib/delnoVoice";
import { useCallback, useEffect, useRef, useState } from "react";

export function useDelnoVoice(options: {
  mountRef: React.RefObject<HTMLElement | null>;
  onTranscript: (text: string) => Promise<string>;
  onExchange?: (userText: string, assistantText: string) => void;
}) {
  const { mountRef, onTranscript, onExchange } = options;
  const [voicePhase, setVoicePhase] = useState<VoicePhase>("idle");
  const [voiceActive, setVoiceActive] = useState(false);
  const audioRef = useRef<HTMLAudioElement>(null);
  const controllerRef = useRef<ReturnType<typeof createVoiceController> | null>(null);
  const onTranscriptRef = useRef(onTranscript);
  const onExchangeRef = useRef(onExchange);

  useEffect(() => {
    onTranscriptRef.current = onTranscript;
  }, [onTranscript]);

  useEffect(() => {
    onExchangeRef.current = onExchange;
  }, [onExchange]);

  const setPhase = useCallback(
    (phase: VoicePhase) => {
      setVoicePhase(phase);
      const active = phase !== "idle";
      setVoiceActive(active);
      const root = mountRef.current;
      if (!root) return;
      if (active) root.setAttribute("data-voice-active", "true");
      else root.removeAttribute("data-voice-active");
      if (phase === "idle") root.removeAttribute("data-voice-phase");
      else root.setAttribute("data-voice-phase", phase);
    },
    [mountRef],
  );

  useEffect(() => {
    controllerRef.current = createVoiceController({
      onTranscript: (text) => onTranscriptRef.current(text),
      onExchange: (user, assistant) => onExchangeRef.current?.(user, assistant),
      setPhase,
      audioRef,
    });
    return () => controllerRef.current?.stop();
  }, [setPhase]);

  const toggleVoice = useCallback(() => {
    controllerRef.current?.toggle();
  }, []);

  const stopVoice = useCallback(() => {
    controllerRef.current?.stop();
  }, []);

  const askText = useCallback(async (text: string) => {
    await controllerRef.current?.askText(text);
  }, []);

  return { voicePhase, voiceActive, toggleVoice, stopVoice, askText, audioRef };
}

export type { VoicePhase };
