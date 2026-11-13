"use client";

import { useEffect, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import type { ThinkingStep } from "@/lib/hermesThinking";
import { thinkingNarrative } from "@/lib/hermesThinking";
import { cn } from "@/lib/utils";

/**
 * Claude/ChatGPT-style thinking: muted italic stream above the reply.
 * While live — open, shows the current thought. After — collapsed by default.
 */
export function HermesThinkingTrace({
  steps,
  live = false,
  liveIndex,
  durationMs,
}: {
  steps: ThinkingStep[];
  /** Request still in flight — thinking shown before the answer. */
  live?: boolean;
  /** How many steps of the plan are “active” so far (1-based). */
  liveIndex?: number;
  /** Wall time for the finished thought (ms). */
  durationMs?: number;
}) {
  const [open, setOpen] = useState(live);
  useEffect(() => {
    if (live) setOpen(true);
    else setOpen(false);
  }, [live]);

  if (!steps.length) return null;
  const visible = live && liveIndex ? steps.slice(0, Math.max(1, liveIndex)) : steps;
  const body = thinkingNarrative(visible);
  const current = visible[visible.length - 1];
  const secs =
    typeof durationMs === "number" && durationMs > 0
      ? Math.max(1, Math.round(durationMs / 1000))
      : null;

  return (
    <div className={cn("hx-cot", live && "is-live")}>
      <button
        type="button"
        className="hx-cot-toggle"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        {open ? <ChevronDown size={13} strokeWidth={2} /> : <ChevronRight size={13} strokeWidth={2} />}
        <span className="hx-cot-label">
          {live ? (
            <>
              Думаю
              <span className="hx-cot-pulse" aria-hidden>
                …
              </span>
            </>
          ) : secs ? (
            <>Думал {secs} с</>
          ) : (
            <>Размышления</>
          )}
        </span>
      </button>
      {open ? (
        <div className="hx-cot-body">
          <pre className="hx-cot-text">{body}</pre>
          {live && current ? (
            <p className="hx-cot-now">
              Сейчас: <em>{current.label}</em>
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
