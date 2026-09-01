# DELNO — единый мастер-план

**Версия:** 2026-09-01  
**Статус:** canonical — по этому документу начинаем реализацию  
**Prod staging:** https://a.47z.ru/delno/ · https://a.47z.ru/delno-api/

---

## 1. Что мы строим (одной фразой)

**DELNO** — коммерческий multi-tenant SaaS «ИИ-сотрудник»: у каждого клиента свой телефон, мессенджеры, сайт/виджет, голос и база знаний с **уровнями доступа** (внутреннее для кабинета vs публичное для клиентов).

**Один platform backend** (`delno-api`) + **три UI** (site, cabinet, admin).

---

## 2. Три знаменателя (чтобы не путаться)

| Категория | Смысл | Примеры |
|-----------|-------|---------|
| **A. Есть и работает** | Уже на prod, используем как есть или как reference | Second Brain, AVA Voice, delno-site stack |
| **B. Переносим** | Код/логика с prod → в git → адаптируем под multi-tenant | `brain_platform`, паттерны text-bot, voice |
| **C. Строим новое** | DELNO-специфика, которой нет | Auth, channel router, billing, CMS, delno-web/admin |

**Правило:** не писать KB и ACL с нуля — **переносим Second Brain (B)**. Не coupling с Quantum Office runtime — **изолированный stack `/opt/delno` (C)**.

---

## 3. Что есть СЕЙЧАС (inventory prod)

### 3.1. DELNO stack (изолированный, уже на prod)

| Компонент | Путь / URL | Состояние |
|-----------|------------|-----------|
| delno-site | `/opt/delno/site`, `:18019`, `/delno/` | ✅ лендинг v23 |
| delno-api | `/opt/delno/api`, `:18020`, `/delno-api/` | ✅ scaffold (PG, leads, operator stub) |
| delno-postgres | Docker `delno-internal` | ✅ отдельная БД |
| systemd | `delno-stack.service` | ✅ |
| secrets | `/opt/delno/.env` | ✅ только DELNO |

**Ограничения:** нет auth, нет multi-tenant channels, leads локально в site, KB demo — статика.

### 3.2. Second Brain — наша KB (Quantum Office, prod)

| Параметр | Значение |
|----------|----------|
| Сервис | `ava-knowledge.service` → `127.0.0.1:8017` |
| Код | `/opt/ava-knowledge/brain_platform/` (~62 файла, ~9656 строк) |
| **Не в git** | prod опережает репозиторий |
| Данные | SQLite 324 MB: 1530 docs, 8493 chunks (все embedded), 728 emails, 418 threads, 136 contacts |
| Поиск | Hybrid: FTS5 + vector (`text-embedding-3-small`) + RRF |
| Ingest | FAQ, vault, files, IMAP — timer ~15 мин |
| Tenant сейчас | один: `quantum-labs` |

**API:** `/api/brain/*` (новый) + `/api/knowledge/*` (legacy для AVA Voice).

**Потребители:** ava-text-bot, ava-mailer, AVA Voice (legacy).

### 3.3. Quantum Office (reference, single-tenant)

| Сервис | Порт | Переносим? |
|--------|------|------------|
| AVA Voice (Asterisk+Mango+Realtime) | — | **B** паттерны → `delno-voice` |
| ava-text-bot | 8011 | **B** agent loop, principals → delno-api operator |
| ava-knowledge (Second Brain) | 8017 | **B** → `delno-knowledge` |
| ava-mailer | 8000 | reference (post-call) |
| ava-calendar / conference | 8014/8016 | reference |
| ava-outreach | 8012 | не трогаем |

**Не ломать на prod:** `/opt/polyhub`, `/root/ava`, Asterisk, Mango, VPN.

---

## 4. Целевая архитектура

```
                         ┌─────────────────────────────────────────┐
                         │              delno-api                   │
                         │  Auth │ Tenants │ Channels │ Operator   │
                         │  CMS  │ Billing hooks │ Channel Router   │
                         └───────────┬─────────────┬─────────────────┘
                                     │             │
              ┌──────────────────────┼─────────────┼──────────────────┐
              │                      │             │                  │
        delno-web              delno-admin    delno-site         delno-voice
     (кабинет клиента)         (admin+CMS)   (marketing)      (Realtime worker)
              │                      │             │                  │
              └──────────────────────┴─────────────┴──────────────────┘
                                     │
                         ┌───────────▼───────────┐
                         │    delno-knowledge     │  ← fork brain_platform
                         │  /api/brain/* + ACL    │
                         │  per-tenant vault+ingest │
                         └───────────────────────┘
```

**Prod layout (staging):**

```
/opt/delno/
├── .env
├── docker-compose.yml      # site + api + postgres + knowledge (phase 1)
├── site/
├── api/
├── knowledge/              # delno-knowledge (phase 1)
└── data/
    ├── pg/
    └── brain/              # per-tenant brain DB / vault
```

---

## 5. Second Brain → delno-knowledge (перенос, не переписывание)

### 5.1. Что переносим as-is (B)

Из `/opt/ava-knowledge/brain_platform/`:

- `security/acl.py` — principals, visibility, default deny
- `security/zones.py` — public/private/secret index zones
- `search/` — hybrid engine (FTS + vector + RRF)
- `ingest/` — vault, mail, files, FAQ
- `db/` — schema (SQLite v1 → Postgres/pgvector v2)
- `schemas/models.py` — DocumentFrontmatter, ACL, Classification
- `api/router.py` — `/api/brain/*`
- `mcp/` — опционально для Cursor/admin tools
- Tests — `test_security_contracts.py`, hybrid tests

### 5.2. Что адаптируем (B → C)

| Было (Quantum Office) | Станет (DELNO) |
|-----------------------|----------------|
| `BRAIN_TENANT_ID=quantum-labs` | tenant_id из delno-api JWT / channel router |
| Hardcoded SERVICE_PRINCIPALS | + principals per DELNO channel (см. §6) |
| Один vault `quantum-brain` | vault per tenant: `vault/{tenant_slug}/` |
| Ingest IMAP office@ | Ingest per tenant (optional, phase 5+) |
| `channels: [office-assistant]` | + auto-ingest **настроек кабинета** |
| Single SQLite | SQLite per tenant (v1) → Postgres pgvector (v2) |

### 5.3. Уровни базы знаний (уже реализованы — используем)

Каждый документ имеет **visibility** + **channels** + **ACL**:

| Visibility | Кто видит (типично) |
|------------|---------------------|
| `public` | Внешние клиенты — **только после publish** |
| `company` | Внутренние документы tenant |
| `team:sales`, `team:ops` | Команды / outreach |
| `restricted` | Explicit ACL (mail, CRM, PII) |
| `secret` | Admin + explicit ACL |

| Канал (tag) | Назначение |
|-------------|------------|
| `office-assistant` | Настройки кабинета, runbooks — **видит голосовой помощник владельца, не видят гости** |

**Index zones:** mail/contacts/PII **никогда** не попадают в public zone.

**ACL in-query:** фильтр в SQL до vector search, не post-filter. Audit log на каждый search.

### 5.4. Principals — mapping для DELNO

delno-api **никогда** не доверяет tenant_id из body клиента. Router определяет tenant + principal:

| Сценарий | Principal | Видит |
|----------|-----------|-------|
| Входящий звонок (внешний) | `service:delno-voice-public` | `public` (published FAQ) |
| Голосовой помощник в кабинете / owner | `service:delno-voice-office` | `public` + `channels: office-assistant` |
| Widget / site chat (anon) | `service:delno-widget-guest` | `public` + assistant_safe |
| Telegram guest (не owner) | `service:delno-text-guest` | `public` + assistant_safe |
| Owner / tenant_admin в cabinet | `service:delno-text-owner` | **вся KB tenant** |
| Outreach bot | `service:delno-outreach` | `public` + `team:sales` |
| Platform admin (Cursor/support) | `service:delno-admin` + `X-Admin` | full tenant (audit) |

Legacy names (`service:voice-public`, `service:text-owner`, …) сохраняем как aliases на переходный период.

### 5.5. Auto-ingest настроек кабинета

При изменении в delno-web (часы работы, скрипты, FAQ, тарифы):

```
delno-api (tenant settings save)
  → POST delno-knowledge /api/brain/ingest/tenant-settings
  → document: visibility=company, channels=[office-assistant]
  → voice-office видит, voice-public — нет
```

Публичный FAQ клиента:

```
delno-web KB → visibility=public → publish flow → voice-public + widget видят
```

---

## 6. Карта переноса (A → B → C)

| Источник (prod) | Цель (git/deploy) | Действие | Фаза |
|-----------------|-------------------|----------|------|
| `/opt/ava-knowledge/brain_platform/` | `delno-knowledge/` | rsync → git, multi-tenant | **0** |
| `delno-api/` scaffold | `delno-api/` | auth, channels, router | **0–1** |
| `DELNO-site-v23/` | `delno-site/` | CMS fetch, leads → api | **1** |
| ava-text-bot agent loop | `delno-api/operator/` | LLM + tools + principals | **2** |
| AVA Realtime patterns | `delno-voice/` | per-tenant session config | **4** |
| ava-text-bot webhooks | `delno-api/webhooks/` | token → tenant router | **3** |
| — | `delno-web/` | cabinet UI | **2** |
| — | `delno-admin/` | admin + CMS UI | **1** |

**Не переносим как runtime dependency:** shared `.env`, импорт Python из `/opt/ava-*`.

---

## 7. Репозитории

| Repo | Содержимое | Статус |
|------|------------|--------|
| `quantum-office` | monorepo staging: delno-api, docs, site export | текущий |
| `delno-knowledge` | brain_platform fork | **создать в фазе 0** (можно папка в monorepo сначала) |
| `delno-web` | cabinet frontend | фаза 2 |
| `delno-admin` | admin + CMS frontend | фаза 1 |
| `delno-site` | marketing (уже есть export) | фаза 1 |
| `delno-voice` | voice worker | фаза 4 |

**Решение v1:** всё в `quantum-office` как пакеты (`delno-api/`, `delno-knowledge/`, …), split repos когда команда вырастет.

---

## 8. Модель данных delno-api (commercial v1)

### Core (уже есть / добавить)

```
tenants, users, audit_logs          ✅ частично
leads, conversations, messages      ✅ частично
channel_accounts                    ⬜ фаза 0
phone_numbers                       ⬜ фаза 0
tenant_voice_profiles               ⬜ фаза 0
tenant_settings (→ brain ingest)    ⬜ фаза 1
cms_pages, cms_revisions            ⬜ фаза 1
subscriptions, usage_records        ⬜ фаза 6
```

**Правило:** LLM tools **никогда** не принимают `tenant_id` из prompt — только backend context.

KB documents/chunks живут в **delno-knowledge**, не дублируем в delno-api PG (кроме metadata/sync pointers).

---

## 9. Channel Router (критический компонент)

| Вход | Lookup | Principal |
|------|--------|-----------|
| Inbound call `+7…` | `phone_numbers.e164` → tenant | voice-public или voice-office |
| Telegram webhook | bot token → channel_account | text-guest / text-owner |
| MAX webhook | token → channel_account | text-guest / text-owner |
| Web widget | `tenant_public_key` | widget-guest |
| Cabinet operator | JWT session | text-owner |
| Internal voice worker | service token | voice-office |

После lookup: brain search с правильным principal + voice_profile + tools.

---

## 10. Roadmap — фазы реализации

### PHASE 0 — Foundation + Brain port ⬅️ **СТАРТ ЗДЕСЬ**

**Цель:** единый фундамент, KB не с нуля.

| # | Задача | Тип |
|---|--------|-----|
| 0.1 | Extract `brain_platform` с prod → `delno-knowledge/` в git | B |
| 0.2 | Docker: delno-knowledge в `/opt/delno` stack (:18021) | C |
| 0.3 | delno-api: Auth JWT + roles (platform_admin, tenant_owner, …) | C |
| 0.4 | Migrations: channel_accounts, phone_numbers, tenant_voice_profiles | C |
| 0.5 | KnowledgeAdapter → `/api/brain/search` + principal header | C |
| 0.6 | Channel router skeleton + tenant seed CLI | C |
| 0.7 | Tests: cross-tenant isolation + ACL smoke | C |

**Exit criteria:**
- [ ] `brain_platform` в git, тесты проходят локально
- [ ] delno-api ищет KB с principal, guest не видит `office-assistant`
- [ ] Admin создаёт tenant через API
- [ ] Stack на prod: site + api + postgres + knowledge

---

### PHASE 1 — Admin + CMS

| # | Задача |
|---|--------|
| 1.1 | `/admin/v1/tenants` CRUD + audit |
| 1.2 | `/admin/v1/cms/pages` draft/publish |
| 1.3 | delno-admin: login, tenants, CMS editor |
| 1.4 | delno-site: FAQ/pricing из CMS API |
| 1.5 | Leads: site → delno-api (не local) |

**Exit:** marketing site редактируется из admin; leads в PG.

---

### PHASE 2 — Tenant cabinet + Operator

| # | Задача |
|---|--------|
| 2.1 | delno-web: login, dashboard, inbox (read) |
| 2.2 | KB UI: upload, FAQ edit, publish public/private |
| 2.3 | Auto-ingest tenant settings → brain (`office-assistant`) |
| 2.4 | Operator LLM loop (OpenAI) + tools: get_knowledge, update_settings, create_lead |
| 2.5 | Critical writes → confirm card |

**Exit:** клиент логинится, настраивает KB с уровнями, Operator знает настройки кабинета.

---

### PHASE 3 — Messengers (per tenant)

| # | Задача |
|---|--------|
| 3.1 | Telegram connect wizard + webhook |
| 3.2 | MAX connect wizard + webhook |
| 3.3 | Router: token → tenant; guest vs owner principals |
| 3.4 | Inbound → conversation + KB reply |

**Exit:** клиент подключает **свой** Telegram bot.

---

### PHASE 4 — Telephony + Voice (critical path)

| # | Задача |
|---|--------|
| 4.1 | phone_numbers provisioning (Mango/SIP) |
| 4.2 | delno-voice worker: Realtime per call |
| 4.3 | Internal API: session config (tenant, voice, principal) |
| 4.4 | Post-call → transcript in inbox |
| 4.5 | Voice preset / clone UI |

**Exit:** свой номер → свой голос → public FAQ наружу, office-assistant внутри.

---

### PHASE 5 — Website widget

| # | Задача |
|---|--------|
| 5.1 | Embeddable JS `data-tenant-key` |
| 5.2 | Chat + optional voice (STT/TTS → Realtime) |
| 5.3 | Principal: widget-guest |

---

### PHASE 6 — Billing + hardening

Plans, usage meters, payments, rate limits, RLS optional, penetration tests on ACL.

---

### PHASE 7 — Scale

Dedicated server, horizontal voice workers, Redis queues, retire AVA coupling.

---

## 11. Sprint 1 — конкретные задачи (начинаем сейчас)

Первый спринт = **Phase 0.1–0.7**:

```
Неделя A (backend):
  1. scp/rsync brain_platform → delno-knowledge/ + Dockerfile + compose
  2. delno-api: JWT auth, User.roles, login/register
  3. Alembic: channel_accounts, phone_numbers, tenant_voice_profiles
  4. KnowledgeAdapter: /api/brain/search + X-Principal-Id mapping helper
  5. POST /v1/admin/tenants, GET /v1/admin/tenants

Неделя B (integration):
  6. Deploy knowledge container to /opt/delno on prod
  7. Seed tenant "demo" + vault sample + ACL test script
  8. Wire operator get_knowledge tool → brain with principal
  9. Document principals in delno-api/AGENTS.md
 10. CI: pytest delno-api + delno-knowledge security tests
```

**Не делаем в Sprint 1:** telephony, voice clone, billing, delno-web/admin UI (это Phase 1–2).

---

## 12. Критерии «коммерческий продукт работает»

- [ ] Self-service регистрация tenant
- [ ] **Свой** номер → звонки с **своим** голосом и KB (public наружу)
- [ ] **Свой** Telegram / widget
- [ ] Inbox unified
- [ ] Operator (текст + голос) знает настройки кабинета, гости — нет
- [ ] Admin редактирует marketing site без git deploy
- [ ] Tenant A не видит данные tenant B (automated tests)
- [ ] Quantum Office prod не сломан

---

## 13. Tech stack

| Layer | Choice |
|-------|--------|
| API | FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16 |
| Knowledge | brain_platform (SQLite v1 → pgvector v2) |
| Auth | JWT + refresh, bcrypt |
| Client/Admin UI | Next.js, Tailwind, shadcn |
| Voice | OpenAI Realtime (delno-voice worker) |
| Deploy | Docker compose в `/opt/delno`, systemd `delno-stack` |

---

## 14. Риски (осознанные)

| Риск | Митигация |
|------|-----------|
| brain_platform не в git | Phase 0.1 — extract первым делом |
| ACL regression при multi-tenant | Port security tests, deny_by_default |
| Mango multi-tenant сложность | Phase 4; MVP = клиент приносит свой Mango |
| Scope creep (CMS, billing) | Strict phase gates, Sprint 1 = foundation only |

---

## 15. Связанные документы

| Документ | Назначение |
|----------|------------|
| `docs/DELNO_MASTER_PLAN.md` | **этот файл — canonical** |
| `delno-api/docs/DEPLOY_ISOLATION.md` | prod deploy `/opt/delno` |
| `DELNO-site-v23/docs/00_MASTER_SPEC.md` | product vision |
| `delno-api/AGENTS.md` | onboarding для API |
| `/opt/ava-knowledge/brain_platform/README.md` | brain runtime (prod) |

---

## 16. Резюме для команды

1. **Second Brain — наш фундамент KB**, не пишем с нуля.
2. **Уровни доступа уже есть** — principals + visibility + `office-assistant` channel.
3. **DELNO stack изолирован** — `/opt/delno`, не shared `.env` с AVA.
4. **Начинаем с Phase 0:** brain в git → knowledge container → auth → adapter → ACL tests.
5. **Три UI + один API** — admin (CMS), web (cabinet), site (marketing).

**Следующий commit:** `delno-knowledge/` extract + Phase 0 scaffold.
