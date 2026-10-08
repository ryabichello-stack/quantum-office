# Cursor Design System — Audit

**Date:** 2026-10-08  
**Repo:** quantum-office  
**Principle applied:** REUSE → IMPROVE → ADD → REPLACE

---

## Paths inspected

| Location | Result |
|----------|--------|
| `~/.cursor/skills/` | **Missing** (empty / not used) |
| `~/.cursor/skills-cursor/` | **Existing** — Cloud Agent utilities (env-setup, walkthrough-artifacts, subscribe, …) — **keep** |
| `~/.cursor/plugins/.../skills/` | **Existing** — Figma, Datadog, GitLab CI — **keep** |
| `/workspace/.cursor/` | **Was missing** → **created** (rules, agents, custom skills) |
| `/workspace/.agents/skills/` | **Was missing** → **populated** via `npx skills add` |
| `~/.cursor/mcp.json` | **Missing** on cloud VM |
| `/workspace/.cursor/mcp.json` | **Missing** |
| Figma MCP | **Available, needsAuth** |
| Cursor Browser | **Available** (computerUse) |
| Image generation | **Available** (`GenerateImage`) |
| `AGENTS.md` | **Existing** — office onboarding, unchanged core |
| Frontend stack | **Next.js** — `delno-web/` (package.json), `DELNO-site-v23/` (Docker deploy, CSS landing) |

---

## Existing (kept)

- Cloud skills: `env-setup`, `migrate-to-builds`, `subscribe`, `walkthrough-artifacts`, `visualize`
- Plugin skills: full **Figma** suite, **gitlab-ci-author**, Datadog skills
- BDK skills under `$HOME/.cursor/skills-cursor/bdk-*` (not modified)
- `AGENTS.md`, `docs/P1.1_SITE_LANDING.md`, `docs/P1.5_MOBILE_PASS.md`

---

## Missing (before this task)

- Global/project **design** skills (apple-design, frontend-design, marketing, …)
- **Product marketing context** document
- **Custom orchestration** skills and **subagents**
- **Project rules** for design/UX/copy/CRO/visual verification
- **`docs/design/design-system.md`**

---

## Duplicate

- **None installed twice.**  
- **Naming aliases (not duplicates):** marketing repo uses `cro` (not `page-cro`), `emails` (not `email-sequence`), `social` (not `social-content`), `ab-testing` (not `ab-test-setup`), `pricing` (not `pricing-strategy`), `accessibility` (not `web-accessibility`), `product-marketing` skill + `.agents/product-marketing.md` file (different roles).

---

## Deprecated

- None removed. Old v4-as-default approach remains **deprecated by policy** in `P1.1`, not deleted.

---

## Recommended (installed this task)

### Emil Kowalski (`emilkowalski/skills`)

`apple-design`, `emil-design-eng`, `prototype`, `break-ui`, `animate`, `find-animation-opportunities`, `improve-animations`, `review-animations`, `mobile-native`

### MengTo (`MengTo/Skills`)

`design-first-ui-prompting`, `build-awwwards-quality-sites`, `animation-systems`, `gsap`, `optimize-web-animations`, `threejs` (optional runtime)

### Anthropic (`anthropics/skills`)

`frontend-design`

### UX / a11y

`magnus919/agent-skills@product-design-and-ux`, `addyosmani/web-quality-skills@accessibility`

### Marketing (`coreyhaines31/marketingskills`)

`product-marketing`, `customer-research`, `competitor-profiling`, `marketing-psychology`, `offers`, `copywriting`, `copy-editing`, `cro`, `pricing`, `content-strategy`, `seo-audit`, `ai-seo`, `signup`, `onboarding`, `ab-testing`, `analytics`, `social`, `emails`, `ads`

### Project-only custom (`.cursor/skills/`)

`premium-product-ui`, `apple-premium-web`, `design-system-architect`, `graphics-pipeline`, `visual-qa`, `conversion-copy-system`, `premium-web-workflow`

### Subagents (`.cursor/agents/`)

`creative-director`, `product-ux-designer`, `conversion-strategist`, `copy-chief`, `design-engineer`, `visual-qa`, `accessibility-reviewer`

### Rules (`.cursor/rules/`)

`00-product-quality.mdc` … `50-visual-verification.mdc`

---

## Installed during this task

- **40** upstream skills under `.agents/skills/` (see `skills-lock.json`)
- **7** custom skills, **7** subagents, **6** rules
- `.agents/product-marketing.md` + symlink `product-marketing-context.md`
- `docs/design/design-system.md`, `docs/cursor-studio-setup.md`, dry-run log

---

## Not installed (gaps)

| Item | Reason |
|------|--------|
| Dedicated Playwright skill | Use Browser/computerUse + `visual-qa` custom skill |
| Global `-g` skill copies | Project-scoped for git; run `npx skills add … -g` on local Cursor if desired |
| Figma MCP auth | User must authenticate in Cursor settings |
| `form-cro` as separate skill | Covered by `cro` + `signup` in marketingskills repo |

---

## Dry run

See **`docs/cursor-studio-dry-run.md`** — production `https://dlno.ru/` reviewed without code changes.
