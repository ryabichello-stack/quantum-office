---
name: premium-web-workflow
description: Orchestrate premium UI work from understanding through diverge, critique, implement, browser render, visual QA, adversarial QA, motion and CRO review. Main workflow for meaningful UI tasks in this repo.
---

# Premium Web Workflow

## Phase 1 — Understand

Read `.agents/product-marketing.md`, current page code, `docs/design/design-system.md`, user task.

## Phase 2 — Define

User goal, business goal, primary conversion, audience, objections, visual direction (1 paragraph).

## Phase 3 — Diverge (major changes only)

2–3 **meaningfully different** directions; use `prototype` skill.

## Phase 4 — Critique

Spawn or emulate: **creative-director**, **product-ux-designer**, **conversion-strategist** (`.cursor/agents/`). Pick or merge winner.

## Phase 5 — Implement

**design-engineer** — minimal diff, existing patterns.

## Phase 6 — Render

Start dev server or use production URL; **Cursor Browser** — never sign off on code-only review.

## Phase 7 — Visual QA

Custom `visual-qa` skill + screenshots.

## Phase 8 — Adversarial QA

`break-ui` — long text, empty states, errors.

## Phase 9 — Motion

If motion exists: `review-animations`; delete purposeless animation.

## Phase 10 — CRO

`cro` / `conversion-strategist` — value prop, proof, friction, pricing clarity.

## Phase 11 — Polish

Fix findings → re-render → re-QA until quality gates pass.

## Quality gates (summary)

Build passes **and** browser inspected **and** mobile **and** copy **and** conversion logic **and** Creative Director + Visual QA sign-off for premium work.
