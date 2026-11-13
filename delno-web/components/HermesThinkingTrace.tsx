"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight, Sparkles } from "lucide-react";
import type { ThinkingStep } from "@/lib/hermesThinking";
import { cn } from "@/lib/utils";

/** Collapsible chain-of-thought / tool trail above the assistant reply. */
export function HermesThinkingTrace({
  steps,
  defaultOpen = true,
}: {
  steps: ThinkingStep[];
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  if (!steps.length) return null;
  return (
    <div className="hx-think">
      <button
        type="button"
        className="hx-think-toggle"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <Sparkles size={14} />
        <span>Размышления</span>
        <em>{steps.length}</em>
      </button>
      {open ? (
        <ol className="hx-think-list">
          {steps.map((step, i) => (
            <li
              key={`${step.label}-${i}`}
              className={cn(
                "hx-think-step",
                step.ok === true && "is-ok",
                step.ok === false && "is-bad",
              )}
            >
              <span className="hx-think-dot" aria-hidden />
              <div>
                <strong>{step.label}</strong>
                {step.detail ? <p>{step.detail}</p> : null}
              </div>
            </li>
          ))}
        </ol>
      ) : null}
    </div>
  );
}
