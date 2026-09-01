# DELNO — план реализации (детальный checklist)

**Canonical strategy:** [`DELNO_MASTER_PLAN.md`](DELNO_MASTER_PLAN.md)  
**Домены:** [`DLNO_DOMAINS.md`](DLNO_DOMAINS.md)  
**Обновлено:** 2026-09-01 · **Revision REV-3.1** (Sprint 3 executable plan)

Легенда: ✅ done · 🔄 in progress · ⬜ todo

---

## Текущий статус (кратко для ревью)

| Компонент | URL / путь | Статус |
|-----------|------------|--------|
| Marketing staging | https://a.47z.ru/delno/ | ✅ |
| Marketing prod | https://dlno.ru (DNS pending) | 🔄 nginx ready |
| API staging | https://a.47z.ru/delno-api/ | ✅ |
| API prod | https://api.dlno.ru (DNS pending) | 🔄 |
| delno-api | `/opt/delno/api` :18020 | ✅ |
| delno-knowledge | `/opt/delno/knowledge` :18021 | ✅ |
| delno-site (staging) | :18019, basePath `/delno` | ✅ |
| delno-site-root (prod) | :18022, root | ✅ |
| delno-admin scaffold | local :3010 | ✅ code |
| delno-web scaffold | local :3020 | ✅ code |

---

## Трек A — Product (параллельно с engineering)

### P1 — Selling Website (`dlno.ru` + staging)

| # | Задача | Статус |
|---|--------|--------|
| P1.1 | Hero: «ИИ-сотрудник» — clarity за 5–10 сек | ✅ v4 hero на `/` (staging) |
| P1.2 | Блок каналов: телефон, сайт, Telegram, MAX, email | ✅ v4 product stage |
| P1.3 | CTA «Попробовать» → voice demo + lead form | ✅ lead form + «Спросить вслух» |
| P1.4 | Leads с сайта → **delno-api** | ✅ route + form + deploy scripts |
| P1.5 | Mobile UX / lighthouse pass | ⬜ |
| P1.6 | `dlno.ru` DNS Cloudflare → `5.35.86.62` | ⬜ **S3 P0 #5** |
| P1.7 | SSL на origin (Cloudflare Full / certbot) | ⬜ **S3 P0 #5** |
| P1.8 | Privacy/terms актуальны для dlno.ru | ⬜ |
| P1.9 | Exit: clarity-test пройден 3+ людьми | ⬜ |

### P2 — First Value

| # | Задача | Статус |
|---|--------|--------|
| P2.1 | Self-service register → tenant | ⬜ |
| P2.2 | Upload KB → first search | ⬜ |
| P2.3 | Widget embed → first message | ⬜ |
| P2.4 | Time to First Value < 15 min | ⬜ |

---

## Трек B — Engineering E0 Foundation

| # | Задача | Статус |
|---|--------|--------|
| E0.1 | `delno-knowledge/` brain_platform в git | ✅ |
| E0.2 | JWT auth + roles | ✅ |
| E0.3 | Models: channels, phones, voice, flags, usage, events | ✅ |
| E0.4 | Admin tenants CRUD | ✅ |
| E0.5 | KnowledgeAdapter → `/api/brain/search` + principals | ✅ |
| E0.6 | Alembic migrations | ✅ scaffold |
| E0.7 | Channel router skeleton | ✅ |
| E0.8 | `/v1/public/*` namespace | ✅ |
| E0.9 | Feature flags read/write API | ✅ |
| E0.10 | Model provider abstraction stub | ✅ |
| E0.11 | Deploy full stack prod: api + knowledge + postgres | ✅ |
| E0.12 | CI: pytest delno-api + brain security tests | ✅ `.github/workflows/delno-tests.yml` |
| E0.13 | Cross-tenant isolation integration test | ✅ |
| E0.14 | **Exit E0:** admin creates tenant; events emit; flags work | 🔄 |
| E0.15 | Minimal operational events (lead.created, auth.failed, …) | ⬜ **S3 P2 #11** |

---

## Трек C — Engineering E1 Knowledge + CMS

| # | Задача | Статус |
|---|--------|--------|
| E1.1 | delno-knowledge container prod `:18021` | ✅ |
| E1.2 | Init brain DB + seed demo vault | ✅ `seed-demo` CLI + docker entrypoint |
| E1.3 | ACL smoke: guest ≠ owner (automated) | ✅ |
| E1.4 | Knowledge provenance in API responses | ⬜ **S3 P1 #9** |
| E1.5 | CMS models: pages, revisions | ✅ |
| E1.6 | Admin CMS CRUD draft/publish | ✅ |
| E1.7 | Site fetch published CMS (FAQ block pilot) | ✅ FaqSection + /api/cms/faq |
| E1.8 | Auto-ingest tenant settings → brain | ⬜ |
| E1.9 | Per-tenant vault path isolation | ⬜ |
| E1.10 | **delno-admin** scaffold: login + tenants + CMS | ✅ |
| E1.11 | **Exit E1:** KB search works; CMS FAQ from admin | ⬜ |

---

## Трек D — Engineering E2 Communication

| # | Задача | Статус |
|---|--------|--------|
| E2.1 | ChannelAdapter interface + registry | ⬜ |
| E2.2 | Telegram Instant bot (DELNO shared) | ⬜ |
| E2.3 | Telegram Branded connect wizard | ⬜ |
| E2.4 | MAX onboarding (client-owned bot) | ⬜ |
| E2.5 | Webhook signing + retry + events | ⬜ |
| E2.6 | Router: token → tenant → principal | ⬜ |
| E2.7 | Inbound message → conversation record | ⬜ |
| E2.8 | Email adapter stub | ⬜ |

---

## Трек E — Engineering E3 Widget + Operator

| # | Задача | Статус |
|---|--------|--------|
| E3.1 | **delno-web** scaffold: login + dashboard shell | ✅ |
| E3.2 | Operator LLM loop — **basic read-only only** | ✅ KB search + model provider |
| E3.3 | Tool registry + confirmation classes | ⬜ |
| E3.4 | Embeddable web widget JS | ⬜ |
| E3.5 | Voice widget WebRTC MVP | ⬜ |
| E3.6 | Fallback voice→text | ⬜ |
| E3.7 | KB UI upload/publish | ⬜ |
| E3.8 | Lead capture from widget → inbox | ⬜ |

---

## Трек F — Engineering E4 Telephony

| # | Задача | Статус |
|---|--------|--------|
| E4.1 | phone_numbers provisioning workflow | ⬜ |
| E4.2 | Mango/SIP credential storage | ⬜ |
| E4.3 | delno-voice worker Realtime | ⬜ |
| E4.4 | Internal call session API | ⬜ |
| E4.5 | Post-call transcript → inbox | ⬜ |
| E4.6 | Voice preset/clone UI | ⬜ |

---

## Трек G — Engineering E5 Commercial

| # | Задача | Статус |
|---|--------|--------|
| E5.1 | Self-service onboarding flow | ⬜ |
| E5.2 | Billing stubs + plans table | ⬜ |
| E5.3 | Usage aggregation per tenant | ⬜ |
| E5.4 | Rate limits per tenant | ⬜ |
| E5.5 | Monitoring + health dashboard | ⬜ |

---

## Трек H — Domains & Deploy

| # | Задача | Статус |
|---|--------|--------|
| H1 | Staging: `a.47z.ru/delno` + `/delno-api` | ✅ |
| H2 | Prod site root: `dlno.ru` nginx + container | ✅ |
| H3 | Cloudflare DNS → server | ⬜ |
| H4 | `api.dlno.ru` live | ⬜ |
| H5 | Unified deploy `/opt/delno` full stack | ✅ |
| H6 | `app.dlno.ru`, `admin.dlno.ru` nginx | ⬜ |

---

## API endpoints (реализовано)

| Method | Path | Назначение |
|--------|------|------------|
| GET | `/v1/health` | health |
| POST | `/v1/auth/login` | JWT login |
| GET | `/v1/auth/me` | current user |
| GET/POST | `/v1/admin/tenants` | platform admin |
| GET/POST/PATCH | `/v1/admin/cms/pages` | CMS CRUD |
| POST | `/v1/admin/cms/pages/{id}/publish` | publish |
| POST | `/v1/public/leads` | anon leads (X-Tenant-Slug) |
| GET | `/v1/public/cms/pages/{slug}` | published CMS |
| GET/PATCH | `/v1/tenant/feature-flags` | tenant flags |
| GET | `/v1/tenant/me` | tenant context |
| POST | `/v1/leads` | tenant-scoped leads |
| POST | `/v1/operator/chat` | operator MVP |

---

## Sprint 3 — исполнимый план (строго по порядку)

**Принцип:** сначала безопасность (E0/E1 exit), потом production connectivity, потом selling website, потом FAQ/CMS, Operator — только basic read-only loop в конце.  
**E0/E1 ещё не закрыты** — cross-tenant isolation, ACL smoke, brain init-db, provenance, FAQ from API остаются todo.

### P0 — блокеры (делать первым)

| # | Шаг | Задачи | Статус |
|---|-----|--------|--------|
| 1 | **Tenant isolation + ACL** | E0.13, E1.3; CI | ✅ |
| 2 | *(внутри #1)* | ACL automated smoke | ✅ |
| 3 | **Init production brain** | E1.2: init-db, demo vault, demo tenant, tenant-scoped search, provenance | ✅ |
| 4 | **Site → real leads API** | P1.4: `DELNO_API_URL`, rebuild staging, leads → PG | ✅ code + deploy |
| 5 | **DNS + production ingress** | P1.6/P1.7, H3/H4: reg.ru DNS → `5.35.86.62`, `dlno.ru`, `api.dlno.ru`, SSL, health, CORS, prod env | ⬜ deferred; staging OK |

**Не делать до шага 1:** Operator с write-tools по tenant data.

### P1 — product + CMS

| # | Шаг | Задачи | Критерий готовности |
|---|-----|--------|---------------------|
| 6 | **Selling Website exit** | P1.1 hero, P1.2 каналы, P1.3 CTA, P1.5 mobile, P1.8 privacy/terms | 🔄 hero/CTA на staging; mobile + clarity test pending |
| 7 | **Clarity test** | P1.9: 3+ незнакомых с DELNO | Минимум 3 человека понимают продукт; если 2+ говорят «AI-платформа» / «чат-бот» — hero переделывать |
| 8 | **FAQ from CMS** | E1.7: draft/publish, site = published only, fallback + cache | ✅ site fetch + fallback |
| 9 | **Provenance** | E1.4: source metadata в knowledge responses | API возвращает tenant-safe provenance |

### P2 — Operator + observability foundation

| # | Шаг | Задачи | Критерий готовности |
|---|-----|--------|---------------------|
| 10 | **Basic Operator LLM** | E3.2: `/v1/operator/chat`, model provider, system prompt, tenant context, **read-only KB search**, history, errors | ✅ read-only KB loop |
| 11 | **Operational events** | E0.15: `lead.created`, `knowledge.search_failed`, `operator.error`, `integration.error`, `auth.failed`, `tenant.isolation_violation` | Events пишутся; фундамент для E6 Supervisor |
| 12 | **Docs/status** | Обновить roadmap + master plan | REV актуален |

### Sprint 3 — exit criteria (все одновременно)

- [x] Tenant isolation тестируется автоматически (CI)
- [x] ACL работает (guest ≠ owner)
- [x] Brain инициализирован (demo vault + tenant search)
- [ ] `dlno.ru` + `api.dlno.ru` production работают (DNS deferred)
- [x] Форма сайта пишет лид в PG (staging verified 2026-09-01)
- [ ] Сайт понятен 3+ людям за 5–10 сек (P1.9)
- [x] FAQ из CMS без code deploy (fallback + `/api/cms/faq`)
- [x] Operator безопасно отвечает по tenant KB (read-only)
- [ ] Ни одной задачи E4+ / future product modules не начато

### DO NOT START в Sprint 3

CRM (в т.ч. CRM Lite), marketplace, bank integrations, PSTN/SIP telephony, phone provisioning, Mango multi-tenant, full Voice Worker, billing payments, reseller/white-label, full booking, marketing automation, advanced Tool Registry, mass actions, **repo migration** из quantum-office.

### Разрешено: stub/interface без полной реализации

ChannelAdapter, ModelProvider, ToolRegistry, event bus, feature flags, usage records — контракт да, большой subsystem нет.

---

## Анти-scope (не делаем сейчас)

Full CRM, marketplace, billing payments, PSTN telephony, bank layer — см. Product Guardrails в master plan.
