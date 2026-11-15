"use client";

import { useEffect, useId, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import type { ThinkingStep } from "@/lib/hermesThinking";
import { thinkingView } from "@/lib/hermesUiStates";
import { cn } from "@/lib/utils";

/**
 * One line while Hermes works: the current action, in plain present tense.
 * The owner can open the full list in the same words.
 * When the reply is ready the line becomes «Сделал N действий».
 */
export function HermesThinkingTrace({
  steps,
  live = false,
  liveIndex,
  awaiting = false,
}: {
  steps: ThinkingStep[];
  /** Request still in flight — the line is the current action. */
  live?: boolean;
  /** How many steps of the plan are active so far (1-based). */
  liveIndex?: number;
  /** Between tools, or before the first one: «Думаю над ответом…». */
  awaiting?: boolean;
  /** Kept so existing callers can pass the measured duration. */
  durationMs?: number;
}) {
  const view = thinkingView(steps, { live, liveIndex, awaiting });
  const [open, setOpen] = useState(false);
  const listId = useId();

  useEffect(() => {
    if (!live) setOpen(false);
  }, [live]);

  if (!view.line) return null;

  return (
    <div
      className={cn("hx-think", live && "is-live")}
      data-state={live ? "live" : "done"}
      data-open={open ? "true" : "false"}
    >
      <button
        type="button"
        className="hx-think-toggle"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        onClick={() => setOpen((v) => !v)}
      >
        {open ? <ChevronDown size={14} strokeWidth={2} /> : <ChevronRight size={14} strokeWidth={2} />}
        <span className="hx-think-line" key={view.line}>
          {view.line}
        </span>
      </button>
      {open ? (
        <ol id={listId} className="hx-think-list">
          {view.steps.map((step, i) => (
            <li key={`${i}-${step.label}`}>
              <span>{step.label}</span>
              {step.detail ? <small>{step.detail}</small> : null}
            </li>
          ))}
        </ol>
      ) : null}
      {live ? (
        <span className="sr-only" aria-live="polite">
          {view.line}
        </span>
      ) : null}
    </div>
  );
}
