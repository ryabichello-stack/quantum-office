# GAP ANALYSIS — AS-IS vs AI Revenue OS

**Дата:** 2026-08-23

Легенда: ✅ есть · 🟡 частично · ❌ нет

---

## 1. Сводка по доменам ТЗ

| Домен ТЗ | AS-IS | Gap |
|----------|-------|-----|
| Accounts & LPR Graph | 🟡 Bitrix mirror + company card + DaData | Нет lifecycle, committee, evidence, multi-entity |
| Quantum Radar | ❌ | Нет ICP search / signals feed |
| Social Intelligence | ❌ (кроме Telegram bot) | Весь pipeline + adapters |
| Identity Graph | ❌ | Clustering / verification workflow |
| Lead Capture | 🟡 callback CTA, Bitrix, sheets | Нет forms/UTM/SLA/owner унифицировано |
| Quantum Inbox | 🟡 email inbox thread + reply | Нет omnichannel, AI suggested reply из SB |
| Quantum Outreach | ✅ sequences, windows, caps, A–G3 ops | Нет journey versions, multi-threading committee, network-neutral social steps |
| AVA Voice | 🟡 Console + AVA + telephony→Bitrix | Нет RAG-ответов на звонке из SB claims, qualification schema |
| Content Studio | ❌ | Greenfield |
| Video Studio | ❌ | Greenfield |
| Sales Pipeline | 🟡 Bitrix deals | Нет локальной воронки Opportunity |
| Analytics & Attribution | 🟡 funnel + step % | Нет meeting/revenue attribution |
| Revenue Orchestrator | 🟡 runner + sequences | Нет event graph / approvals / global guardrails |
| Second Brain | ✅ brain_platform | Нужна связь claims → reply/content |
| Multi-tenant SaaS | ❌ (schema ready in brain) | Этап 8 |
| RBAC | ❌ single token | Этап 8 |

---

## 2. Capability matrix — социальные источники

| Источник | Search people | Company page | Public content | Inbound owned | Publish | Direct message | AS-IS код |
|----------|---------------|--------------|----------------|---------------|---------|----------------|-----------|
| Telegram | 🟡 username/import | 🟡 channels | 🟡 | ✅ bot | 🟡 channel admin | ❌ cold | text-bot, ops_notify, files |
| VK | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ MANUAL only (цель) | нет |
| Одноклассники | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ MANUAL | нет |
| TenChat | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ MANUAL | нет |
| LinkedIn | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ MANUAL | нет |
| MAX | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | нет |
| YouTube | ❌ | ❌ | ❌ | ❌ | ❌ | — | нет |
| Web / company site | 🟡 ручной / DaData | 🟡 | ❌ crawler | — | — | — | DaData only |
| Реестры | 🟡 через DaData/Bitrix | 🟡 INN | — | — | — | — | DaData |
| Bitrix CRM | ✅ contacts | ✅ companies | — | — | — | — | clients module |
| Email | — | — | — | ✅ IMAP | ✅ SMTP | ✅ | outreach |
| Voice | — | — | — | ✅ | — | ✅ dial | console / AVA |

**Правило ТЗ:** отсутствие capability ≠ browser automation. Режим: API / indexed public / import / user-assisted / `MANUAL_TASK`.

---

## 3. Mapping статусов

| Vault canonical | AS-IS эквивалент | Действие |
|-----------------|------------------|----------|
| `NEW` | Bitrix company без outbox / pending | Ввести Account.lifecycle |
| `ENRICHED` | есть timezone/inn/director | Флаг enrichment |
| `IN_SEQUENCE` | sequence `active` | Map |
| `REPLIED` | outbox `replied` / inbox | Map |
| `INTERESTED` | class `positive_interest` | Map |
| `MEETING_BOOKED` | calendar/conference event? слабо | Нужна Meeting entity |
| `DISQUALIFIED` | skipped / policy | Map |
| `NO_RESPONSE` | sequence completed без reply | Map |
| `BLACKLISTED` | `manual_dnc` + suppression | Map 1:1 |

---

## 4. Событийная модель

| Нужно (ТЗ) | AS-IS |
|------------|-------|
| Единый event envelope | ❌ разрозненные вызовы notify / Bitrix |
| Idempotency / outbox | 🟡 ops_notify dedup, IMAP message_id |
| `message.received` → orchestrator | 🟡 reply_watcher side effects |
| `call.completed` → orchestrator | 🟡 Console watcher → Telegram only |
| `journey.stopped` на reply | ✅ sequence stop / OOO pause |

---

## 5. Два обязательных среза — gap detail

### Slice A — Unified inbound

| Шаг | Статус |
|-----|--------|
| Приём email reply | ✅ |
| Приём call completed | 🟡 notify есть, нет Lead unify |
| Resolve Account/Person | 🟡 company_id / Bitrix |
| Inbox UI | ✅ thread + reply |
| AI classification | 🟡 rules-based, не LLM+SB citations |
| Suggested reply from Second Brain | ❌ |
| Lead/Opportunity local | ❌ Bitrix only |
| Audit + attribution | 🟡 partial |

### Slice B — Universal LPR search

| Шаг | Статус |
|-----|--------|
| Company input | ✅ clients / Bitrix |
| DecisionRoleTemplate | ❌ |
| Multi-network search | ❌ |
| Candidate scoring + evidence | ❌ |
| Identity cluster + human verify | ❌ |
| Committee coverage UI | ❌ |
| SocialActionTask | ❌ |

---

## 6. Технический долг и неизвестные

| # | Риск / неизвестное | Нужно решение |
|---|-------------------|---------------|
| 1 | `main` ≠ prod | Merge PR #10 до миграций |
| 2 | Legal/ToS VK/OK/TenChat/LinkedIn search | Capability matrix per connector; юр. review |
| 3 | Где SoT компаний: Bitrix vs local Account | Dual-write → local SoT + Bitrix sync |
| 4 | call_history вне репо | Facade + backup policy |
| 5 | LLM cost на classification | Budget + cheap model first |
| 6 | sheets-campaign vs outreach | Отдельный контур; не смешивать в Account без map |
| 7 | mailer legacy calendar | Не ломать; calendar/conference уже вынесены |
| 8 | Multi-tenant timing | Не блокировать Slice A/B |

---

## 7. Переиспользуемые компоненты (явный список)

1. `outreach/outbox.py` + `sender.py` + `modules/sequences`
2. `outreach/modules/replies` (+ thread/reply)
3. `outreach/modules/consent` + deliverability suppression
4. `outreach/modules/clients` + `company_card.py` + DaData
5. `outreach/ops_notify.py` + Console `_panel_notify`
6. `console/main.py` calls / dial / line
7. `knowledge/brain_platform/` RAG + vault claims
8. `calendar/` + `conference/` для Meeting
9. `text-bot/` как Telegram channel adapter seed
10. Geo windows / fairness (`geo_schedule.py`)
