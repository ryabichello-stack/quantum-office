# План интеграции оригинального Hermes (Nous) в DELNO

> **Происхождение:** решение и тезисы — Codex (запись в `AGENT_CHANGE_REGISTER.md`, 2026-11-13).  
> Полный текст из ChatGPT-проекта Codex на сервер ещё не был скопирован; этот файл **реконструирован и расширен** Cursor по реестру + официальным docs Nous + рецензии `HERMES_ORIGINAL_INTEGRATION_REVIEW.md`.  
> Когда Codex выложит свой канонический md — слить/заменить, не плодить два source of truth.

**Статус:** архитектурный план. Production API / telephony не менять этим документом.

---

## Решение

1. **Движок агента** = upstream [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) (субагенты, cron, memory, skills, MCP, context files, profiles).  
2. **Платформа** = DELNO: tenant/user auth, vault/connectors, knowledge, audit, billing, cabinet UI, telephony routing.  
3. **Этап 1 runtime:** **отдельный процесс Hermes на tenant** (отдельный `HERMES_HOME`). Причина: в multiplex gateway MCP discovery/tool registration ещё **process-global** (upstream `#67605`); разные MCP-каталоги на tenants в одном процессе небезопасны.  
4. Один общий Hermes на всех клиентов — **запрещён**.

---

## Модель изоляции

| Слой | Механизм |
|------|----------|
| Данные / config / memory / skills / cron | `HERMES_HOME=/opt/delno/data/tenants/<tenant_id>/hermes/` |
| Office tools | MCP `delno_office` + `Authorization: Bearer <tenant-scoped token>` |
| Context | `SOUL.md`, `AGENTS.md`, KB-снимки в home; только этот tenant |
| Субагенты | Hermes `delegate_task` внутри того же home (не чужой tenant) |
| Owner messaging | Отдельные bot tokens на profile; не клонировать channels между tenants |
| Телефония | Остаётся DELNO/`trunk_id` (Codex); Hermes не обходит маршрутизацию |

---

## Фазы проверки (Codex) + уточнения

1. **Pin** версии hermes-agent (tag/commit), не floating install.  
2. **Изолированный прототип** runtime вне overwrite `/opt/delno/api`.  
3. **Scoped MCP** — token видит только grants своего tenant.  
4. **2-tenant isolation tests** — memory, sessions, MCP tool list, KB read.  
5. Затем **кабинет bridge**, durable task accounting (см. `HERMES_AGENT_ARCHITECTURE.md` как control plane), owner-каналы.

Self-setup: provisioner создаёт home → inject `.env`/MCP → агент донастраивает skills/cron/SOUL в рамках policy; коннекторы — через DELNO credential forms → refresh grants.

---

## Связанные документы

- Рецензия Cursor: `HERMES_ORIGINAL_INTEGRATION_REVIEW.md`  
- Направление: `HERMES_NOUS_INTEGRATION.md`  
- Control plane (tasks/approvals): `HERMES_AGENT_ARCHITECTURE.md`  
- Office OS: `DELNO_OFFICE_OS_ARCHITECTURE.md`  
- Реестр: `AGENT_CHANGE_REGISTER.md`
