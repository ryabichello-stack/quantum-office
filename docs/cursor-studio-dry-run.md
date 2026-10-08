# Cursor Studio — Dry Run (no code changes)

**Date:** 2026-10-08  
**Target:** https://dlno.ru/ (production marketing site)  
**Purpose:** Verify studio agents/skills can perform UX, creative, copy, CRO, and visual QA on a real render.

---

## Artifacts

| File | Description |
|------|-------------|
| `/opt/cursor/artifacts/delno-home-desktop-hero.png` | Desktop hero |
| `/opt/cursor/artifacts/delno-home-mobile-hero.png` | Mobile ~390px hero |
| `/opt/cursor/artifacts/delno-home-pricing.png` | Pricing section |

---

## Product UX Designer (summary)

- Hero value prop readable; product mock competes with primary CTA for attention.
- Pricing requires deep scroll — high friction for evaluation-stage visitors.
- Mobile header minimal — good focus, weaker wayfinding to `#prices`.

**Severity:** major (pricing discoverability), minor (nav)

---

## Creative Director (summary)

- Yellow/black identity is strong and on-brand for DELNO marketing CSS.
- Typography scale matches premium editorial direction in `v2.css`.
- Verify live loading indicators — may indicate slow demo assets (needs perf check, not layout).

**Verdict:** **Revise** — reduce hero visual competition; do not add decorative effects.

---

## Copy Chief (summary)

- Production hero copy differs from **repo canonical** (`docs/P1.1`: «Клиенты пишут и звонят»). Document which variant is intentional on prod.
- Price mention «от 5 990 ₽» in hero underplays **2 990 ₽** entry tier — align with KB.
- Multiple parallel CTAs blur primary action.

**Verdict:** **Revise** copy hierarchy; align with `.agents/product-marketing.md`.

---

## Conversion Strategist (summary)

- Too many equal-weight CTAs in hero (voice, phone, messengers, form).
- Trust/proof above fold: **UNKNOWN** logos — add verified proof or move demo social proof higher.
- Recommend: primary = voice demo; secondary = lead form; tertiary = channels in footer/sticky.

**Verdict:** **Needs work** on CTA focus and pricing anchor in nav.

---

## Visual QA (summary)

- Desktop and mobile captures obtained — **Pass** for process gate.
- Check widget vs sticky bar overlap on `/v2` when deployed (not tested on prod v2 in this run).
- Re-run after deploy when `/v2` convert variant is live.

---

## Accessibility (spot check — not full audit)

- Color contrast on yellow hero: verify WCAG for small text (accessibility-reviewer full pass recommended).
- Focus order for multiple hero links: test keyboard on next pass.

---

## Conclusion

**Studio configuration works:** subagent browser run produced screenshots and multi-lens review without editing production code.

**Next UI task:** use `premium-web-workflow` on a **repo-controlled** route (e.g. ship `/v2` convert) with before/after Visual QA.
