# DELNO — единая точка входа для ChatGPT

**Revision:** REV-3.4 · 2026-09-01 (dlno.ru DNS + nginx ingress all subdomains)

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
Прочитай entry point и все связанные документы по raw URL из него (REV-3.3):

https://raw.githubusercontent.com/ryabichello-stack/quantum-office/cursor/delno-api-scaffold-14e9/docs/DELNO_FOR_CHATGPT.md

Открой каждый raw URL из секции «Карта документов».
Подтверди revision REV-3.3.

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
| 2 | **Master plan** | Стратегия, архитектура, guardrails, E0–E10 | https://raw.githubusercontent.com/ryabichello-stack/quantum-office/cursor/delno-api-scaffold-14e9/docs/DELNO_MASTER_PLAN.md |
| 3 | **Roadmap** | Checklist, что ✅ сделано, Sprint 3, API endpoints | https://raw.githubusercontent.com/ryabichello-stack/quantum-office/cursor/delno-api-scaffold-14e9/docs/DELNO_IMPLEMENTATION_ROADMAP.md |
| 4 | **Domains** | dlno.ru, DNS reg.ru, nginx | https://raw.githubusercontent.com/ryabichello-stack/quantum-office/cursor/delno-api-scaffold-14e9/docs/DLNO_DOMAINS.md |
| 5 | **Clarity test** | P1.9 протокол (⏸ deferred) | https://raw.githubusercontent.com/ryabichello-stack/quantum-office/cursor/delno-api-scaffold-14e9/docs/P1.9_CLARITY_TEST.md |
| 6 | **Mobile pass** | P1.5 checklist 375/390px | https://raw.githubusercontent.com/ryabichello-stack/quantum-office/cursor/delno-api-scaffold-14e9/docs/P1.5_MOBILE_PASS.md |
| 7 | **DaData party enrichment** | E1.12–E1.15 spec (adapter, leads, site, tenant) | https://raw.githubusercontent.com/ryabichello-stack/quantum-office/cursor/delno-api-scaffold-14e9/docs/E1.12_DADATA_PARTY_ENRICHMENT.md |

**Проверка версии master plan:** строка `DELNO-MASTER-PLAN-REV-3.3` + секция `Rev.3 — Implementation Status`.

---

## Внешний аудит ChatGPT (2026-09-01) — принят

**Вердикт:** Sprint 3 ≈ *backend core mostly done, product exit not done*.

**Критический путь до закрытия Sprint 3:**

1. ~~E0.15 operational events~~ ✅  
2. ~~E0.14 formal exit~~ ✅  
3. ~~E1.11 end-to-end~~ ✅  
4. P1.5 mobile pass 🔄 (`mobile.css`, viewport — manual verify)
5. P1.8 privacy/terms ✅ (ИП Рябов Д.В., ИНН/OGRNIP из DaData, office@dlno.ru)
6. P1.9 clarity test — ⏸ deferred ([`P1.9_CLARITY_TEST.md`](P1.9_CLARITY_TEST.md))
7. **E1.12–E1.15 DaData party enrichment** ⬜ — [`E1.12_DADATA_PARTY_ENRICHMENT.md`](E1.12_DADATA_PARTY_ENRICHMENT.md) (parallel post-S3, не блокирует exit)

**Hero P1.1–P1.3:** визуально на staging ✅, но **не считать успешным до P1.9**.

**PR #20:** draft, возможен merge conflict с `main` — resolve перед merge.

**Не начинать:** CRM, marketplace, telephony, billing, repo migration.

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
| Site root + ingress | `:18022` site, `:18023` web, `:18024` admin, nginx all vhosts | 🔄 |
| API prod ingress | `api.dlno.ru` — nginx → :18020 | 🔄 |
| Целевые DNS | A `@` + CNAME subdomains → `5.35.86.62` (reg.ru) | 🔄 см. [`DLNO_DOMAINS.md`](DLNO_DOMAINS.md) |

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
| 5 | DNS + prod ingress (`dlno.ru`, subdomains) | 🔄 | reg.ru A/CNAME → 5.35.86.62; nginx vhosts deployed |

### P1 — product + CMS

| # | Задача | Статус | Примечание |
|---|--------|--------|------------|
| 6 | Selling website exit | 🔄 | P1.1–P1.3 на staging ✅; **не валидирован до P1.9**; P1.8 legal ✅; mobile pending |
| 7 | Clarity test (P1.9) | ⏸ | **deferred** — вернёмся позже; протокол готов |
| 8 | FAQ from CMS | ✅ | `FaqSection` + `/api/cms/faq`, fallback static |
| 9 | Provenance in API responses (E1.4) | ⬜ | есть в brain search matches; не везде в delno-api |

### P2 — Operator + observability

| # | Задача | Статус | Примечание |
|---|--------|--------|------------|
| 10 | Basic Operator LLM (read-only KB) | ✅ | `/v1/operator/chat`, 22 pytest pass |
| 11 | Operational events (E0.15) | ✅ | lead.created, auth.failed, operator.error, knowledge.search_failed |
| 12 | Docs/status sync | ✅ | REV-3.3: entry + roadmap + master + DaData spec |
| 13 | Party enrichment E1.12 | ✅ | adapter + `GET /v1/tenant/party/lookup` |
| 14 | Party enrichment E1.13–E1.15 | ⬜ | leads, site suggest, tenant legal |

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
| **E0.14 exit** | ~~Foundation formal exit~~ | ✅ |
| **E1.11 exit** | ~~Admin CMS → site~~ | ✅ |
| **E1.4 provenance** | Unified source contract в delno-api — не везде | P1 |
| **E1.8–E1.9** | Auto-ingest settings → brain; per-tenant vault isolation | low (post-S3) |
| **P1.5 mobile** | Lighthouse / responsive pass не делали | **P0 Product** |
| **P1.8 legal** | Privacy/terms для dlno.ru | ✅ ИП Рябов Д.В. (DaData) |
| **P1.9 clarity** | Нет результатов теста 3+ людей | **blocker P1 exit** |
| **E0.15 events** | ~~Operational event bus~~ | ✅ done |
| **E1.12 DaData** | Party lookup adapter + endpoint | ✅ |
| **E1.13–E1.15** | Lead enrich, site suggest, tenant legal | ⬜ |
| **delno-site-root** | Prod root `:18022` не пересобран последним deploy | P1 |
| **PR #20 merge** | draft + merge conflict с main | P1 |

---

## Что делать дальше (рекомендуемый порядок)

**Без DNS (можно сейчас):**

1. **P1.5 Mobile UX** — 🔄 code done; manual verify 375/390px ([`P1.5_MOBILE_PASS.md`](P1.5_MOBILE_PASS.md))
2. ~~**P1.8 Privacy/terms**~~ ✅ — ИП Рябов Д.В., реквизиты из DaData
3. **E1.4 Provenance** — unified API contract
4. **P1.9 Clarity test** — ⏸ deferred ([`P1.9_CLARITY_TEST.md`](P1.9_CLARITY_TEST.md))
5. **E1.13 Lead enrichment** — inn on leads + operator tool ([`E1.12_DADATA_PARTY_ENRICHMENT.md`](E1.12_DADATA_PARTY_ENRICHMENT.md))

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
# E0.14 / E1.11 formal exit
DELNO_API_URL=https://a.47z.ru/delno-api bash delno-api/deploy/smoke_formal_exit.sh

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
