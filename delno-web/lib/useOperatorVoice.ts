"use client";

import { useEffect, useRef, useState } from "react";
import { createVoiceController, type VoicePhase } from "@/lib/delnoVoice";

export function useOperatorVoice(onTranscript: (text: string) => Promise<string>) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const controllerRef = useRef<ReturnType<typeof createVoiceController> | null>(null);
  const [voicePhase, setVoicePhase] = useState<VoicePhase>("idle");
  const [voiceActive, setVoiceActive] = useState(false);

  useEffect(() => {
    controllerRef.current = createVoiceController({
      onTranscript,
      setPhase: (phase) => {
        setVoicePhase(phase);
        setVoiceActive(phase !== "idle" && phase !== "error");
      },
      audioRef,
    });
    return () => controllerRef.current?.stop();
  }, [onTranscript]);

  function toggleVoice() {
    controllerRef.current?.toggle();
    window.setTimeout(() => {
      setVoiceActive(controllerRef.current?.isActive() ?? false);
      if (!controllerRef.current?.isActive()) setVoicePhase("idle");
    }, 60);
  }

  return { voiceActive, voicePhase, toggleVoice, audioRef };
}
