---
name: visual-qa
description: Independent visual QA via browser screenshots — desktop and mobile layout, typography, spacing, overflow, states, motion, console errors, baseline a11y. Use after UI changes before marking work done.
---

# Visual QA

## Required checks

1. **Desktop** screenshot (≥1280px) — full page or critical sections
2. **Mobile** screenshot (390×844 or device) — hero, nav, CTA, forms
3. **Typography** — hierarchy readable; no orphan headings
4. **Spacing** — consistent section padding; no accidental collisions
5. **Overflow** — long Russian strings, large prices, narrow viewports
6. **States** — hover/focus where applicable; modal open; error path if touched
7. **Console** — no relevant errors during load and primary interaction
8. **Motion** — if animated, run `review-animations`; respect reduced motion

## Tools

- Cursor Browser / computerUse subagent
- `break-ui` skill for adversarial content
- `mobile-native` for touch targets and sticky bars

## Output format

```markdown
## Visual QA — [page]
- Pass / Fail
- Findings (severity: blocker / major / minor)
- Screenshots: [paths or artifact refs]
```

Adversarial mindset: find problems; do not defend implementation.
