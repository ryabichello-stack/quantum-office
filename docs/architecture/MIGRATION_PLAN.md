# MIGRATION PLAN — к AI Revenue OS

**Дата:** 2026-08-23  
**Правила:** вертикальные срезы; не дублировать outreach/AVA/Second Brain; миграции обратимы; не browser automation.

---

## 0. Предусловия

1. **Merge PR #10** (Layers A–G3 outreach control plane) в `main`.
2. Зафиксировать baseline тестов: `outreach/tests` (40+), sync UI script.
3. Не трогать Asterisk / polyhub / prod `.env` без runbook.

---

## 1. Этапы (синхрон с ТЗ §21)

| Этап | Название | Зависимости | Критерий готовности |
|------|----------|-------------|---------------------|
| **0** | Аудит | — | Этот пакет docs ✅ |
| **1** | Ядро данных + события | Merge #10 | Account/Person/Consent/Evidence timeline; email+call+profiles в одной карточке |
| **2** | Unified Inbox + inbound | Этап 1 | Slice A E2E |
| **3** | Social Intelligence / LPR | Этап 1 | Slice B E2E (хотя бы import+manual adapters) |
| **4** | Orchestrator + outreach wrap | 2–3 | Journey stop на reply атомарно |
| **5** | Content Studio | 1 + SB | Call objection → approved content pack |
| **6** | Video Studio | 5 | Private YouTube draft + approval |
| **7** | Radar / intent-first | 3 | Signals → verification → action |
| **8** | Productization | 1–4 | Новый tenant без правок кода |

---

## 2. Этап 1 — конкретные миграции

### 2.1 Данные

| Шаг | Действие | Откат |
|-----|----------|-------|
| 1.1 | Добавить `tenant_id` default `quantum-labs` в outreach clients/outbox/consent | DROP COLUMN / ignore |
| 1.2 | Таблица `accounts` (или rename view поверх `companies`) + `lifecycle_status` | DROP |
| 1.3 | Таблица `people` + `employments` + map contacts | DROP |
| 1.4 | `contact_points` с verification_status | DROP |
| 1.5 | Mapping consent → `BLACKLISTED` / suppression | Reversible map table |
| 1.6 | `events` / outbox_events (envelope) | Truncate |
| 1.7 | Backfill из Bitrix mirror + outbox emails | Re-run sync |

**Не удалять** колонки Bitrix ids и outbox statuses.

### 2.2 API facade (без breaking UI)

- `GET /api/v1/accounts/{id}` → wrap `company_card`
- `GET /api/v1/people?account_id=`
- `GET /api/v1/conversations` → wrap reply_inbox
- Сохранить `/api/modules/*` до deprecation window

### 2.3 Config packages (файлы/JSON, не код)

Первый tenant package в `config/tenants/quantum-labs/`:

- `product_profile.json` (Quantum Labs / Payouts как продукты)
- `icp_template.json` (ломбарды)
- `decision_role_template.json` (CEO, CFO, accountant, …)
- `channel_policy.json`

---

## 3. Slice A — Unified inbound (первый код после Этапа 0)

### Scope

1. Нормализовать событие `message.received` / `call.completed`.
2. Resolve/create Account+Person (из email / phone / company_id).
3. Показать в Inbox (уже thread) + enrichment panel.
4. Classification → suggested next action (meeting / reply / task).
5. Optional: suggested reply draft из Second Brain claims (APPROVAL_REQUIRED).
6. Создать/обновить Lead record (локально) + Bitrix sync как adapter.
7. Audit log + usage record.

### Acceptance tests

| ID | Сценарий | Pass |
|----|----------|------|
| A1 | IMAP reply → один Account/Person, sequence stop | 🟡 resolve+event; stop via existing sequences |
| A2 | Operator reply из UI → Message outbound в thread | ✅ Layer G |
| A3 | Call completed → event + Inbox note / task | 🟡 console → resolve-inbound |
| A4 | Unsubscribe → suppression blocks send | 🟡 lifecycle BLACKLISTED |
| A5 | Duplicate email не создаёт второй Person | ✅ unit |

### Не в scope Slice A

Social search, Content Studio, multi-tenant UI, video.

---

## 4. Slice B — Universal LPR search (второй код)

### Scope (MVP)

1. `SocialSourceAdapter` interface + capability registry.
2. Adapters v0:
   - `bitrix` / `clients` (существующие контакты)
   - `dadata` / registry
   - `web_import` (URL paste)
   - `telegram` (username import)
   - stubs: `vk`, `ok`, `tenchat`, `linkedin` с capability `import_only` / `manual`
3. `LPRSearchRun` + `CandidateProfile` + score breakdown (rules first).
4. Identity cluster **APPROVAL_REQUIRED** merge UI.
5. Committee coverage matrix (roles × sources).
6. `SocialActionTask` → open profile URL + approved draft.

### Acceptance tests

| ID | Сценарий | Pass |
|----|----------|------|
| B1 | Company + role template → candidates from ≥2 sources | |
| B2 | Same person 2 URLs → cluster proposal, not auto-merge | |
| B3 | Reject candidate → not used in outreach | |
| B4 | Coverage shows missing roles | |
| B5 | Manual task stores result without auto-DM | |
| B6 | Cost estimate logged per run | |

### Не в scope Slice B

Intent-first monitoring, cold auto-DM, LinkedIn unofficial scrapers.

---

## 5. Backlog (приоритет)

### P0 — сейчас

- [x] Stage 0 docs (AS_IS, TARGET, GAP, MIGRATION)
- [ ] Merge outreach PR #10
- [x] Этап 1.1–1.5 data foundations (accounts module)
- [x] Slice A implementation (resolve + enrichment + next_action)

### P1 — первый продаваемый контур

- [x] Slice B MVP adapters + verification API (UI later)
- [x] DecisionRoleTemplate for Quantum Labs tenant
- [x] SocialActionTask API (Panel UI later)
- [x] Lead local (+ Bitrix adapter later)
- [x] Second Brain citations in suggested reply

### P2

- [x] Revenue Orchestrator journeys (wrap sequences) — scaffold
- [x] Intent-first signals — Radar MVP API
- [x] Owned-page listening (Telegram/VK when capable)
- [x] Content Studio MVP — objection → draft API
- [x] YouTube private upload path

### P3

- [x] Multi-tenant onboarding
- [x] RBAC roles
- [x] Usage metering / billing readiness
- [ ] Video generative providers

---

## 6. Решения, требующие подтверждения (Accept)

| # | Вопрос | Рекомендация | Статус Stage 1 |
|---|--------|--------------|----------------|
| R1 | SoT компаний: Bitrix или local Account? | Local Account + Bitrix sync adapter | **Accepted (default)** — `modules/accounts` |
| R2 | Где хранить Account DB? | `outreach/data` / modules.db | **Accepted** — `MODULES_DB` |
| R3 | LLM для inbox classification сейчас? | Сначала rules | **Accepted** |
| R4 | Порядок: Slice A до или после merge #10? | После merge / поверх ветки G3 | **Accepted** — branch `cursor/revenue-os-stage1-9b51` |
| R5 | Отдельный сервис `social-intel`? | Нет до нагрузки | **Accepted** — `modules/social` in outreach |
| R6 | ADR Second Brain Accept? | Переиспользовать brain_platform | Pending |

### Stage 1 shipped (this branch)

- `outreach/modules/accounts` — Account / Person / Employment / ContactPoint / Lead / domain_events
- Lifecycle `NEW`…`BLACKLISTED`
- Inbound resolve on IMAP reply + `message.received` / `message.classified` events
- Console call watcher → `resolve-inbound` + `call.completed` event
- Tenant config seed: `outreach/config/tenants/quantum-labs/*`
- API: `/api/modules/accounts/*`

---

## 7. Следующий рекомендуемый шаг после Accept Stage 0

```text
1) Merge PR #10
2) Этап 1: Account/Person/lifecycle + event envelope (тонкий слой)
3) Slice A: unified inbound E2E
4) Slice B: LPR search MVP (import + manual + coverage UI)
```

Без Accept на R1–R4 не начинать массовый рефакторинг клиентов Bitrix.
