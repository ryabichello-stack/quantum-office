---
name: design-system-architect
description: Define or extend design tokens, type scale, color roles, surfaces, radii, shadows, motion tokens, and component states. Use before adding new UI patterns across DELNO site, web app, or widget.
---

# Design System Architect

## Canonical doc

Maintain **`docs/design/design-system.md`** when tokens change.

## Deliverables

- Typography roles (display, title, body, caption, mono)
- Spacing scale (4px base or project convention)
- Color: background, surface, border, text primary/secondary, accent, danger, success
- Radius + shadow tiers (2–3 levels max)
- Motion: duration + easing tokens; `prefers-reduced-motion` policy

## Process

1. Inventory existing CSS variables in `DELNO-site-v23/app/v2/v2.css`, `delno-web/app/globals.css`, `components/widget/crystal-widget.css`
2. Propose minimal delta — REUSE existing names where possible
3. Map components → tokens (buttons, inputs, cards, nav)

## Do not

- Introduce Tailwind/shadcn for one page if stack is plain CSS unless user requests migration.
