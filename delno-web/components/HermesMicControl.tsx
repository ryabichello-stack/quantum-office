"use client";

import type { ComponentProps, CSSProperties } from "react";
import { Loader2, Mic } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  formatRecordTime,
  micButtonLabel,
  waveHeights,
  type DictatePhase,
} from "@/lib/hermesUiStates";
import { cn } from "@/lib/utils";

export function HermesMicButton({
  phase,
  level,
  elapsedMs = 0,
  compact,
  className,
  variant = "ghost",
  disabled,
  style,
  onContextMenu,
  ...rest
}: {
  phase: DictatePhase;
  level: number;
  elapsedMs?: number;
  compact?: boolean;
} & ComponentProps<typeof Button>) {
  const recording = phase === "recording";
  const busy = phase === "transcribing";
  const flatStyle: CSSProperties | undefined = typeof style === "function" ? undefined : style;
  const levelStyle: CSSProperties | undefined = recording
    ? ({ ...flatStyle, "--mic-level": String(Math.min(1, Math.max(0, level))) } as CSSProperties)
    : flatStyle;
  return (
    <Button
      {...rest}
      type="button"
      variant={recording ? "ghost" : variant}
      size="icon"
      disabled={disabled || busy}
      aria-label={micButtonLabel(phase)}
      aria-pressed={recording}
      aria-busy={busy}
      data-phase={phase}
      data-elapsed={elapsedMs}
      onContextMenu={(event) => {
        event.preventDefault();
        onContextMenu?.(event);
      }}
      className={cn(
        "hx-tool-btn hx-mic-btn touch-none",
        recording && "is-recording",
        busy && "is-transcribing",
        className,
      )}
      style={levelStyle}
    >
      {busy ? (
        <Loader2 className="hx-spin" size={compact ? 16 : 18} aria-hidden />
      ) : (
        <Mic size={compact ? 16 : 18} aria-hidden />
      )}
    </Button>
  );
}

export function HermesDictateStatus({
  phase,
  level,
  elapsedMs,
  onStop,
}: {
  phase: DictatePhase;
  level: number;
  elapsedMs: number;
  onStop: () => void;
}) {
  if (phase === "idle") return null;
  if (phase === "transcribing") {
    return (
      <div className="hx-dictate is-transcribing" role="status" data-phase="transcribing">
        <Loader2 className="hx-spin" size={16} aria-hidden />
        <span>Распознаю…</span>
      </div>
    );
  }
  const bars = waveHeights(level, elapsedMs);
  return (
    <div className="hx-dictate is-recording" data-phase="recording">
      <span className="sr-only">Идёт запись. Нажмите «Стоп», чтобы распознать речь.</span>
      <span className="hx-dictate-dot" aria-hidden />
      <span className="hx-dictate-label">Запись</span>
      <time className="hx-dictate-time" dateTime={`PT${Math.floor(elapsedMs / 1000)}S`} aria-hidden>
        {formatRecordTime(elapsedMs)}
      </time>
      <span className="hx-mic-waves" aria-hidden>
        {bars.map((height, i) => (
          <i key={i} style={{ height: `${height}px` }} />
        ))}
      </span>
      <button type="button" className="hx-dictate-stop" onClick={onStop} aria-label="Остановить запись">
        Стоп
      </button>
    </div>
  );
}
