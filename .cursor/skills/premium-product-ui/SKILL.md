---
name: premium-product-ui
description: Combine product UX, high-end UI, information density, clarity, interaction quality, and design-system consistency for DELNO and Quantum office products. Use for dashboards, marketing pages, and widget UI that must feel premium without decorative noise.
---

# Premium Product UI

## When to use

Landing pages, `delno-web` dashboard, embed widget chrome, onboarding — any surface where users decide trust in seconds.

## Load first

1. `.agents/product-marketing.md`
2. `docs/design/design-system.md`
3. Relevant upstream skills (pick 1–3): `product-design-and-ux`, `frontend-design`, `apple-design`, `emil-design-eng`

## Principles

- Hierarchy before decoration; one primary action per viewport.
- Density: show real product structure (inbox, channels, limits) — no fake metrics.
- States: loading, empty, error, disabled, success — designed, not afterthoughts.
- Match existing stack (Next.js, CSS modules / global CSS in repo); no framework rewrites for visuals alone.

## Output

- Token-aligned spacing/type/color choices
- Component-level notes (not page-specific magic numbers)
- Explicit mobile behavior

## Handoff

Implementation → **design-engineer** subagent. Review → **visual-qa** + **accessibility-reviewer**.
