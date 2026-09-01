# DELNO — детальный план разработки (для ревью)

Версия: 2026-09-01  
Аудитория: product + engineering review (ChatGPT / команда)  
Статус: draft для корректировки

---

## 0. Контекст и цель

**DELNO** — коммерческий multi-tenant SaaS: «один ИИ-сотрудник» для бизнеса (телефон, сайт, мессенджеры, почта). Не чат-бот платформа.

**Неп negotiable (с day 1 коммерческого продукта):**
- У каждого клиента (tenant) **свой** номер телефонии
- **Свои** мессенджеры (Telegram, MAX — branded bots, token клиента)
- **Свой** сайт / widget на своём домене
- **Своя** база знаний
- **Свой** голос (preset или clone)
- Полная **изоляция данных** между tenant (tenant_id, audit, no cross-leak)

**Reference (не runtime dependency):** Quantum Office / AVA на сервере `5.35.86.62` — паттерны телефонии, Realtime, calendar. Не импортировать Python-модули, не shared `.env`.

---

## 1. Что есть СЕЙЧАС

### 1.1. Маркетинговый сайт (delno-site)

| Параметр | Значение |
|----------|----------|
| Код | `DELNO-site-v23/` (export v23, Next.js 16, React 19) |
| Prod URL | https://a.47z.ru/delno/ |
| Deploy | `/opt/delno/site` в изолированном stack |
| Порт | `127.0.0.1:18019` |
| Функции | Лендинг v2/v4, lead form, TTS voice demo (не Realtime), privacy/terms |
| Ограничения | Lead API локальный в site; KB demo — статика/TTS; **нет** admin CMS; **нет** multi-tenant |

### 1.2. Platform API (delno-api) — scaffold

| Параметр | Значение |
|----------|----------|
| Код | `delno-api/` (FastAPI, PostgreSQL) |
| Prod URL | https://a.47z.ru/delno-api/v1/health |
| Deploy | `/opt/delno/api`, Docker, порт `18020` |
| DB | PostgreSQL `delno-postgres`, volume `delno-pg-data`, сеть `delno-internal` |
| Модели | tenants, users, leads, conversations, messages, audit_logs |
| API | `/v1/leads`, `/v1/operator/chat`, `/v1/operator/conversations`, confirm stub |
| Tools | `get_knowledge`, `create_lead` (registry готов для расширения) |
| Adapters | KNOWLEDGE_BASE_URL, MESSENGER_BASE_URL — **пустые** (изоляция от ava-*) |
| Ограничения | Нет auth/JWT; нет channel_accounts; нет telephony; operator — keyword MVP, не LLM loop |

### 1.3. Изолированный stack на prod

```
/opt/delno/
├── .env              # только DELNO secrets
├── docker-compose.yml
├── site/             # delno-site
├── api/              # delno-api
└── data/

systemd: delno-stack.service
nginx: /delno/, /delno-api/ → 18019, 18020
```

Не зависит от: `/opt/ava-*`, `/opt/polyhub`, `/root/ava` (adapters выключены).

### 1.4. Quantum Office / AVA (reference на prod)

| Сервис | Порт | Что умеет | Multi-tenant |
|--------|------|-----------|--------------|
| AVA Voice | Asterisk+Mango+Realtime | Inbound calls, in-call tools, post-call | ❌ single |
| ava-text-bot | 8011 | Telegram, MAX webhook, /api/chat | ❌ single |
| ava-knowledge | 8017 | Brain KB search/ingest | ❌ single |
| ava-calendar | 8014 | CalDAV booking | ❌ single |
| ava-conference | 8016 | Telemost | ❌ single |
| ava-outreach | 8012 | Bitrix CRM | ❌ single |

**Prod новее git** — MAX, secretary, brain уже на сервере; в репозитории `quantum-office` этого мало.

### 1.5. Документация и vision

- `DELNO_Cursor_Knowledge_Base/docs/00_MASTER_SPEC.md` — product/architecture vision
- `delno-api/docs/DEPLOY_ISOLATION.md` — изоляция и миграция
- `DELNO-site-v23/docs/02_PROTOTYPE_ARCHITECTURE.md`, `03_LAUNCH_STRATEGY.md`
- Git PR: `cursor/delno-api-scaffold-14e9` (#20)

### 1.6. Чего НЕТ (gap)

- Личный кабинет клиента (frontend + backend)
- Админ-панель DELNO (frontend + backend) — управление сайтом, tenant, billing
- Multi-tenant telephony (свой номер per tenant)
- Per-tenant voice (preset/clone)
- Per-tenant messengers (branded bots)
- Per-tenant KB (upload, ingest, vector search)
- Auth / RBAC (platform_admin, tenant_owner, …)
- Self-service onboarding
- Billing / usage meters
- Site CMS из admin (редактирование лендинга без деплоя кода)

---

## 2. Целевая архитектура (репозитории и приложения)

### 2.1. Репозитории (целевое разделение)

| Repo | Назначение |
|------|------------|
| `delno-api` | Backend: tenant core, auth, channels, voice routing, KB API, operator tools, billing hooks |
| `delno-web` | **Frontend клиента** — личный кабинет (React/Next) |
| `delno-admin` | **Frontend администратора** — platform admin + CMS сайта |
| `delno-site` | Public marketing site (рендер из CMS или static + API) |
| `delno-voice` | Voice runtime (Asterisk/Realtime worker) — позже отдельный lifecycle |
| `delno-channels` | Webhook workers Telegram/MAX — опционально позже |
| `quantum-office` | Reference only |

На первом этапе допустимо: `delno-api` + `delno-web` + `delno-admin` + `delno-site` (4 repo или monorepo с packages — решение на ревью).

### 2.2. Три типа UI + один platform backend

```
┌─────────────────────────────────────────────────────────────┐
│                     delno-api (Platform API)                 │
│  Auth │ Tenants │ Channels │ Voice │ KB │ Operator │ CMS   │
└─────────────────────────────────────────────────────────────┘
         ▲              ▲                    ▲
         │              │                    │
   delno-web      delno-admin           delno-site
 (кабинет клиента) (админ DELNO)      (public marketing)
 app.delno.ru      admin.delno.ru       dlno.ru
```

**Backend один** (`delno-api`) с RBAC:
- **Tenant API** — для `delno-web` (tenant_owner, manager, …)
- **Admin API** — для `delno-admin` (platform_admin, support)
- **Public API** — для widget, webhooks, anon health

**Не делать** два отдельных backend для admin и client — один API, разные scopes/roles.

### 2.3. Admin управляет сайтом

Маркетинговый сайт должен редактироваться из **delno-admin**:
- Страницы, блоки, тарифы, FAQ, SEO
- Версии/черновик/publish
- API: `delno-api` модуль `cms` → `delno-site` читает published content (SSR/ISR или API-driven)

Сейчас site — hardcoded React; целевое — **headless CMS** в platform API + admin UI.

---

## 3. Модель данных (commercial v1)

### 3.1. Core

```
tenants (id, slug, name, plan, status, settings_json)
users (id, tenant_id, email, role, password_hash / oauth)
roles / permissions (RBAC)
audit_logs (tenant_id, actor, action, old/new, timestamp)
```

### 3.2. Channels (всё per tenant)

```
channel_accounts (
  id, tenant_id, type,  -- mango|sip|telegram|max|email|web_widget
  credentials_encrypted,
  status, verified_at, meta_json
)

phone_numbers (
  id, tenant_id, channel_account_id,
  e164, label, status,  -- active|pending|failed
  routing_config_json
)
```

### 3.3. Voice

```
tenant_voice_profiles (
  tenant_id,
  mode,           -- preset | cloned
  provider,       -- openai | elevenlabs | ...
  preset_id,
  clone_id,
  language,
  sample_status,
  consent_recorded_at
)
```

### 3.4. Knowledge

```
knowledge_documents (tenant_id, title, source, content, embedding vector?)
knowledge_chunks (tenant_id, document_id, text, metadata)
```

### 3.5. Conversations

```
contacts (tenant_id, phone, email, name, ...)
conversations (tenant_id, channel, contact_id, status)
messages (tenant_id, conversation_id, role, body, meta)
calls (tenant_id, phone_number_id, duration, transcript, recording_url?)
leads (tenant_id, source, ...)
```

### 3.6. CMS (site from admin)

```
cms_pages (slug, locale, title, blocks_json, status draft|published)
cms_assets (images, files)
cms_revisions (history)
```

### 3.7. Billing (hook-ready)

```
subscriptions (tenant_id, plan, status)
usage_records (tenant_id, metric, quantity, period)
```

**Правило:** LLM tools **никогда** не принимают `tenant_id` — только backend из JWT/session/webhook lookup.

---

## 4. Channel Router (критический компонент)

Единая точка входа для всех каналов:

| Вход | Lookup |
|------|--------|
| Inbound call to `+7…` | `phone_numbers.e164` → tenant_id |
| Telegram webhook | bot token → channel_account → tenant_id |
| MAX webhook | token → tenant_id |
| Web widget | `tenant_public_key` → tenant_id |
| Email (later) | inbox address → tenant_id |

После lookup: load tenant KB, voice_profile, prompt, tools, calendar credentials.

---

## 5. Frontend: личный кабинет клиента (delno-web)

**URL:** `app.dlno.ru` (или `/app`)

**Роли:** tenant_owner, tenant_admin, manager, operator, viewer

### 5.1. Разделы MVP

1. **Dashboard** — статус каналов, пропущенные, usage
2. **Inbox** — conversations (phone, tg, web) unified timeline
3. **Contacts / Leads**
4. **Knowledge** — upload, URL import, preview, test query
5. **Channels** — wizard подключения:
   - Телефон (Mango OAuth / SIP credentials)
   - Telegram (token)
   - MAX (token)
   - Website widget (embed code)
6. **Voice** — выбор preset / upload clone samples / preview
7. **Operator** — chat + voice UI для настройки («Подключи Telegram», «Измени часы работы»)
8. **Settings** — company profile, hours, users, billing

### 5.2. Operator UX (текст + голос)

- Один chat thread → backend `POST /v1/operator/chat`
- Голос: STT → тот же endpoint → TTS (Phase 1) → Realtime (Phase 2)
- Critical writes → confirmation card in UI

### 5.3. Tech

- Next.js или React + Vite
- Auth: JWT / session cookie from delno-api
- Real-time inbox: WebSocket или SSE

---

## 6. Frontend: админ-панель (delno-admin)

**URL:** `admin.dlno.ru`

**Роли:** platform_admin, support (read-only option)

### 6.1. Разделы

1. **Tenants** — list, create, suspend, impersonate (support)
2. **Tenant detail** — channels, usage, logs, billing
3. **Platform health** — voice workers, queue depth, errors
4. **CMS** — **редактирование marketing site:**
   - Pages (home, pricing, FAQ, legal)
   - Blocks (hero, features, tariffs)
   - Publish to production site
5. **Voice catalog** — manage preset voices
6. **Plans & pricing** — SKU, limits
7. **Audit** — platform-wide security log
8. **Supervisor** (later) — incidents, auto-fix status

### 6.2. Site CMS flow

```
Admin edits page in delno-admin
  → POST /admin/v1/cms/pages/{id}
  → draft in PostgreSQL
  → Publish
  → delno-site revalidate / fetch published API
  → dlno.ru updated without git deploy
```

---

## 7. Backend: delno-api (детализация модулей)

### 7.1. API namespaces

| Prefix | Consumer | Примеры |
|--------|----------|---------|
| `/v1/public/` | site, widget | health, lead capture anon |
| `/v1/tenant/` | delno-web | inbox, KB, channels, operator |
| `/v1/admin/` | delno-admin | tenants, cms, platform |
| `/v1/webhooks/` | Telegram, MAX, Mango, voice | unsigned + signature verify |
| `/v1/internal/` | delno-voice worker | call session, tool proxy |

### 7.2. Модули

1. **auth** — register, login, refresh, RBAC middleware
2. **tenants** — CRUD, settings
3. **channels** — connect, verify, disconnect, encrypt secrets
4. **telephony** — phone_numbers, Mango/SIP provisioning API
5. **voice** — voice_profiles, preset catalog, clone jobs
6. **knowledge** — ingest, search (pgvector), tenant-scoped
7. **conversations** — unified inbox API
8. **operator** — LLM loop + tool registry + confirm + audit
9. **cms** — pages, publish, assets
10. **billing** — stubs → Stripe/ЮKassa later
11. **adapters** — optional HTTP to legacy ava during migration

### 7.3. Voice runtime integration

- `delno-voice` worker registers with API
- On inbound call: voice asks API `GET /internal/v1/calls/session?to=+7...`
- API returns: tenant_id, voice_id, system_prompt, tool_endpoint
- Post-call: `POST /internal/v1/calls/{id}/complete` → transcript → inbox

AVA patterns reused; config **never** global yaml for all tenants.

---

## 8. AVA: роль при commercial launch

| Использовать | Не использовать |
|--------------|-----------------|
| OpenAI Realtime integration patterns | Single-tenant ai-agent.local.yaml |
| Mango/SIP dialplan ideas | Shared Mango trunk for all clients |
| Post-call extraction logic | mailer → single Bitrix |
| Calendar/Telemost flow as reference | ava `.env` secrets |

**Path:** Week 1–8 build tenant routing in delno-api; voice worker reads per-tenant config; gradually replace AVA docker with `delno-voice` on same or new server.

---

## 9. Детальный roadmap

### PHASE 0 — Foundation (недели 1–2) ✅ частично done

- [x] delno-site on prod (isolated stack)
- [x] delno-api scaffold (PG, tenant seed, tools, audit)
- [ ] Auth (JWT, register/login, roles)
- [ ] `channel_accounts`, `phone_numbers`, `tenant_voice_profiles` migrations
- [ ] Channel router skeleton
- [ ] Repo split decision: monorepo vs multi-repo

**Exit:** API создаёт tenant, admin может создать tenant вручную через API/seed.

---

### PHASE 1 — Admin backend + CMS API (недели 3–5)

**Backend:**
- [ ] `/admin/v1/tenants` CRUD
- [ ] `/admin/v1/cms/pages` draft/publish
- [ ] `/admin/v1/users` platform admins
- [ ] Audit on all admin writes

**Frontend delno-admin (MVP):**
- [ ] Login
- [ ] Tenant list + detail
- [ ] CMS editor (hero, pricing, FAQ — JSON blocks minimum)
- [ ] Publish triggers site update

**Frontend delno-site:**
- [ ] Fetch published CMS from API (replace hardcoded v2/v4 or hybrid)

**Exit:** Marketing site редактируется из admin без git push.

---

### PHASE 2 — Tenant cabinet backend (недели 5–7)

**Backend:**
- [ ] `/tenant/v1/*` scoped by JWT tenant_id
- [ ] Knowledge upload + search (pgvector or keyword MVP)
- [ ] Leads/inbox read APIs
- [ ] Operator LLM loop (OpenAI + tools)

**Frontend delno-web (MVP):**
- [ ] Login/register/onboarding shell
- [ ] Dashboard + Inbox (read-only first)
- [ ] KB upload UI
- [ ] Operator text chat

**Exit:** Клиент логинится, видит inbox, загружает KB, говорит с Operator текстом.

---

### PHASE 3 — Channels: messengers (недели 7–9)

**Backend:**
- [ ] Telegram connect: validate token, set webhook `https://api.dlno.ru/v1/webhooks/telegram/{account_id}`
- [ ] MAX connect: same pattern
- [ ] Router: token → tenant
- [ ] Inbound message → conversation + operator/KB reply

**Frontend:**
- [ ] Channel wizards in delno-web
- [ ] Test message button

**Exit:** Клиент подключает **свой** Telegram bot, сообщения в inbox.

---

### PHASE 4 — Telephony per tenant (недели 9–14) ⚠️ critical path

**Backend:**
- [ ] Mango API integration OR SIP credential storage per tenant
- [ ] `phone_numbers` provisioning workflow: pending → verify → active
- [ ] Inbound routing: DID → tenant
- [ ] Internal API for voice worker (session config)
- [ ] Post-call webhook → call record + transcript in inbox

**Voice worker (delno-voice v1):**
- [ ] Realtime session with dynamic voice_id + prompt per call
- [ ] In-call tools proxy to delno-api (calendar, KB) with tenant context

**Frontend:**
- [ ] Telephony wizard (connect Mango / enter SIP)
- [ ] Phone number status UI
- [ ] Voice preset picker + clone upload UI
- [ ] Test call button

**Exit:** Клиент подключает **свой номер**, звонит — отвечает **его** голос + **его** KB.

---

### PHASE 5 — Website widget (недели 12–14)

- [ ] Embeddable JS snippet `data-tenant-key`
- [ ] Web chat + optional voice (STT/TTS)
- [ ] Same operator/KB as phone

**Exit:** Widget на сайте клиента, conversations в inbox.

---

### PHASE 6 — Billing & commercial hardening (недели 14–18)

- [ ] Plans: Диалоги 2990 / Звонки 5990
- [ ] Usage meters (minutes, dialogs)
- [ ] Payment integration
- [ ] Rate limits per tenant
- [ ] PostgreSQL RLS optional
- [ ] Cross-tenant isolation tests

---

### PHASE 7 — Scale & migration (недели 18+)

- [ ] Move `/opt/delno` to dedicated server
- [ ] delno-voice horizontal workers
- [ ] Redis queues
- [ ] delno-channels separate service if needed
- [ ] Retire AVA dependency completely

---

## 10. Инфраструктура и домены (target)

| Домен | App |
|-------|-----|
| dlno.ru | delno-site (public) |
| app.dlno.ru | delno-web |
| admin.dlno.ru | delno-admin |
| api.dlno.ru | delno-api |

Prod сейчас: `a.47z.ru/delno`, `a.47z.ru/delno-api` (staging).

---

## 11. Tech stack (рекомендация для ревью)

| Layer | Choice |
|-------|--------|
| API | FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16, pgvector |
| Auth | JWT + refresh, bcrypt, optional OAuth |
| Queue | Redis + Celery/ARQ (phase 4+) |
| Client UI | Next.js 15+ App Router, Tailwind, shadcn |
| Admin UI | Same stack as client (shared component lib) |
| Voice | OpenAI Realtime, later multi-provider |
| Secrets | env + encrypted columns, later Vault |
| Deploy | Docker compose → k8s only when needed |

---

## 12. Риски и вопросы для ревью (ChatGPT)

1. Monorepo (`delno/` packages) vs 4 separate repos — что быстрее для 2–3 dev?
2. CMS: custom blocks vs headless (Payload, Strapi) — build vs buy?
3. Mango multi-tenant: one DELNO Mango partner account vs each client brings own — legal/billing?
4. Voice clone provider: OpenAI only vs ElevenLabs — quality/latency/cost?
5. Voice worker: fork AVA docker vs greenfield — timeline tradeoff?
6. Realtime on website: Phase 1 STT/TTS vs immediate WebRTC?
7. PostgreSQL RLS from day 1 or tenant_id discipline first?
8. dlno.ru DNS migration timing vs continue a.47z.ru staging?

---

## 13. Следующий конкретный шаг (immediate)

**Sprint 1 (1–2 недели):**

1. **delno-api:**
   - Auth (register/login/JWT)
   - Migrations: channel_accounts, phone_numbers, tenant_voice_profiles
   - Admin endpoints: create tenant, list tenants
   - CMS models + admin CRUD (pages draft)

2. **delno-admin (new repo):**
   - Scaffold Next.js
   - Login against delno-api
   - Tenant list page
   - CMS page editor (minimal)

3. **delno-web (new repo):**
   - Scaffold Next.js
   - Login/register
   - Empty dashboard shell

4. **delno-site:**
   - One CMS-driven section (e.g. FAQ) as proof

5. **Не делать в Sprint 1:** telephony provisioning, voice clone, billing.

---

## 14. Критерии «коммерческий продукт работает»

- [ ] Новый клиент регистрируется self-service
- [ ] Подключает **свой** номер → принимает звонки с **своим** голосом и KB
- [ ] Подключает **свой** Telegram
- [ ] Вставляет widget на **свой** сайт
- [ ] Видит все обращения в inbox
- [ ] Настраивает через Operator (текст, потом голос)
- [ ] Admin редактирует marketing site без deploy
- [ ] Данные tenant A недоступны tenant B (tests)

---

## 15. Резюме для ChatGPT

**Сейчас:** isolated marketing site + API scaffold, без cabinet, без multi-tenant channels, без telephony productization.

**Делаем:** commercial multi-tenant platform with three frontends (site, client app, admin) and one backend (delno-api), per-tenant phone/messengers/KB/voice from day one of commercial launch.

**AVA:** reference for voice engineering only; tenant data and routing live in delno-api.

**Приоритет critical path:** channel_accounts + phone routing + voice worker per-tenant config → then messengers → widget → billing.

**Admin must control marketing site via CMS API.**

Просьба к ревьюеру: проверить последовательность фаз, оценить сроки, указать architectural risks и предложить корректировки.
