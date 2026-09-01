# DELNO — единая точка входа для ChatGPT

**Revision:** REV-3.1 · 2026-09-01

---

## Что отправлять ChatGPT

**Одна ссылка — только эту:**

https://raw.githubusercontent.com/ryabichello-stack/quantum-office/main/docs/DELNO_FOR_CHATGPT.md

Мастер-план, роудмап и домены **отдельно не отправляй** — они перечислены ниже, ChatGPT сам откроет по raw URL.

---

## Промпт (скопируй целиком)

```
Прочитай entry point и все связанные документы по raw URL из него (REV-3):

https://raw.githubusercontent.com/ryabichello-stack/quantum-office/main/docs/DELNO_FOR_CHATGPT.md

Открой каждый raw URL из секции «Карта документов».
Подтверди revision REV-3.
Дай feedback по Sprint 3 приоритетам.
Не предлагай CRM / marketplace / telephony до E3/E4.
```

---

## Карта документов

| # | Документ | Зачем | Raw URL |
|---|----------|-------|---------|
| 1 | **Этот файл** | Точка входа, промпт, краткий контекст | https://raw.githubusercontent.com/ryabichello-stack/quantum-office/main/docs/DELNO_FOR_CHATGPT.md |
| 2 | **Master plan** | Стратегия, архитектура, guardrails, E0–E10 | https://raw.githubusercontent.com/ryabichello-stack/quantum-office/main/docs/DELNO_MASTER_PLAN.md |
| 3 | **Roadmap** | Checklist, что ✅ сделано, Sprint 3, API endpoints | https://raw.githubusercontent.com/ryabichello-stack/quantum-office/main/docs/DELNO_IMPLEMENTATION_ROADMAP.md |
| 4 | **Domains** | dlno.ru, DNS, nginx (справочно) | https://raw.githubusercontent.com/ryabichello-stack/quantum-office/main/docs/DLNO_DOMAINS.md |

**Проверка версии master plan:** строка `DELNO-MASTER-PLAN-REV-3` + секция `Rev.3 — Implementation Status`.

---

## Краткий контекст

- **DELNO** — multi-tenant SaaS «ИИ-сотрудник» (телефон, сайт, мессенджеры, KB, голос per tenant)
- **KB foundation:** Second Brain (`brain_platform`) — не писать с нуля
- **Prod:** `/opt/delno` на 5.35.86.62; staging https://a.47z.ru/delno/; prod https://dlno.ru (DNS pending)
- **Repo:** quantum-office monorepo (временно) → потом delno-platform · PR [#20](https://github.com/ryabichello-stack/quantum-office/pull/20)
- **Done (S0–S2):** delno-api, delno-knowledge, auth, CMS, public leads, channel router, admin/web scaffolds, prod stack
- **Next (S3):** P0 isolation+ACL → brain init → leads→PG → DNS → P1 website exit → FAQ CMS → basic Operator (read-only)

**Dev credentials (seeded):** `admin@delno.one` / `admin123456`, `owner@delno.one` / `demo123456`
