# DELNO — единая точка входа для ChatGPT

**Revision:** REV-4.3 · 2026-09-04 (Widget Commit 2 — security hardening)

**Активный продуктовый этап:** Crystal Widget + Conversation Core — см. [`DELNO_WIDGET_AUDIT.md`](DELNO_WIDGET_AUDIT.md) AUDIT-1.0.

---

## ⚠️ Marketing site — canonical version

**Default landing `/` = v2 only.** Owner **rejected v4 hero** as default (2026-09-01).

| | |
|---|---|
| **Canonical** | v2 — «Клиенты пишут и звонят. DELNO отвечает.» |
| **Not default** | v4 — only at `/v4`, do not switch `/` without owner approval |
| **Doc** | [`P1.1_SITE_LANDING.md`](P1.1_SITE_LANDING.md) |

**Agents: do not redeploy v4 to `/`.**

---

## Что отправлять ChatGPT

**Одна ссылка — только эту:**

https://raw.githubusercontent.com/ryabichello-stack/quantum-office/main/docs/DELNO_FOR_CHATGPT.md

> Если PR [#20](https://github.com/ryabichello-stack/quantum-office/pull/20) ещё не в `main`, используй raw URL ветки:
> https://raw.githubusercontent.com/ryabichello-stack/quantum-office/cursor/delno-api-scaffold-14e9/docs/DELNO_FOR_CHATGPT.md

Мастер-план, роудмап и домены **отдельно не отправляй** — они перечислены ниже, ChatGPT сам откроет по raw URL.

---

## Промпт (скопируй целиком)

```
Прочитай entry point и все связанные документы по raw URL из него (REV-4.1):

https://raw.githubusercontent.com/ryabichello-stack/quantum-office/cursor/delno-api-scaffold-14e9/docs/DELNO_FOR_CHATGPT.md

Открой каждый raw URL из секции «Карта документов».
Подтверди revision REV-4.1.

Твоя задача — аудит текущего состояния DELNO. Ответь структурированно:

1. **Что уже сделано** — сверь с секцией «Текущий статус» и roadmap; отметь расхождения.
2. **Что забыли / пропустили / не закрыли** — exit criteria, дыры в безопасности, docs drift.
3. **Что делать дальше** — строго по приоритету; что блокирует; что можно параллельно.
4. **Комментарии** — риски, scope creep, готовность prod cabinet.
5. **Не предлагать** — CRM, marketplace, telephony (E4 full), billing, repo migration, **v4 hero as default landing**.

Формат: таблицы + короткие bullet lists. Без воды.
```

---

## Карта документов

| # | Документ | Зачем | Raw URL |
|---|----------|-------|---------|
| 1 | **Этот файл** | Точка входа, промпт, актуальный статус | см. ссылку выше |
| 2 | **Master plan** | Стратегия, архитектура, guardrails, E0–E10 | https://raw.githubusercontent.com/ryabichello-stack/quantum-office/cursor/delno-api-scaffold-14e9/docs/DELNO_MASTER_PLAN.md |
| 3 | **Roadmap** | Checklist, что ✅ сделано, API endpoints | https://raw.githubusercontent.com/ryabichello-stack/quantum-office/cursor/delno-api-scaffold-14e9/docs/DELNO_IMPLEMENTATION_ROADMAP.md |
| 4 | **Domains** | dlno.ru, DNS reg.ru, nginx | https://raw.githubusercontent.com/ryabichello-stack/quantum-office/cursor/delno-api-scaffold-14e9/docs/DLNO_DOMAINS.md |
| 5 | **Clarity test** | P1.9 протокол (⏸ deferred) | https://raw.githubusercontent.com/ryabichello-stack/quantum-office/cursor/delno-api-scaffold-14e9/docs/P1.9_CLARITY_TEST.md |
| 6 | **Mobile pass** | P1.5 checklist 375/390px | https://raw.githubusercontent.com/ryabichello-stack/quantum-office/cursor/delno-api-scaffold-14e9/docs/P1.5_MOBILE_PASS.md |
| 7 | **DaData party enrichment** | E1.12–E1.15 spec | https://raw.githubusercontent.com/ryabichello-stack/quantum-office/cursor/delno-api-scaffold-14e9/docs/E1.12_DADATA_PARTY_ENRICHMENT.md |
| 8 | **Site landing (v2 canonical)** | v4 rejected as `/` default | https://raw.githubusercontent.com/ryabichello-stack/quantum-office/cursor/delno-api-scaffold-14e9/docs/P1.1_SITE_LANDING.md |
| 9 | **Widget product audit** | Crystal Widget + Conversation Core plan, DoD, commits | https://raw.githubusercontent.com/ryabichello-stack/quantum-office/cursor/delno-api-scaffold-14e9/docs/DELNO_WIDGET_AUDIT.md |

**Проверка версии master plan:** строка `DELNO-MASTER-PLAN-REV-3.3` + секция `Rev.3 — Implementation Status`.

---

## Краткий контекст

- **DELNO** — multi-tenant SaaS «ИИ-сотрудник» (телефон, сайт, мессенджеры, KB, голос per tenant)
- **KB foundation:** Second Brain (`brain_platform`) в `delno-knowledge/` — не писать с нуля
- **Prod server:** `5.35.86.62` · изолированный стек `/opt/delno` (не трогать `/opt/polyhub`, `/root/ava`, ava-outreach runtime)
- **Repo:** quantum-office monorepo (временно) · ветка `cursor/delno-api-scaffold-14e9` · PR [#20](https://github.com/ryabichello-stack/quantum-office/pull/20)
- **Deploy:** tar + scp на сервер (без git на prod); `docker compose build api` + отдельный `delno-web` container `:18023`

### Prod (работает)

| Что | URL |
|-----|-----|
| Marketing site | https://dlno.ru |
| **Tenant cabinet** | https://app.dlno.ru |
| API | https://api.dlno.ru/v1/health |
| Widget CDN | https://cdn.dlno.ru/widget/v1/embed.js |

### Staging (работает)

| Что | URL |
|-----|-----|
| Marketing site | https://a.47z.ru/delno/ |
| **Tenant cabinet** | https://a.47z.ru/delno-app/ |
| API | https://a.47z.ru/delno-api/v1/health |
| Leads (site proxy) | `POST https://a.47z.ru/delno/api/leads` |
| FAQ CMS proxy | `GET https://a.47z.ru/delno/api/cms/faq` |

**Cabinet credentials (seed):** `owner@delno.one` / `demo123456`  
**Platform admin:** `admin@delno.one` / `admin123456`

---

## Текущий статус (2026-09-04)

Легенда: ✅ done · 🔄 in progress · ⬜ todo · ⏸ deferred

### P0 — foundation

| # | Задача | Статус |
|---|--------|--------|
| Cross-tenant isolation + CI | ✅ |
| ACL guest ≠ owner | ✅ |
| Brain init + demo vault | ✅ |
| Site → leads → PG | ✅ staging + prod |
| DNS + prod ingress | 🔄 dlno.ru live; subdomains mostly OK |

### P1 — product + CMS

| # | Задача | Статус |
|---|--------|--------|
| Selling website (v2 hero) | ✅ |
| Clarity test P1.9 | ⏸ deferred |
| FAQ from CMS | ✅ |
| Provenance E1.4 | ✅ |

### P2 — First Value + cabinet

| # | Задача | Статус |
|---|--------|--------|
| Self-service register | ✅ `POST /v1/auth/register` |
| KB upload | ✅ `POST /v1/tenant/knowledge/documents` |
| Widget embed in cabinet | ✅ `GET /v1/tenant/widget` |
| Time to First Value | 🔄 flow ready, not measured |

### E3 — Widget + Operator + cabinet UI

| # | Задача | Статус | Примечание |
|---|--------|--------|------------|
| E3.1 Cabinet MVP | ✅ | login, leads, inbox, operator, settings |
| E3.2 Operator read-only KB | ✅ | `/v1/operator/chat` |
| E3.3 Tool registry + confirmation | ✅ | READ/SAFE_WRITE/HIGH_IMPACT; LLM tool calling |
| E3.4 Embeddable widget | 🔄 | CDN embed ✅; API security Commit 2 ✅ |
| E3.5 Voice WebRTC widget | ⬜ | |
| E3.6 Voice→text fallback | ⬜ | |
| E3.7 KB UI upload/publish | 🔄 | upload + list in `/dashboard/knowledge` |
| E3.8 Widget lead → inbox | 🔄 | API ✅; CDN UX Commit 1 |

**Product phase:** [`DELNO_WIDGET_AUDIT.md`](DELNO_WIDGET_AUDIT.md) — Crystal Widget + Conversation Core.

**Cabinet visual parity (marketing mock):**

| Фаза | Что | Статус |
|------|-----|--------|
| 1 | Operator orb + live setup (KB, flags, settings) | ✅ |
| 2 | Inbox enriched (names, preview, voice playback, DELNO result card) | ✅ |
| 3 | Sidebar nav (Диалоги · Клиенты · Календарь · Знания · Operator · Настройки) | ✅ |
| 4 | Crystal orb CSS 1:1 (phase-driven from widget) | ✅ |
| — | Appointment card in inbox | ⬜ blocked on E4 booking backend — **не фейкать** |

**Operator cabinet features (prod):**

- Crystal orb + STT/TTS (`GET /v1/operator/tts`, JWT)
- Quick chips + confirm card for write tools
- Tools: `get_tenant_summary`, `update_tenant_settings`, `upload_knowledge_snippet`, `set_feature_flag`
- Regex intents + LLM tool calling fallback

### E2 — Communication (started post-S3)

| # | Задача | Статус |
|---|--------|--------|
| E2.1 ChannelAdapter + registry | ✅ |
| E2.2 Telegram shared bot | 🔄 webhook MVP; auto-reply ⬜ |
| E2.5 Webhook signing + events | 🔄 `X-Telegram-Bot-Api-Secret-Token` + `message.received` |
| E2.6 Router token → tenant | ✅ `channel_router` + account id in URL |
| E2.7 Inbound → conversation | ✅ `POST /v1/webhooks/telegram/{channel_account_id}` |
| E2.3 Branded bot wizard | ⬜ |
| E2.8 Email stub | ⬜ |

**Telegram webhook URL (per tenant channel account):**

```
POST https://api.dlno.ru/v1/webhooks/telegram/{channel_account_id}
Header: X-Telegram-Bot-Api-Secret-Token: {channel_accounts.meta.webhook_secret}
```

### E1 — Knowledge + DaData

E1.12–E1.15 ✅ · E1.16 CRM push ⬜ **DO NOT START**

### E4+ — NOT STARTED

Telephony, booking, billing, CRM — см. guardrails ниже.

---

## Что сделано в PR #20 (коммиты, новые сверху)

| Коммит | Суть |
|--------|------|
| `a7525b4` | E2 Telegram webhook → conversation; orb CSS parity; KB list UI |
| `a0a84f5` | E3.3 LLM tool calling; sidebar nav; calendar/knowledge pages |
| `3a4e8db` | Operator TTS via API (JWT, OpenAI mp3) |
| `6b40f10` | Inbox enriched UI (console mock parity) |
| `60555d5` | Operator crystal orb + live cabinet setup tools |
| `4eda703` | P2 register, KB upload, widget embed in cabinet |
| `074b070` | E3.4 CDN embed; E1.8 settings sync; E1.9 vault paths |
| `78d916c` | P0: isolation + ACL + CI |
| `d99c7a2` | FAQ CMS + Operator read-only |

**Последний deploy prod:** 2026-09-04 · `app.dlno.ru` + `api.dlno.ru` health 200

---

## Что забыли / не закрыли (для аудита)

| Область | Gap | Критичность |
|---------|-----|-------------|
| **P1.9 clarity** | Нет теста 3+ людей | blocker P1 exit |
| **P2.4 TTFV** | Flow есть, не измерен | low |
| **E2.2 auto-reply** | Webhook пишет в PG, бот не отвечает | medium |
| **E3.5 WebRTC** | Voice widget не начат | medium |
| **E3.7 KB list** | Список из events, не из brain catalog | low |
| **Appointment card** | Ждёт E4 booking | — не делать fake |
| **PR #20 merge** | draft, возможен conflict с main | P1 |
| **Docs drift** | Master plan REV-3.3 может отставать от E2/E3 | low |

---

## Что делать дальше (рекомендуемый порядок)

**Сейчас (без блокеров):**

1. **E2.2** — shared DELNO Telegram bot: webhook → auto-reply → inbox thread
2. **E3.5** — WebRTC voice widget MVP
3. **P1.9** clarity test — ⏸ когда owner вернётся
4. Обновить master plan REV-3.4+ под E2/E3 статус

**Не начинать:**

- E1.16 CRM push до triggers
- E4 telephony / booking / appointment UI с fake data
- CRM, marketplace, billing, repo migration

---

## DO NOT START

CRM (Bitrix push E1.16), marketplace, bank integrations, PSTN/SIP telephony, phone provisioning, Mango multi-tenant, full Voice Worker, billing payments, reseller/white-label, **full booking**, marketing automation, mass actions, **repo migration** из quantum-office.

**Stub/interface OK:** ChannelAdapter ✅, ModelProvider ✅, ToolRegistry ✅.

---

## Smoke-команды

### Prod

```bash
curl -sf https://api.dlno.ru/v1/health
curl -sf https://app.dlno.ru/ -o /dev/null -w "%{http_code}\n"
curl -sf https://dlno.ru/ | head -c 200

# Login → operator TTS (needs JWT)
# POST https://api.dlno.ru/v1/auth/login {"email":"owner@delno.one","password":"demo123456"}
# GET  https://api.dlno.ru/v1/operator/tts?text=hello  Authorization: Bearer …
```

### Staging

```bash
curl -sf https://a.47z.ru/delno-api/v1/health
curl -sf https://a.47z.ru/delno-app/
DELNO_API_URL=https://a.47z.ru/delno-api bash delno-api/deploy/smoke_formal_exit.sh
```

### На сервере

```bash
ssh root@5.35.86.62
docker ps | grep delno
curl -sf http://127.0.0.1:18020/v1/health   # api
curl -sf http://127.0.0.1:18023/ -o /dev/null -w "%{http_code}\n"  # web
curl -sf http://127.0.0.1:18021/api/brain/health
systemctl status ava-outreach ava-mailer ava-text-bot  # не ломать
```

---

## Ключевые пути в репо

| Путь | Назначение |
|------|------------|
| `delno-api/app/operator/` | Operator agent, tools, setup intents |
| `delno-api/app/adapters/channels/` | E2 ChannelAdapter (Telegram) |
| `delno-api/app/api/v1/webhooks.py` | Telegram webhook endpoint |
| `delno-api/app/services/inbound_messages.py` | Inbound → conversation |
| `delno-api/app/services/conversation_present.py` | Inbox enrichment |
| `delno-api/app/services/tts.py` | Operator TTS |
| `delno-web/components/OperatorStage.tsx` | Operator UI + orb |
| `delno-web/components/CrystalOrb.tsx` | Crystal orb component |
| `delno-web/styles/crystal-operator.css` | Phase-driven orb CSS |
| `delno-web/app/dashboard/` | Cabinet pages |
| `delno-knowledge/` | brain_platform, vault, search |
| `DELNO-site-v23/` | Next.js marketing site |
| `docs/DELNO_IMPLEMENTATION_ROADMAP.md` | Detailed checklist |

---

## API endpoints (новые с REV-4.0)

| Method | Path | Назначение |
|--------|------|------------|
| POST | `/v1/operator/confirm` | Confirm pending write tool |
| GET | `/v1/operator/tts?text=` | TTS mp3 (JWT) |
| GET | `/v1/operator/conversations` | Enriched inbox list |
| GET | `/v1/operator/conversations/{id}` | Conversation detail |
| GET | `/v1/tenant/knowledge/documents` | KB upload history (E3.7) |
| POST | `/v1/webhooks/telegram/{channel_account_id}` | Telegram inbound (E2) |

**Widget security (Commit 2):** rate limit per `site_key`+IP; `visitor_id` session bind (403 on mismatch); CORS `*.dlno.ru` regex.

Полный список — в [`DELNO_IMPLEMENTATION_ROADMAP.md`](DELNO_IMPLEMENTATION_ROADMAP.md).
