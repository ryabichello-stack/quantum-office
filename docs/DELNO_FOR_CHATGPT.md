# DELNO — единая точка входа для ChatGPT

**Revision:** REV-3.2 · 2026-09-01 (Sprint 3 mid-flight)

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
Прочитай entry point и все связанные документы по raw URL из него (REV-3.2):

https://raw.githubusercontent.com/ryabichello-stack/quantum-office/cursor/delno-api-scaffold-14e9/docs/DELNO_FOR_CHATGPT.md

Открой каждый raw URL из секции «Карта документов».
Подтверди revision REV-3.2.

Твоя задача — аудит Sprint 3. Ответь структурированно:

1. **Что уже сделано** — сверь с секцией «Sprint 3 — текущий статус» и roadmap; отметь расхождения.
2. **Что забыли / пропустили / не закрыли** — exit criteria E0/E1, дыры в безопасности, незадеплоенное, docs drift.
3. **Что делать дальше** — строго по приоритету Sprint 3; что блокирует exit; что можно параллельно.
4. **Комментарии** — риски, scope creep, качество hero/P1, готовность к clarity test (P1.9).
5. **Не предлагать** — CRM, marketplace, telephony, billing, repo migration (см. DO NOT START).

Формат: таблицы + короткие bullet lists. Без воды.
```

---

## Карта документов

| # | Документ | Зачем | Raw URL |
|---|----------|-------|---------|
| 1 | **Этот файл** | Точка входа, промпт, актуальный статус | см. ссылку выше |
| 2 | **Master plan** | Стратегия, архитектура, guardrails, E0–E10 | https://raw.githubusercontent.com/ryabichello-stack/quantum-office/main/docs/DELNO_MASTER_PLAN.md |
| 3 | **Roadmap** | Checklist, Sprint 3, API endpoints | https://raw.githubusercontent.com/ryabichello-stack/quantum-office/cursor/delno-api-scaffold-14e9/docs/DELNO_IMPLEMENTATION_ROADMAP.md |
| 4 | **Domains** | dlno.ru, DNS, nginx (справочно) | https://raw.githubusercontent.com/ryabichello-stack/quantum-office/main/docs/DLNO_DOMAINS.md |

**Проверка версии master plan:** строка `DELNO-MASTER-PLAN-REV-3` + секция `Rev.3 — Implementation Status`.

---

## Краткий контекст

- **DELNO** — multi-tenant SaaS «ИИ-сотрудник» (телефон, сайт, мессенджеры, KB, голос per tenant)
- **KB foundation:** Second Brain (`brain_platform`) в `delno-knowledge/` — не писать с нуля
- **Prod server:** `5.35.86.62` · изолированный стек `/opt/delno` (не трогать `/opt/polyhub`, `/root/ava`, ava-outreach runtime)
- **Repo:** quantum-office monorepo (временно) · ветка `cursor/delno-api-scaffold-14e9` · PR [#20](https://github.com/ryabichello-stack/quantum-office/pull/20)
- **DNS:** домен на **reg.ru** (NS: `ns1.reg.ru`, `ns2.reg.ru`), **не Cloudflare** — prod DNS отложен пользователем; dev на staging

### Staging (работает сейчас)

| Что | URL |
|-----|-----|
| Marketing site | https://a.47z.ru/delno/ |
| API | https://a.47z.ru/delno-api/v1/health |
| Leads (site proxy) | `POST https://a.47z.ru/delno/api/leads` |
| FAQ CMS proxy | `GET https://a.47z.ru/delno/api/cms/faq` |

### Prod (готово infra, ждёт DNS)

| Что | URL / статус |
|-----|--------------|
| Site root container | `:18022`, nginx для `dlno.ru` готов |
| API prod ingress | `api.dlno.ru` — nginx готов, DNS pending |
| Целевые A-записи | `@`, `www`, `api` → `5.35.86.62` |

**Dev credentials (seeded):** `admin@delno.one` / `admin123456`, `owner@delno.one` / `demo123456`

---

## Sprint 3 — текущий статус (2026-09-01)

Легенда: ✅ done · 🔄 in progress · ⬜ todo · ⏸ deferred

### P0 — блокеры

| # | Задача | Статус | Примечание |
|---|--------|--------|------------|
| 1 | Cross-tenant isolation tests | ✅ | `delno-api/tests/test_tenant_isolation.py`, brain tests, CI |
| 2 | ACL smoke (guest ≠ owner) | ✅ | principals fix `text-guest`, operator tool ACL |
| 3 | Brain init-db + demo vault | ✅ | `seed-demo`, docker entrypoint, provenance in search |
| 4 | Site → leads → PostgreSQL | ✅ | staging smoke 2026-09-01 |
| 5 | DNS + prod ingress (`dlno.ru`, `api.dlno.ru`) | ⏸ | reg.ru, пользователь настроит позже |

### P1 — product + CMS

| # | Задача | Статус | Примечание |
|---|--------|--------|------------|
| 6 | Selling website exit | 🔄 | hero v4 на `/`, каналы, CTA — OK; mobile + terms pending |
| 7 | Clarity test (P1.9) | ⬜ | 3+ человека, 5–10 сек — **ручной шаг владельца** |
| 8 | FAQ from CMS | ✅ | `FaqSection` + `/api/cms/faq`, fallback static |
| 9 | Provenance in API responses (E1.4) | ⬜ | есть в brain search matches; не везде в delno-api |

### P2 — Operator + observability

| # | Задача | Статус | Примечание |
|---|--------|--------|------------|
| 10 | Basic Operator LLM (read-only KB) | ✅ | `/v1/operator/chat`, 22 pytest pass |
| 11 | Operational events (E0.15) | ⬜ | `lead.created`, `auth.failed`, … — не начато |
| 12 | Docs/status sync | 🔄 | roadmap обновлён; master plan частично отстаёт |

### Sprint 3 exit criteria (чеклист)

- [x] Tenant isolation в CI
- [x] ACL guest ≠ owner
- [x] Brain init + demo tenant search
- [ ] `dlno.ru` + `api.dlno.ru` live (DNS deferred)
- [x] Lead form → PG (staging verified)
- [ ] Clarity test P1.9 (3+ людей)
- [x] FAQ from CMS (site proxy)
- [x] Operator read-only KB
- [x] E4+ / future modules не начаты

---

## Что сделано в PR #20 (коммиты)

| Коммит | Суть |
|--------|------|
| `78d916c` | P0: isolation + ACL smoke + GitHub CI |
| `88e498b` | P0: brain init-db + demo vault seed |
| `1e49a19` | P0: site leads → delno-api PostgreSQL |
| `d99c7a2` | FAQ from CMS + Operator LLM read-only |
| `bfc8754` | Default landing = v4 hero; staging rebuild |

**Последний deploy staging:** 2026-09-01, full stack rebuild на `5.35.86.62`.

---

## Что забыли / не закрыли (явно для аудита)

ChatGPT, проверь эти пункты особенно:

| Область | Gap | Критичность |
|---------|-----|-------------|
| **E0.14 exit** | Admin creates tenant + events emit + flags — не формально закрыт | medium |
| **E1.11 exit** | KB search + CMS FAQ end-to-end через admin UI — частично (API есть, admin flow?) | medium |
| **E1.4 provenance** | Metadata в delno-api responses для tenant UI — не везде | medium |
| **E1.8–E1.9** | Auto-ingest settings → brain; per-tenant vault isolation | low (S3+) |
| **P1.5 mobile** | Lighthouse / responsive pass не делали | high для P1 exit |
| **P1.8 legal** | Privacy/terms для dlno.ru — не обновляли под prod domain | high перед prod DNS |
| **P1.9 clarity** | Нет результатов теста 3+ людей | **блокер P1 exit** |
| **E0.15 events** | Operational event bus не реализован | high для observability |
| **DNS docs drift** | `DLNO_DOMAINS.md` / roadmap ещё упоминают Cloudflare | low (docs) |
| **Site repo completeness** | Большая часть `DELNO-site-v23/` не в git (только ключевые файлы) | medium (CI/build risk) |
| **delno-site-root** | Prod root site `:18022` — не пересобирали в последнем deploy | low |
| **Master plan sync** | `DELNO_MASTER_PLAN.md` может отставать от roadmap REV-3.1 | low |

---

## Что делать дальше (рекомендуемый порядок)

**Без DNS (можно сейчас):**

1. **P1.9 Clarity test** — 3+ человека открывают https://a.47z.ru/delno/, фиксируют первое впечатление за 5–10 сек
2. **P1.5 Mobile UX** — lighthouse, hero/CTA/forms на 375px
3. **E0.15 Operational events** — минимальный event log для leads, auth, operator errors
4. **E1.4 Provenance** — единый формат source metadata в API responses
5. **P1.8 Privacy/terms** — актуализировать под dlno.ru / office@dlno.ru
6. **E0.14 / E1.11 formal exit** — smoke через admin: tenant → CMS publish → site

**После DNS (reg.ru):**

7. A-записи `@`, `www`, `api` → `5.35.86.62`
8. SSL (certbot или reg.ru)
9. Smoke: `https://dlno.ru`, `https://api.dlno.ru/v1/health`, lead → prod DB
10. CORS / env для prod origins

**Не начинать до закрытия Sprint 3 exit:** E2 channels, E3 widget embed, E4 telephony, CRM, billing, repo migration.

---

## DO NOT START (Sprint 3 guardrails)

CRM, marketplace, bank integrations, PSTN/SIP telephony, phone provisioning, Mango multi-tenant, full Voice Worker, billing payments, reseller/white-label, full booking, marketing automation, advanced Tool Registry, mass actions, **repo migration** из quantum-office.

---

## Smoke-команды (staging)

```bash
curl -sf https://a.47z.ru/delno-api/v1/health
curl -sf https://a.47z.ru/delno/ | head -c 200
curl -sf https://a.47z.ru/delno/api/cms/faq
curl -sf -X POST https://a.47z.ru/delno/api/leads \
  -H 'Content-Type: application/json' \
  -d '{"source":"smoke","name":"Test","phone":"+79990001122"}'
```

На сервере:

```bash
ssh root@5.35.86.62
systemctl status ava-outreach ava-mailer ava-text-bot  # не ломать
docker ps | grep delno
curl -sf http://127.0.0.1:18020/v1/health
curl -sf http://127.0.0.1:18021/api/brain/health
```

---

## Ключевые пути в репо

| Путь | Назначение |
|------|------------|
| `delno-api/` | FastAPI, auth, CMS, leads, operator |
| `delno-knowledge/` | brain_platform, vault, search |
| `DELNO-site-v23/` | Next.js marketing site |
| `delno-api/deploy/` | docker-compose, install scripts |
| `.github/workflows/delno-tests.yml` | CI pytest |
