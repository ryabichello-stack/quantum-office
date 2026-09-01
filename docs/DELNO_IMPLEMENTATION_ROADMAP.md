# DELNO — план реализации (детальный checklist)

**Canonical strategy:** [`DELNO_MASTER_PLAN.md`](DELNO_MASTER_PLAN.md)  
**Домены:** [`DLNO_DOMAINS.md`](DLNO_DOMAINS.md)  
**Обновлено:** 2026-09-01

Легенда: ✅ done · 🔄 in progress · ⬜ todo

---

## Трек A — Product (параллельно с engineering)

### P1 — Selling Website (`dlno.ru` + staging)

| # | Задача | Статус |
|---|--------|--------|
| P1.1 | Hero: «ИИ-сотрудник» — clarity за 5–10 сек | ⬜ |
| P1.2 | Блок каналов: телефон, сайт, Telegram, MAX, email | ⬜ |
| P1.3 | CTA «Попробовать» → voice demo + lead form | ⬜ |
| P1.4 | Leads с сайта → **delno-api** (не local-only) | 🔄 |
| P1.5 | Mobile UX / lighthouse pass | ⬜ |
| P1.6 | `dlno.ru` DNS Cloudflare → `5.35.86.62` | ⬜ |
| P1.7 | SSL на origin (Cloudflare Full / certbot) | ⬜ |
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
| E0.6 | Alembic migrations (replace create_all) | 🔄 |
| E0.7 | Channel router skeleton | 🔄 |
| E0.8 | `/v1/public/*` namespace | 🔄 |
| E0.9 | Feature flags read/write API | 🔄 |
| E0.10 | Model provider abstraction stub | 🔄 |
| E0.11 | Deploy full stack prod: api + knowledge + postgres | ⬜ |
| E0.12 | CI: pytest delno-api + brain security tests | ⬜ |
| E0.13 | Cross-tenant isolation integration test | ⬜ |
| E0.14 | **Exit E0:** admin creates tenant; events emit; flags work | ⬜ |

---

## Трек C — Engineering E1 Knowledge + CMS

| # | Задача | Статус |
|---|--------|--------|
| E1.1 | delno-knowledge container prod `:18021` | ⬜ |
| E1.2 | Init brain DB + seed demo vault | ⬜ |
| E1.3 | ACL smoke: guest ≠ owner (automated) | ⬜ |
| E1.4 | Knowledge provenance in API responses | ⬜ |
| E1.5 | CMS models: pages, revisions | 🔄 |
| E1.6 | Admin CMS CRUD draft/publish | 🔄 |
| E1.7 | Site fetch published CMS (FAQ block pilot) | ⬜ |
| E1.8 | Auto-ingest tenant settings → brain | ⬜ |
| E1.9 | Per-tenant vault path isolation | ⬜ |
| E1.10 | **delno-admin** scaffold: login + tenants + CMS | 🔄 |
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
| E3.1 | **delno-web** scaffold: login + dashboard shell | 🔄 |
| E3.2 | Operator LLM loop (OpenAI) | ⬜ |
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
| H5 | Unified deploy script `/opt/delno` full stack | 🔄 |
| H6 | `app.dlno.ru`, `admin.dlno.ru` nginx (later) | ⬜ |

---

## Текущий спринт (крупный блок — делаем сейчас)

1. 🔄 Alembic + initial migration  
2. 🔄 CMS models + admin CMS API  
3. 🔄 Channel router + public leads API  
4. 🔄 Site `/api/leads` → delno-api proxy  
5. 🔄 Feature flags tenant API  
6. 🔄 Model provider stub  
7. 🔄 delno-admin scaffold (login, tenants list)  
8. 🔄 delno-web scaffold (login, dashboard shell)  
9. ⬜ Prod deploy: api upgrade + knowledge container  
10. ⬜ Tests batch (+integration)

**Следующий спринт после этого:** E1 prod knowledge + ACL tests + CMS-driven FAQ on site + Operator LLM.

---

## Анти-scope (не делаем сейчас)

- Full CRM, marketplace, billing payments, PSTN telephony, bank layer  
- См. Product Guardrails в master plan
