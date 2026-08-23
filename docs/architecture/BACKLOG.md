# BACKLOG — AI Revenue OS

Связано: [AS_IS](./AS_IS.md) · [TARGET](./TARGET_ARCHITECTURE.md) · [GAP](./GAP_ANALYSIS.md) · [DATA_MAPPING](./DATA_MAPPING.md) · [MIGRATION_PLAN](./MIGRATION_PLAN.md)

Источник требований: `Quantum_Console_AI_Revenue_OS_Cursor_Spec.md` v1.1.

---

## Epic 0 — Foundation docs ✅

- [x] AS_IS architecture
- [x] TARGET architecture
- [x] GAP analysis + social capability matrix
- [x] DATA_MAPPING (AS-IS → canonical)
- [x] Migration plan + backlog
- [x] Human Accept R1–R4 (defaults applied in Stage 1)

---

## Epic 1 — Data core

| ID | Item | Depends | Size | Status |
|----|------|---------|------|--------|
| D1 | Merge PR #10 (outreach A–G3) | — | ops | 🟡 branch base |
| D2 | `tenant_id` default + enforced filters | D1 | S | ✅ accounts module |
| D3 | Account facade + lifecycle enum | D1 | M | ✅ |
| D4 | Person + Employment + ContactPoint | D3 | M | ✅ |
| D5 | Consent ↔ BLACKLISTED mapping | D3 | S | ✅ resolve + send_guards + suppress |
| D6 | Event envelope + writers reply/call | D2 | M | ✅ |
| D7 | Tenant config package quantum-labs | D1 | S | ✅ |
| D8 | Company timeline API | D3,D6 | M | ✅ account timeline |

---

## Epic 2 — Slice A Unified inbound

| ID | Item | Depends | Status |
|----|------|---------|--------|
| A1 | Normalize `message.received` / `call.completed` | D6 | ✅ |
| A2 | Account/Person resolve on inbound | D3,D4 | ✅ |
| A3 | Inbox enrichment panel (account side) | A2 | ✅ peel-away panel |
| A4 | Suggested next action (meeting/task/reply) | A2 | ✅ rules-first |
| A5 | Optional SB-cited reply draft (approval) | knowledge | ✅ best-effort brain/knowledge |
| A6 | Local Lead record + Bitrix adapter | D3 | ✅ local Lead |
| A7 | E2E tests A1–A5 from MIGRATION_PLAN | A1–A6 | 🟡 unit tests |

---

## Epic 3 — Slice B LPR search

| ID | Item | Depends | Status |
|----|------|---------|--------|
| B1 | `SocialSourceAdapter` + capability registry | D2 | ✅ |
| B2 | Adapters: clients, dadata, web_import, telegram | B1 | ✅ |
| B3 | Stub adapters vk/ok/tenchat/linkedin (import/manual) | B1 | ✅ |
| B4 | LPRSearchRun + CandidateProfile scoring | B2 | ✅ |
| B5 | IdentityCluster + approve/reject API (UI later) | B4 | ✅ API + UI |
| B6 | Committee coverage matrix | B4,D7 | ✅ API + UI |
| B7 | SocialActionTask | B5 | ✅ API + UI |
| B8 | Cost accounting per search run | B4 | ✅ |
| B9 | E2E tests B1–B6 | B5–B7 | 🟡 unit |

---

## Epic 4 — Orchestrator

| ID | Item | Status |
|----|------|--------|
| O1 | JourneyDefinition versioning wrapping sequences | ✅ scaffold |
| O2 | Global guardrails (consent, quiet hours, caps) | 🟡 consent+blacklist in send_guards; quiet hours via existing windows |
| O3 | Approval / MANUAL_TASK nodes | ✅ in journey JSON |
| O4 | Dry-run mode | ✅ `/dry-run` |

---

## Epic 5+ — Later

Content Studio · Video Studio · Intent Radar · Multi-tenant onboarding · RBAC · Usage metering.

См. этапы 5–8 в MIGRATION_PLAN.

---

## Definition of Ready (для любой задачи)

1. Ссылка на раздел ТЗ / ADR.
2. AS-IS компонент для reuse указан.
3. Acceptance test написан до кода.
4. Нет скрытой browser automation.
5. Cost/observability plan если есть external API.
