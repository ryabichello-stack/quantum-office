# DELNO — документ для ChatGPT (entry point)

**Revision:** REV-3 · 2026-09-01  
**Repo:** [quantum-office](https://github.com/ryabichello-stack/quantum-office) · PR [#20](https://github.com/ryabichello-stack/quantum-office/pull/20)

Отправь ChatGPT **этот файл** и **оба** raw URL ниже.

---

## 0. Этот файл (entry point)

https://raw.githubusercontent.com/ryabichello-stack/quantum-office/main/docs/DELNO_FOR_CHATGPT.md

---

## 1. Master plan (стратегия + архитектура)

https://raw.githubusercontent.com/ryabichello-stack/quantum-office/main/docs/DELNO_MASTER_PLAN.md

Содержит: Product North Star, dual roadmap, Second Brain / ACL, monorepo strategy, guardrails, phases E0–E10, Sprint 0–3 status.

**Проверка версии:** строка `DELNO-MASTER-PLAN-REV-3` + секция `Rev.3 — Implementation Status`.

---

## 2. Implementation roadmap (checklist + статус)

https://raw.githubusercontent.com/ryabichello-stack/quantum-office/main/docs/DELNO_IMPLEMENTATION_ROADMAP.md

Содержит: что ✅ сделано (Sprint 0–2), что ⬜ дальше, API endpoints, Sprint 3.

---

## 3. Домены

https://raw.githubusercontent.com/ryabichello-stack/quantum-office/main/docs/DLNO_DOMAINS.md

---

## Промпт для ChatGPT

```
Прочитай три документа по raw URL (REV-3, 2026-09-01):
1. DELNO_FOR_CHATGPT.md — entry point
2. DELNO_MASTER_PLAN.md — стратегия
3. DELNO_IMPLEMENTATION_ROADMAP.md — статус и checklist

Подтверди revision REV-3. Дай feedback по Sprint 3 приоритетам.
Не предлагай CRM/marketplace/telephony до E3/E4.
```

---

## Краткий контекст (если не открывает URL)

- **DELNO** — multi-tenant SaaS «ИИ-сотрудник» (телефон, сайт, мессенджеры, KB, голос per tenant)
- **KB foundation:** Second Brain (`brain_platform`) — не писать с нуля
- **Prod:** `/opt/delno` на 5.35.86.62; staging https://a.47z.ru/delno/; prod domain https://dlno.ru (DNS pending)
- **Repo:** quantum-office monorepo (временно), потом delno-platform
- **Done (S0–S2):** delno-api, delno-knowledge, auth, CMS, public leads, channel router, admin/web scaffolds, prod stack
- **Next (S3):** Cloudflare DNS, site→api leads on prod rebuild, FAQ from CMS, brain init-db + ACL tests, Operator LLM

**Dev credentials (seeded):** `admin@delno.one` / `admin123456`, `owner@delno.one` / `demo123456`
