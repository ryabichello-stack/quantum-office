# DELNO / Office — Design System (baseline)

**Status:** Baseline extracted from existing CSS · extend via `design-system-architect` skill  
**Stacks:** `DELNO-site-v23` (marketing CSS), `delno-web` (app), `delno-widget` / `crystal-widget.css`

---

## Typography

| Role | Marketing (`v2.css`) | Notes |
|------|----------------------|--------|
| Display / H1 | clamp(58px, 6.5vw, 103px), weight 900, tight tracking | Hero only |
| Section H2 | clamp(48px, 6vw, 82px) | Promise, features, pricing |
| Body | 16–18px, line-height ~1.6 | `--gray` / `#555651` secondary |
| UI small | 10–13px | Kicker, labels |

**Font family:** Arial, Helvetica, sans-serif (marketing). App: see `delno-web/app/globals.css`.

---

## Color (marketing v2)

| Token | Value | Role |
|-------|-------|------|
| `--y` | `#ffd233` | Brand accent, highlights |
| `--black` | `#111` | Text, primary buttons |
| `--bg` | `#f6f6f3` | Page background |
| `--line` | `#dfdfda` | Borders |
| `--gray` | `#686964` | Secondary text |

**v4 convert palette** (`.v4-refined` in `app/v4/v4.css`): `--v4-ink`, `--v4-paper`, `--v4-accent` (#74e4c3) — use only on `/v4` and `/v2` convert layouts.

---

## Spacing

- Section padding: `120px clamp(24px, 6vw, 96px)` (desktop); `82px 20px` (mobile ≤740px)
- Header height: 72px (sticky)
- Grid gaps: 8–14px (components), 6vw (hero columns)

---

## Layout

- Max content width: implicit via clamp padding; price grid max ~1180px
- Hero: two-column grid `.76fr / 1.24fr` (collapses ≤1100px)

---

## Radius & shadow

- Buttons/cards: 12–16px radius
- Console drop-shadow: heavy product mock — use sparingly outside hero

---

## Motion

- Hover lifts: `translateY(-2px)` on buttons/cards
- v4: spring-like CSS keyframes — always provide `prefers-reduced-motion: reduce` overrides (see `v4.css`)
- Widget orb: phase-driven CSS in `crystal-widget.css`

---

## Components (marketing)

- `.v2-btn` primary / secondary / compact
- `.v2-header` + `ActiveNav` pill
- `.voice-cta` / voice demo section
- Lead modal: `.lead-dialog` (v4.css)

---

## Responsive

- Breakpoints: 1100px, 740px (primary in `v2.css` / `mobile.css`)
- Mobile: hide desktop nav; stack CTAs; sticky header

---

## Widget

- Crystal orb + chat panel — dark/light variants in `delno-widget/` and `components/widget/`
- Do not break embed contract documented in `delno-widget/INTEGRATION.md`

---

## Governance

- Token changes: update this doc in the same PR
- New pages: pick **one** accent system (canonical yellow v2 vs v4 mint) per route
