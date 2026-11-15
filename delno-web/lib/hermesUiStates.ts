/**
 * Pure UI state for the Hermes mic and the thinking trace.
 * The cabinet binds to these shapes; tests lock the transitions.
 */

export type DictatePhase = "idle" | "recording" | "transcribing";

export type DictateSnapshot = {
  phase: DictatePhase;
  error: string;
  elapsedMs: number;
  /** 0..1 microphone energy from AnalyserNode. */
  level: number;
  /** Text already placed in the composer. Not sent automatically. */
  draft: string;
  /** True only after a real streaming engine emitted a partial. */
  streaming: boolean;
};

export type DictateEvent =
  | { type: "start" }
  | { type: "tick"; elapsedMs: number }
  | { type: "level"; level: number }
  | { type: "partial"; text: string }
  | { type: "stop" }
  | { type: "recognized"; text: string }
  | { type: "fail"; message: string }
  | { type: "cancel" }
  | { type: "dismiss-error" };

export function initialDictate(): DictateSnapshot {
  return {
    phase: "idle",
    error: "",
    elapsedMs: 0,
    level: 0,
    draft: "",
    streaming: false,
  };
}

export function reduceDictate(state: DictateSnapshot, event: DictateEvent): DictateSnapshot {
  switch (event.type) {
    case "start":
      if (state.phase !== "idle") return state;
      return {
        ...state,
        phase: "recording",
        error: "",
        elapsedMs: 0,
        level: 0,
        streaming: false,
      };
    case "tick":
      if (state.phase !== "recording") return state;
      return { ...state, elapsedMs: Math.max(0, event.elapsedMs) };
    case "level":
      if (state.phase !== "recording") return state;
      return { ...state, level: Math.min(1, Math.max(0, event.level)) };
    case "partial":
      if (state.phase !== "recording") return state;
      return { ...state, draft: event.text, streaming: true };
    case "stop":
      if (state.phase !== "recording") return state;
      return { ...state, phase: "transcribing", level: 0 };
    case "recognized":
      if (state.phase !== "transcribing") return state;
      return {
        ...state,
        phase: "idle",
        draft: event.text,
        level: 0,
        elapsedMs: 0,
        streaming: false,
        error: "",
      };
    case "fail":
      return {
        ...state,
        phase: "idle",
        error: event.message,
        level: 0,
        elapsedMs: 0,
        streaming: false,
      };
    case "cancel":
      return { ...initialDictate(), draft: state.draft };
    case "dismiss-error":
      return { ...state, error: "" };
    default:
      return state;
  }
}

export function formatRecordTime(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function micButtonLabel(phase: DictatePhase): string {
  if (phase === "recording") return "Остановить запись";
  if (phase === "transcribing") return "Распознаю речь";
  return "Голосовой ввод";
}

const WAVE_SHAPE = [0.45, 0.72, 1, 0.78, 0.5];

/** Bar heights in px. Silence stays short; speech lifts the bars. */
export function waveHeights(level: number, elapsedMs: number): number[] {
  const energy = Math.min(1, Math.max(0, level));
  return WAVE_SHAPE.map((shape, i) => {
    const wobble = 0.72 + 0.28 * Math.sin(elapsedMs / 160 + i * 0.9);
    return Math.round(4 + energy * 18 * shape * wobble);
  });
}

export type ThoughtStep = { label: string; detail?: string };

export type ThinkingView = {
  live: boolean;
  /** Large animated step. Null once the answer is ready. */
  current: ThoughtStep | null;
  /** Steps hidden behind «Ход мыслей · N …» until the owner opens them. */
  summarySteps: ThoughtStep[];
  summaryLabel: string;
  showSummary: boolean;
};

export function ruSteps(count: number): string {
  const n = Math.abs(Math.trunc(count));
  const n10 = n % 10;
  const n100 = n % 100;
  let word = "шагов";
  if (n10 === 1 && n100 !== 11) word = "шаг";
  else if (n10 >= 2 && n10 <= 4 && (n100 < 12 || n100 > 14)) word = "шага";
  return `${n} ${word}`;
}

export function thoughtsLabel(count: number): string {
  return `Ход мыслей · ${ruSteps(count)}`;
}

export function thinkingView(
  steps: ThoughtStep[],
  opts: { live?: boolean; liveIndex?: number },
): ThinkingView {
  const live = Boolean(opts.live);
  if (!steps.length) {
    return {
      live,
      current: null,
      summarySteps: [],
      summaryLabel: thoughtsLabel(0),
      showSummary: false,
    };
  }
  if (!live) {
    return {
      live: false,
      current: null,
      summarySteps: steps,
      summaryLabel: thoughtsLabel(steps.length),
      showSummary: true,
    };
  }
  const visible = steps.slice(0, Math.max(1, opts.liveIndex || 1));
  const current = visible[visible.length - 1] ?? null;
  const summarySteps = visible.slice(0, -1);
  return {
    live: true,
    current,
    summarySteps,
    summaryLabel: thoughtsLabel(summarySteps.length),
    showSummary: summarySteps.length > 0,
  };
}
