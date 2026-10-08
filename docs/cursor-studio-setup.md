# Cursor Product / Design Studio — Setup

**Last updated:** 2026-10-08

This repo includes a **project-scoped** design and marketing studio for DELNO and office UIs.

---

## Layout

| Path | Purpose |
|------|---------|
| `.agents/skills/` | Upstream skills installed by `npx skills add` (lock: `skills-lock.json`) |
| `.cursor/skills/` | **Custom** project skills (orchestration + DELNO-specific) |
| `.cursor/agents/` | Subagent definitions (Creative Director, Visual QA, …) |
| `.cursor/rules/` | Persistent constraints (not full procedures) |
| `.agents/product-marketing.md` | Canonical marketing context for copy/CRO skills |
| `docs/design/design-system.md` | Tokens and patterns for site/app/widget |

**Note:** Cursor CLI installs third-party skills to `.agents/skills/` by default. Custom skills live under `.cursor/skills/` to avoid overwrite on `skills update`.

---

## Installed upstream skills (40)

| Skill | Source |
|-------|--------|
| apple-design, emil-design-eng, prototype, break-ui, animate, find-animation-opportunities, improve-animations, review-animations, mobile-native | [emilkowalski/skills](https://github.com/emilkowalski/skills) |
| design-first-ui-prompting, build-awwwards-quality-sites, animation-systems, gsap, optimize-web-animations, threejs | [MengTo/Skills](https://github.com/MengTo/Skills) |
| frontend-design | [anthropics/skills](https://github.com/anthropics/skills) |
| product-design-and-ux | [magnus919/agent-skills](https://github.com/magnus919/agent-skills) |
| accessibility | [addyosmani/web-quality-skills](https://github.com/addyosmani/web-quality-skills) |
| product-marketing, customer-research, competitor-profiling, marketing-psychology, offers, copywriting, copy-editing, cro, pricing, content-strategy, seo-audit, ai-seo, signup, onboarding, ab-testing, analytics, social, emails, ads | [coreyhaines31/marketingskills](https://github.com/coreyhaines31/marketingskills) |

**Scope:** project (`npx skills list -p`). For user-global copies:

```bash
npx skills add https://github.com/emilkowalski/skills --skill apple-design --agent cursor -g -y
```

---

## Custom project skills

| Skill | Role |
|-------|------|
| `premium-web-workflow` | **Start here** for meaningful UI work |
| `premium-product-ui` | UX + high-end UI combined |
| `apple-premium-web` | Restraint / hierarchy principles |
| `design-system-architect` | Tokens and component states |
| `graphics-pipeline` | When to use SVG vs generated art vs 3D |
| `visual-qa` | Browser screenshot QA checklist |
| `conversion-copy-system` | Copy + CRO with product context |

---

## Subagents (`.cursor/agents/`)

Invoke via Cursor **Task** with the agent name or by referencing the file in instructions.

| Agent | Use |
|-------|-----|
| `creative-director` | Taste, hierarchy, anti–AI-slop |
| `product-ux-designer` | Flows, states, mobile |
| `conversion-strategist` | Funnel, proof, pricing presentation |
| `copy-chief` | Russian marketing copy |
| `design-engineer` | Implementation |
| `visual-qa` | Independent screenshot QA |
| `accessibility-reviewer` | WCAG baseline |

---

## Rules

| Rule | alwaysApply |
|------|-------------|
| `00-product-quality.mdc` | yes |
| `10-design-quality.mdc` | glob: site/app/widget |
| `20-ux-quality.mdc` | glob |
| `30-copy-quality.mdc` | on demand |
| `40-conversion.mdc` | glob: marketing |
| `50-visual-verification.mdc` | glob: UI paths |

---

## Capabilities

| Capability | Status |
|------------|--------|
| Cursor Browser | ✅ computerUse / manual browser |
| Image generation | ✅ `GenerateImage` when explicitly needed |
| Figma MCP | ⚠️ installed plugin, **needsAuth** |
| MCP cursor-cloud | ✅ diagnostics |
| Playwright skill | ❌ not installed; use custom `visual-qa` |

---

## Recommended workflow

1. Read `.agents/product-marketing.md`
2. Run skill **`premium-web-workflow`**
3. Select 1–3 upstream skills (do not invoke all marketing skills)
4. Implement with **design-engineer** patterns
5. **Browser** render + **visual-qa** subagent
6. Premium pages: **creative-director** sign-off

---

## Maintenance

```bash
cd /path/to/quantum-office
npx skills update -p -y          # refresh upstream skills
npx skills list -p               # verify discovery
```

After updates, skim `skills-lock.json` diff in PR.

---

## Related docs

- Audit: `docs/cursor-design-system-audit.md`
- Dry run: `docs/cursor-studio-dry-run.md`
- Design tokens: `docs/design/design-system.md`
- Landing policy: `docs/P1.1_SITE_LANDING.md`
