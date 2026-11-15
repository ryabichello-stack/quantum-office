"use client";

import { useEffect, useId, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import type { ThinkingStep } from "@/lib/hermesThinking";
import { thinkingView } from "@/lib/hermesUiStates";
import { cn } from "@/lib/utils";

/**
 * While Hermes is working, only the current step is shown large.
 * Earlier steps sit behind «Ход мыслей · N …».
 * When the answer arrives the whole trace collapses; the reply stays outside.
 */
export function HermesThinkingTrace({
  steps,
  live = false,
  liveIndex,
}: {
  steps: ThinkingStep[];
  /** Request still in flight — current step stays open. */
  live?: boolean;
  /** How many steps of the plan are active so far (1-based). */
  liveIndex?: number;
  /** Kept so existing callers can pass the measured duration. */
  durationMs?: number;
}) {
  const view = thinkingView(steps, { live, liveIndex });
  const [open, setOpen] = useState(false);
  const listId = useId();

  useEffect(() => {
    if (!live) setOpen(false);
  }, [live]);

  if (!steps.length || (!view.showSummary && !view.current)) return null;

  const expanded = view.showSummary && open;
  const currentKey = view.current ? `${liveIndex ?? 0}:${view.current.label}` : "";

  return (
    <div
      className={cn("hx-think", live && "is-live")}
      data-state={live ? "live" : "done"}
      data-open={expanded ? "true" : "false"}
    >
      {view.showSummary ? (
        <button
          type="button"
          className="hx-think-toggle"
          aria-expanded={open}
          aria-controls={expanded ? listId : undefined}
          onClick={() => setOpen((v) => !v)}
        >
          {open ? <ChevronDown size={14} strokeWidth={2} /> : <ChevronRight size={14} strokeWidth={2} />}
          <span>{view.summaryLabel}</span>
        </button>
      ) : null}
      {expanded ? (
        <ol id={listId} className="hx-think-list">
          {view.summarySteps.map((step, i) => (
            <li key={`${i}-${step.label}`}>
              <span>{step.label}</span>
              {step.detail ? <small>{step.detail}</small> : null}
            </li>
          ))}
        </ol>
      ) : null}
      {view.current ? (
        <p className="hx-think-current" key={currentKey} aria-live="polite">
          <span className="hx-think-label">{view.current.label}</span>
          {view.current.detail ? <small>{view.current.detail}</small> : null}
        </p>
      ) : null}
    </div>
  );
}
