# DELNO — единый мастер-план

**Версия:** 2026-09-01  
**Revision:** `DELNO-MASTER-PLAN-REV-3.2`  
**Commit:** см. tip `main` (ветка `cursor/delno-api-scaffold-14e9`, PR #20)  
**Статус:** canonical — по этому документу начинаем реализацию  
**Prod staging:** https://a.47z.ru/delno/ · https://a.47z.ru/delno-api/  
**Production domain (купленный):** **https://dlno.ru** — см. [`docs/DLNO_DOMAINS.md`](DLNO_DOMAINS.md)  
**Entry point для ChatGPT (отправляй только его, не этот файл):** [`docs/DELNO_FOR_CHATGPT.md`](DELNO_FOR_CHATGPT.md)

> **Если вы ChatGPT / ревьюер:** начни с `DELNO_FOR_CHATGPT.md`, затем открой связанные raw URL из «Карта документов».  
> Это **НЕ rev.1**. Проверка: в документе есть секции  
> `Product North Star`, `Product Roadmap vs Engineering Roadmap`,  
> `Temporary repository strategy`, `Voice Widget vs Telephony`, `Anti-scope-creep rule`.  
> Rev.1 начинался с «## 1. Что мы строим» без North Star.

### Rev.2 changelog (28 пунктов ревью — все ✅)

1. ✅ Product North Star  
2. ✅ Product vs Engineering Roadmap (P1 + E0–E10)  
3. ✅ Temporary monorepo strategy (`quantum-office` → `delno-platform`)  
4. ✅ Repository split triggers  
5. ✅ Product Guardrails (PARTNER → LEARN → BUILD)  
6. ✅ CRM boundary (integrations now, build later)  
7. ✅ Web Voice Widget раньше telephony  
8. ✅ Voice Widget vs PSTN/SIP разделены  
9. ✅ Model Provider Abstraction  
10. ✅ Commercial MVP exit criteria  
11. ✅ Product / Operations KPIs  
12. ✅ Supervisor — events с раннего этапа  
13. ✅ Explicit Event Model (domain / operational / automation)  
14. ✅ AI Operator long-term control plane  
15. ✅ Tool Registry abstraction  
16. ✅ Confirmation policy (READ / SAFE_WRITE / HIGH_IMPACT)  
17. ✅ Knowledge Provenance  
18. ✅ Second Brain v1 guardrail (не переусложнять)  
19. ✅ Channel Adapter contract  
20. ✅ MAX onboarding (bot belongs to customer)  
21. ✅ Telegram Instant + Branded  
22. ✅ Fallback architecture (voice → text → retry)  
23. ✅ Feature Flags per tenant  
24. ✅ Usage Metering as core service (early)  
25. ✅ Staged monetization  
26. ✅ Security baseline  
27. ✅ Exit-criteria based engineering phases  
28. ✅ Anti-scope-creep rule  

### Rev.3 changelog (implementation status — Sprint 0–2 ✅)

1. ✅ `delno-api` scaffold: JWT auth, admin tenants, CMS, public leads, feature flags, operator stub  
2. ✅ `delno-knowledge`: brain-only `main_delno.py`, prod `:18021`  
3. ✅ Prod stack `/opt/delno`: postgres + api `:18020` + knowledge + site staging `:18019` + site root `:18022`  
4. ✅ `delno-admin` + `delno-web` Next.js scaffolds  
5. ✅ Site leads proxy → delno-api PostgreSQL (staging verified 2026-09-01)  
6. ✅ Nginx ready for `dlno.ru` (DNS **reg.ru** pending — deferred)  
7. 🔄 Sprint 3 mid-flight: P0 backend mostly done → **Product P1 exit + E0/E1 formal exit + events** pending (см. roadmap REV-3.2)  

**Детальный checklist:** [`DELNO_IMPLEMENTATION_ROADMAP.md`](DELNO_IMPLEMENTATION_ROADMAP.md)

### Rev.3 — Implementation Status

| Sprint | Статус | Ключевое |
|--------|--------|----------|
| S0 | ✅ | brain extract, auth, admin tenants, KnowledgeAdapter, tests |
| S1 | ✅ | prod stack staging на `a.47z.ru/delno` |
| S2 | ✅ | CMS, public API, channel router, admin/web scaffolds |
| S3 | 🔄 mid-flight | ✅ isolation, ACL, brain, leads, FAQ, Operator, events, E0/E1 formal exit · ⬜ mobile, legal · ⏸ clarity · DNS deferred |

**Dev credentials (seeded):** `admin@delno.one` / `admin123456`, `owner@delno.one` / `demo123456`

---

## Product North Star

**Сегодня:** DELNO — ИИ-сотрудник первой линии для бизнеса: отвечает клиентам на сайте, по телефону, в Telegram, MAX и email, консультирует, принимает заявки и записывает.

**Долгосрочно:** DELNO развивается в **AI Operating Layer for SMB** — единый разговорный интерфейс, через который предприниматель управляет коммуникациями, CRM, booking, автоматизациями и подключёнными бизнес-сервисами.

Пользователь не должен вручную настраивать десятки интерфейсов. Он формулирует задачу естественным языком, а DELNO выполняет действия через backend tools, интеграции и automations.

**Принцип scope:** архитектура текущих этапов **не блокирует** это развитие, но будущие модули **не попадают** в scope текущего milestone без явного approval.

Мы строим **не contact-center SaaS**, а основу более широкой системы.

---

## Product Roadmap vs Engineering Roadmap

У DELNO параллельно существуют **два roadmap**. Не путать их приоритеты.

### Product Roadmap

| Product Phase | Milestone | Цель |
|---------------|-----------|------|
| **P1 — Selling Website** ⬅️ **текущий** | Clarity test | За 5–10 сек новый пользователь понимает: DELNO = ИИ-сотрудник; отвечает клиентам; работает по телефону, на сайте, в мессенджерах; консультирует, принимает заявки, записывает; как попробовать |
| P2 | First Value | Регистрация → KB → widget/voice demo → первый lead |
| P3 | Paid pilots | Billing + 1–2 канала per tenant |
| P4 | Scale | Telephony multi-tenant, self-service |

**Правило:** инженерная работа **не сдвигает** product milestone. До прохождения clarity-test сайта продукт считается в **Product Phase 1**.

### Engineering Roadmap

| Eng Phase | Фокус |
|-----------|-------|
| E0 | Foundation + repo boundaries + auth/tenant primitives |
| E1 | Knowledge / Second Brain v1 |
| E2 | Unified Communication Core + Telegram/MAX/email |
| E3 | **Web Widget + Voice Widget MVP** + Tenant Operator |
| E4 | Telephony multi-tenant (PSTN/SIP) |
| E5 | Self-service onboarding + billing + usage |
| E6 | Supervisor + self-healing |
| E7 | Partner / referral |
| E8 | CRM Lite / Booking — **только при triggers** |
| E9 | Marketplace / bank distribution |
| E10 | Business OS expansion |

Engineering Phase 0–1 может идти **параллельно** Product Phase 1, но не отменяет его.

---

## Product Guardrails

До подтверждённого usage **нельзя** начинать крупную реализацию:

- CRM (full)
- marketplace
- ERP
- marketing platform
- собственных payment rails
- полной booking platform
- banking layer

**Правило новых модулей:** `PARTNER → LEARN → BUILD`

1. Интегрировать партнёра  
2. Дать клиентам использовать  
3. Измерить adoption, revenue, support burden  
4. Только потом — собственная реализация  

---

## 1. Что мы строим (кратко)

**DELNO** — multi-tenant SaaS «ИИ-сотрудник»: у каждого клиента свой телефон, мессенджеры, сайт/виджет, голос и KB с **уровнями доступа**.

**Один platform backend** (`delno-api`) + **три UI** (site, cabinet, admin).

---

## 2. Три знаменателя

| Категория | Смысл | Примеры |
|-----------|-------|---------|
| **A. Есть** | На prod, as-is или reference | Second Brain, AVA Voice, delno-site stack |
| **B. Переносим** | prod → git → multi-tenant | `brain_platform`, text-bot loop, voice patterns |
| **C. Строим** | DELNO-специфика | Auth, channel router, CMS, billing, events |

**Правило:** KB/ACL не с нуля — **переносим Second Brain (B)**. Runtime Quantum Office не coupling — **изолированный `/opt/delno` (C)**.

---

## 3. Inventory prod (что есть)

### 3.1. DELNO stack

| Компонент | Путь / URL | Состояние |
|-----------|------------|-----------|
| delno-site | `/opt/delno/site`, `:18019`, `/delno/` | ✅ лендинг v23 |
| delno-api | `/opt/delno/api`, `:18020`, `/delno-api/` | ✅ scaffold |
| delno-postgres | Docker `delno-internal` | ✅ |
| secrets | `/opt/delno/.env` | ✅ только DELNO |

### 3.2. Second Brain (наша KB)

| Параметр | Значение |
|----------|----------|
| Сервис | `ava-knowledge.service` → `:8017` |
| Код | `/opt/ava-knowledge/brain_platform/` (~62 файла) |
| **Не в git** | prod опережает репозиторий |
| Данные | 1530 docs, 8493 chunks (embedded), hybrid FTS+vector+RRF |
| Tenant | один: `quantum-labs` |

### 3.3. Quantum Office (reference)

| Сервис | Переносим? |
|--------|------------|
| ava-knowledge (Second Brain) | **B** → `delno-knowledge` |
| ava-text-bot | **B** agent loop, principals |
| AVA Voice | **B** patterns → `delno-voice` |
| ava-outreach, polyhub, `/root/ava` | **не трогаем** |

---

## 4. Temporary repository strategy

DELNO **временно** разрабатывается внутри `quantum-office`. Это **организационное** решение, не целевая архитектура.

**Причины:**
- рядом работающие телефония, Telegram, MAX, email, knowledge, AI;
- Cursor быстрее анализирует существующий код;
- проще поэтапный перенос компонентов;
- не дробим codebase преждевременно.

**Требования (проектировать как отдельный продукт):**
- собственный namespace/packages (`delno-api/`, `delno-knowledge/`, …);
- собственные config/env, migrations, API routes;
- **нет** жёстких импортов из бизнес-слоёв Quantum Office;
- интеграции только через **explicit adapters/interfaces**;
- отдельный build/deploy (`/opt/delno`).

**Целевое состояние:**

```
repos/
├── quantum-office
└── delno-platform      ← после стабилизации core
```

### Repository split triggers

Перенос в `delno-platform`, когда выполняется **большинство**:

1. стабилен package boundary DELNO;
2. tenant/auth/knowledge/communication abstractions перестали существенно меняться;
3. DELNO запускается отдельно от Quantum Office;
4. собственные migrations + environment config;
5. собственный CI/test contour;
6. зависимости от QO вынесены в adapters;
7. совместная разработка создаёт риск случайных изменений prod QO.

**Не переносить** только ради архитектурной чистоты раньше времени.

---

## 5. Целевая архитектура

```
delno-web / delno-admin / delno-site / delno-voice-widget
         ↓
    delno-api
    Auth │ Tenants │ Channels │ Operator │ Events │ Usage │ Billing
    Channel Router │ Tool Registry │ Model Provider Abstraction
         ↓
    delno-knowledge  ← fork brain_platform (ACL, hybrid search)
```

**Prod layout:** `/opt/delno/` — site, api, postgres, knowledge (изолированно).

---

## 6. Second Brain → delno-knowledge

### 6.1. Переносим as-is (B)

`security/acl.py`, `security/zones.py`, `search/`, `ingest/`, `db/`, `schemas/`, `api/router.py`, security tests.

### 6.2. Адаптируем (B → C)

| Было | Станет |
|------|--------|
| `quantum-labs` single tenant | tenant_id per client |
| Hardcoded principals | + DELNO channel principals (§6.4) |
| Один vault | `vault/{tenant_slug}/` |
| `office-assistant` channel | + auto-ingest настроек кабинета |

### 6.3. Knowledge v1 guardrail

**DELNO Knowledge v1** prioritizes:

- reliable tenant isolation;
- retrieval quality;
- source provenance;
- tenant scope;
- versioning.

**Не в v1:** long-term episodic memory, adaptive memory, cross-conversation inference — только после подтверждённого usage.

### 6.4. ACL levels (уже реализованы)

**Visibility:** `public` → `company` → `team:*` → `restricted` → `secret`  
**Channel:** `office-assistant` — настройки кабинета (voice-office видит, voice-public — нет)  
**ACL in-query** + audit log.

| Сценарий | Principal | Видит |
|----------|-----------|-------|
| Внешний звонок / widget guest | `service:delno-voice-public` / `delno-widget-guest` | `public` (published) |
| Голосовой помощник в кабинете | `service:delno-voice-office` | `public` + `office-assistant` |
| Owner в cabinet | `service:delno-text-owner` | вся KB tenant |
| Platform admin | `service:delno-admin` + `X-Admin` | full (audit) |

### 6.5. Knowledge Provenance

Каждый AI answer должен нести metadata источника:

```
document_id, chunk_id, source_type, source_url, version, updated_at
```

Нужно для: доверия, debug, hallucination analysis, UI «Источник ответа».

---

## 7. Voice Widget vs Telephony (разные продукты)

| | Voice Widget | Telephony (PSTN/SIP) |
|---|--------------|----------------------|
| **Инфра** | браузер, WebRTC, Realtime | SIP/PSTN, Mango/Asterisk |
| **Eng phase** | **E3** (раньше) | **E4** (позже) |
| **Зависимости** | KB, tenant context, widget key | номер, billing/min, transfer |
| **MVP** | text + voice в браузере | incoming/outgoing calls |

**Web Voice Widget MVP does not depend on full multi-tenant telephony rollout.**

Telephony infrastructure может оставаться позже; widget — **главный sales differentiator**, переносим в E3.

### Fallback architecture (voice + channels)

При сбое (TTS, Realtime, channel timeout, LLM error) пользователь **не в тупике**:

```
voice failed → show text → retry → alternate provider → graceful handoff
```

Обязательная часть production architecture с E3.

---

## 8. Каналы

### 8.1. Channel Adapter contract

```python
class ChannelAdapter:
    connect()
    disconnect()
    send_message()
    receive_event()
    healthcheck()
    validate_credentials()
```

Telegram / MAX / email / telephony — взаимозаменяемые реализации.

### 8.2. Telegram — два режима

| Режим | Описание |
|-------|----------|
| **Instant** | Общий DELNO bot / Mini App — быстрый conversion, demo |
| **Branded** | Бот клиента — commercial product |

### 8.3. MAX onboarding

- MAX bot **принадлежит клиенту** — клиент создаёт/верифицирует сам;
- DELNO получает token/key → validation → webhook → agent → knowledge → test → production;
- **Не создавать** тысячи MAX bots от аккаунта DELNO.

### 8.4. Channel Router

| Вход | Lookup | Principal |
|------|--------|-----------|
| Widget | `tenant_public_key` | widget-guest |
| Telegram webhook | bot token → channel_account | text-guest / text-owner |
| MAX webhook | token → channel_account | text-guest / text-owner |
| Inbound call | `phone_numbers.e164` | voice-public / voice-office |
| Cabinet operator | JWT | text-owner |

---

## 9. AI Operator + Tool Registry

### 9.1. Роль Operator

**Сейчас:** setup + support assistant в кабинете.

**Долгосрочно:** natural-language control plane для CRM, booking, automation, marketing, analytics, partner services.

Не воспринимать как «чат настроек» — **extensible tool architecture**.

### 9.2. Tool Registry

```
Agent → Tool Registry → Authorized Tool → Domain Service
```

У каждого tool:

| Поле | Назначение |
|------|------------|
| `name` | идентификатор |
| `scope` | tenant / platform |
| `required_permissions` | RBAC |
| `confirmation_class` | READ / SAFE_WRITE / HIGH_IMPACT |
| `tenant_context` | injected backend-side |
| `audit_policy` | always / on_write |
| `rate_limit` | per tenant |

### 9.3. Confirmation policy

| Класс | Поведение | Примеры |
|-------|-----------|---------|
| **READ** | автоматически | get_knowledge, list_conversations |
| **SAFE_WRITE** | implicit/explicit confirm по context | update_hours, create_lead |
| **HIGH_IMPACT** | только explicit confirm | mass campaign, delete KB, payment, disconnect integration, bulk call, change pricing, remove users |

---

## 10. Model Provider Abstraction

DELNO **не привязан** к одной LLM/voice platform.

Все model calls → **provider abstraction**:

- OpenAI, Anthropic, Gemini;
- российские providers;
- local/self-hosted;
- отдельные voice/STT/TTS providers.

Бизнес-логика, tenant context и tools **не зависят** от конкретного provider. Смена модели = config change, не rewrite продукта.

---

## 11. Event Model + Supervisor foundation

### 11.1. Типы событий

| Тип | Примеры |
|-----|---------|
| **Domain** | `message.received`, `lead.created`, `call.completed`, `booking.created` |
| **Operational** | `integration.status_changed`, `webhook.failed`, `channel.disconnected`, `agent.error`, `voice.error`, `payment.failed` |
| **Automation** | `usage.limit_reached`, `workflow.triggered` |

Фундамент для: automation engine, supervisor, billing, analytics.

### 11.2. Supervisor

**Even before Supervisor Agent UI exists, platform services must emit structured operational events.**

Supervisor позже станет потребителем этих events — закладываем с E0/E1.

---

## 12. CRM boundary

DELNO может содержать **CRM-like primitives**: Contact, Lead, Conversation, Task, basic pipeline state.

**Это не означает** full CRM в текущем scope.

| | |
|---|---|
| **Сейчас** | primitives + integrations (Bitrix24, amoCRM, …) |
| **CRM Lite / Full** | только при triggers |

**Triggers для собственной CRM:**
- ~300+ active tenants;
- 30% tenants используют CRM-like data;
- внешние CRM — UX/support bottleneck;
- доказанная готовность платить.

---

## 13. Core services (с раннего этапа)

### 13.1. Usage Metering — core, не «потом»

Считать с E0/E1:

- LLM tokens;
- voice seconds/minutes;
- messages;
- calls;
- channel events;
- tool executions.

Без этого невозможны unit economics и billing.

### 13.2. Feature Flags (per tenant)

`web_voice`, `telegram`, `max`, `phone`, `outbound_calls`, `experimental_operator`, `crm_lite`

→ pilot, gradual rollout, без fork кода.

### 13.3. Security baseline

- encrypted secrets + rotation readiness;
- signed webhooks;
- RBAC + audit;
- tenant scoping;
- rate limits;
- API keys + session security;
- PII minimization;
- deletion/export path.

### 13.4. Staged monetization

| Этап | Модель |
|------|--------|
| Сейчас | subscription + usage |
| Потом | add-ons |
| Далее | partner marketplace |
| Ещё позже | bank / reseller / embedded |

Billing architecture не предполагает один фиксированный тариф.

---

## 14. Product / Operations KPIs

Минимально отслеживать:

- visitor → demo conversion;
- demo → lead → paid → activated;
- **time to first value** (target: **< 15 min** simple onboarding);
- active tenants;
- conversations per tenant;
- voice minutes;
- autonomous resolution rate;
- **human minutes per active tenant per month** ← **top-level KPI**;
- churn, ARPU;
- AI cost per tenant;
- telephony cost per tenant;
- gross margin.

---

## 15. Engineering Roadmap (exit-criteria based)

Каждая фаза = задачи **+ exit criteria** (tests, latency, metrics, feature flags).

### E0 — Foundation ⬅️ engineering start

| Задачи | Exit criteria |
|--------|---------------|
| Repo boundaries, package structure | delno-* изолированы от outreach/mailer/text-bot imports |
| Auth JWT + roles | login/register works; RBAC middleware |
| Migrations: channel_accounts, phone_numbers, tenant_voice_profiles | alembic up/down clean |
| Event emitter skeleton | operational events logged |
| Usage meter stub | counters increment on API calls |
| Feature flags table | per-tenant toggle works |

### E1 — Knowledge / Second Brain v1

| Задачи | Exit criteria |
|--------|---------------|
| Extract brain_platform → `delno-knowledge/` | tests pass locally + CI |
| Docker in `/opt/delno` stack | health OK on prod |
| KnowledgeAdapter → `/api/brain/search` + principal | ACL smoke: guest ≠ owner |
| Knowledge provenance in responses | document_id/chunk_id present |
| Tenant vault isolation test | cross-tenant search returns empty |

### E2 — Communication Core

| Задачи | Exit criteria |
|--------|---------------|
| Channel adapters (Telegram Instant + Branded skeleton) | connect/disconnect/healthcheck |
| MAX onboarding flow (client-owned bot) | token validation + webhook |
| Email adapter stub | receive_event interface |
| Router: token → tenant → principal | integration test |
| Webhook signing + retry | security test |

### E3 — Web Widget + Voice Widget MVP + Operator

| Задачи | Exit criteria |
|--------|---------------|
| Embeddable widget (text + voice WebRTC) | demo on staging tenant |
| KB + lead capture + basic handoff | lead in delno-api PG |
| Operator LLM + tool registry + confirmation classes | HIGH_IMPACT blocked without confirm |
| Fallback: voice→text | manual test passes |
| Mobile web voice UX | works on phone browser |
| **No PSTN required** | widget works without phone_numbers |

### E4 — Telephony multi-tenant

| Задачи | Exit criteria |
|--------|---------------|
| phone_numbers provisioning (Mango/SIP) | pending → active flow |
| delno-voice worker per call | Realtime + tenant config |
| Post-call transcript → inbox | call.completed event |
| Billing per minute | usage_records populated |

### E5 — Self-service + billing

Registration → tenant → KB → channel → test → pay. Time to First Value < 15 min.

### E6 — Supervisor + self-healing

Supervisor UI consumes operational events from E0.

### E7–E10

Partner/referral → CRM Lite (triggers only) → marketplace → Business OS.

---

## 16. Product Phase 1 — Selling Website (текущий product milestone)

**Параллельно с E0/E1**, но **не отменяет** clarity test.

| Задача | Done when |
|--------|-----------|
| Hero: «ИИ-сотрудник» за 5 сек | clarity test passed |
| Каналы: телефон, сайт, мессенджеры | visible on page |
| Demo CTA: попробовать голос/чат | works (even static → brain later) |
| Leads → delno-api | not local site API |
| Mobile-friendly | lighthouse OK |

**Exit:** 5–10 sec clarity test; lead capture works; demo path exists.

---

## 17. Sprints (engineering + Product P1)

### Sprint 0–1 ✅ (done)

```
E0 + E1 start:
  1. brain_platform → delno-knowledge/ + Dockerfile
  2. delno-api: JWT auth, channel_accounts migration
  3. KnowledgeAdapter → /api/brain/search + principals
  4. Event emitter stub + usage meter stub
  5. Feature flags table
  6. Admin: create/list tenants
  7. Prod stack staging (api + knowledge + postgres + site)
```

### Sprint 2 ✅ (done)

```
  8. CMS models + admin CRUD draft/publish
  9. Public API: leads, published CMS pages
 10. Channel router skeleton + model provider stub
 11. delno-admin + delno-web scaffolds
 12. Site leads proxy → delno-api (code ready)
```

### Sprint 3 🔄 (mid-flight — см. [`DELNO_IMPLEMENTATION_ROADMAP.md`](DELNO_IMPLEMENTATION_ROADMAP.md) REV-3.2)

**Backend core mostly done; Product P1 exit not done.**

```
P0 — done (backend):
  ✅ E0.13 cross-tenant isolation + E1.3 ACL smoke (CI)
  ✅ E1.2 brain init-db + demo vault + tenant-scoped search
  ✅ P1.4 site → POST /v1/public/leads → PostgreSQL (staging)
  ⏸ P1.6/P1.7 dlno.ru + api.dlno.ru + SSL (DNS reg.ru deferred)

P1 — product (partial):
  🔄 P1.1–P1.3 hero v4 / channels / CTA on staging — визуально готов, не валидирован (P1.9)
  ⬜ P1.5 mobile · ⬜ P1.8 privacy/terms · ⬜ P1.9 clarity test (3+ людей)
  ✅ E1.7 FAQ from CMS
  ⬜ E1.4 unified provenance in delno-api responses

P2 — operator foundation (partial):
  ✅ E3.2 basic Operator LLM — read-only KB
  ✅ E0.15 operational events (lead.created, auth.failed, operator.error, knowledge.search_failed)
  ⬜ E0.14 / E1.11 formal exit (admin → tenant/CMS → site)
  🔄 docs sync REV-3.2
```

**Exit Sprint 3:** все пункты exit criteria в roadmap одновременно выполнены.

**DO NOT START:** CRM, marketplace, telephony E4, billing payments, repo migration, advanced Tool Registry, mass actions.

---

## 18. Commercial MVP exit criteria

DELNO готов к первому коммерческому масштабированию, если:

- [ ] self-service регистрация + создание tenant;
- [ ] загрузка/импорт знаний;
- [ ] подключён минимум один канал;
- [ ] проведён тест → первый рабочий ответ;
- [ ] типовая проблема решается через AI Operator;
- [ ] usage считается;
- [ ] billing работает;
- [ ] tenant isolation (automated tests);
- [ ] basic monitoring;
- [ ] lead с сайта → backend;
- [ ] mobile web/voice UX;
- [ ] **Time to First Value < 15 min**;
- [ ] human support time измеряется;
- [ ] Quantum Office prod не сломан.

---

## 19. Карта переноса (A → B → C)

| Источник | Цель | Eng Phase |
|----------|------|-----------|
| `brain_platform/` | `delno-knowledge/` | E1 |
| `delno-api` scaffold | auth, events, usage | E0 |
| `DELNO-site-v23` | clarity + CMS | P1 / E1 |
| ava-text-bot loop | delno-api operator | E3 |
| AVA Realtime | voice widget + delno-voice | E3 / E4 |
| ava-text-bot webhooks | delno-api webhooks | E2 |

---

## 20. Tech stack

| Layer | Choice |
|-------|--------|
| API | FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16 |
| Knowledge | brain_platform fork (SQLite v1 → pgvector v2) |
| Models | Provider abstraction (OpenAI first, swappable) |
| Auth | JWT + refresh, bcrypt |
| UI | Next.js, Tailwind, shadcn |
| Voice widget | WebRTC + Realtime (browser) |
| Telephony | Mango/SIP worker (E4) |
| Deploy | Docker `/opt/delno`, systemd `delno-stack` |

---

## 21. Риски

| Риск | Митигация |
|------|-----------|
| Product P1 blocked by engineering | Parallel tracks; P1 = site clarity first |
| brain_platform не в git | E1.1 extract первым |
| Scope creep (CRM, marketplace) | Guardrails + anti-scope-creep rule |
| Single LLM vendor lock-in | Provider abstraction E0 |
| Widget delayed by telephony | E3 before E4 explicitly |

---

## 22. Связанные документы

| Документ | Назначение |
|----------|------------|
| `docs/DELNO_MASTER_PLAN.md` | **этот файл — canonical** |
| `docs/DELNO_FOR_CHATGPT.md` | entry point + raw URLs для ревью |
| `docs/DELNO_IMPLEMENTATION_ROADMAP.md` | checklist + статус Sprint 0–3 |
| `docs/DLNO_DOMAINS.md` | dlno.ru DNS (reg.ru) и nginx |
| `docs/P1.9_CLARITY_TEST.md` | clarity test protocol |
| `delno-api/docs/DEPLOY_ISOLATION.md` | prod deploy |
| `DELNO-site-v23/docs/00_MASTER_SPEC.md` | product vision |
| `delno-api/AGENTS.md` | API onboarding |

---

## 23. Anti-scope-creep rule

**If a requested implementation belongs to a future roadmap phase, Cursor must not silently include it in the current milestone.**

It must document the dependency and defer implementation unless explicitly approved.

---

## 24. Резюме

1. **North Star:** ИИ-сотрудник сегодня → AI Operating Layer for SMB долгосрочно.
2. **Два roadmap:** Product P1 (Selling Website) **параллельно** Engineering E0–E1.
3. **Second Brain — фундамент KB**, не пишем с нуля; v1 = isolation + retrieval, не memory overkill.
4. **Voice Widget (E3) раньше Telephony (E4)** — sales differentiator без PSTN.
5. **Monorepo временно**, split по triggers, не по календарю.
6. **Usage metering + events + feature flags** — с раннего этапа.
7. **CRM/marketplace/banking** — guardrails, PARTNER → LEARN → BUILD.

**Следующий шаг:** P1.5 mobile pass → P1.8 legal → (P1.9 clarity когда вернётесь).
