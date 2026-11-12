# Рецензия: как посадить оригинальный Hermes в multi-tenant DELNO

Дата: 2026-11-13 (МСК). Автор: Cursor.  
Статус: архитектурная рецензия + целевая схема. **Код/prod telephony не менялись.**

## 0. Что удалось найти от Codex

| Артефакт | Где | Статус |
|----------|-----|--------|
| Запись реестра «план интеграции upstream Hermes» | `/opt/delno/docs/AGENT_CHANGE_REGISTER.md` (~00:52 МСК) | ✅ есть |
| Файл `HERMES_ORIGINAL_INTEGRATION_PLAN.md` | Codex: «локальный проект ChatGPT» | ❌ **на Cloud4Box / git пока нет** |
| `HERMES_AGENT_ARCHITECTURE.md` | Codex earlier | durable tasks/subagents **внутри DELNO** (контроль-plane) — не замена Nous |
| `HERMES_NOUS_INTEGRATION.md` | Cursor | направление «база = Nous» |

Ниже рецензирую **заявленное решение Codex из реестра** плюс официальные docs Nous; когда полный md появится на сервере — сверить побайтно с этим отзывом.

**Формулировка Codex (реестр):**  
> оригинальный NousResearch/hermes-agent как движок; DELNO сохраняет tenant/user auth, коннекторы, знания и аудит. На первом этапе отдельный runtime на tenant из-за ограничения upstream multiplex MCP discovery. Первые проверки: pinned upstream, изолированный прототип, scoped MCP, 2-tenant isolation tests, затем кабинет, задачи и каналы.

---

## 1. Вердикт: план Codex в целом **верен**

| Тезис Codex | Оценка | Почему |
|-------------|--------|--------|
| Движок = upstream Hermes, не DIY loop | ✅ **верно** | Иначе снова залипуха |
| DELNO = identity, connectors, KB, audit, billing | ✅ **верно** | Совпадает с `DELNO_OFFICE_OS_ARCHITECTURE.md` |
| Этап 1: **отдельный runtime на tenant** | ✅ **верно и обязательно** | Официально: в multiplex gateway **MCP discovery process-global** — «first profile to build an agent wins»; per-profile MCP registries ещё `#67605` ([Multiplexing Gateway Internals](https://hermes-agent.nousresearch.com/docs/developer-guide/multiplexing-gateway)) |
| Не ставить поверх prod без прототипа | ✅ | Согласовано с владельцем / telephony Codex |
| Isolation tests на 2 tenant до кабинета | ✅ | Минимальный bar |
| Дальше кабинет → задачи → каналы | ✅ по порядку | UI после доказанной изоляции |

**Что в реестре недосказано** (нужно дописать в полный план): как именно «свой набор tools / context / MCP / self-setup» живёт на диске; кто пишет `config.yaml`; как approvals стыкуются с DELNO; что делать с AVA/Frontline; экономика процессов.

`HERMES_AGENT_ARCHITECTURE.md` (agent_tasks/runs…) **не отменяется**, но меняет роль: это **DELNO control plane** (учёт поручений, биллинг, approvals, audit), а исполнение шагов — **Nous AIAgent** внутри tenant runtime, не второй самописный tool-loop.

---

## 2. Как устроен настоящий Hermes (релевантно multi-tenant)

Из официальной модели:

| Понятие Hermes | Смысл | Для DELNO |
|----------------|-------|-----------|
| **Profile** | Отдельный home: `config.yaml`, `.env`, `SOUL.md`, memory, sessions, skills, cron, MCP list | **1 tenant (или 1 owner-bot) → 1 profile home** |
| **Agent** | Бегущий процесс/сессия на profile | Runtime контейнер/systemd unit на tenant |
| **Subagent** (`delegate_task`) | Дочерний агент с **свежим** диалогом, не отдельный profile | Специалисты «почта/research» *внутри* того же tenant home |
| **Bot / gateway** | Messaging identity; токен бота **нельзя** шарить между profiles | Owner TG bot ≠ client TG; per-tenant credentials |
| **Context files** | `SOUL.md`, AGENTS.md, `.hermes.md`, project context | Онбординг пишет office context в home tenant |
| **MCP** | `mcp_servers` в config profile; discovery при старте | Office tools = MCP с **tenant-scoped** token |
| **Cron / skills / memory** | Уже в продукте | Не изобретать; изолировать home |

Критичный факт upstream (подтверждает Codex):

> MCP discovery and tool registration — **process-global**; first profile wins. Full per-profile MCP registries — issue `#67605`.

Значит: **нельзя** на этапе 1 посадить 50 tenants с разными MCP в один multiplex process и ждать изоляции каталога tools. Нужен **отдельный процесс (runtime) на tenant** (или на группу с *идентичным* MCP — почти никогда). Secrets/sessions в multiplex уже изолированы — но нам важны именно разные MCP/toolsets.

---

## 3. Целевая посадка: «у каждого свой Гермес»

```
                 ┌─────────────────────────────────────────┐
                 │  DELNO Platform                         │
                 │  auth · tenants · vault · KB · billing  │
                 │  telephony routing (Codex) · audit      │
                 │  office MCP gateway (tenant token)      │
                 └───────────────┬─────────────────────────┘
                                 │ issue scoped token + provision
         ┌───────────────────────┼───────────────────────┐
         ▼                       ▼                       ▼
 ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
 │ Runtime T1      │   │ Runtime T2      │   │ Runtime Tn      │
 │ hermes-agent    │   │ hermes-agent    │   │ hermes-agent    │
 │ HERMES_HOME=    │   │ HERMES_HOME=    │   │ …               │
 │ …/tenants/t1/   │   │ …/tenants/t2/   │   │                 │
 │   hermes/       │   │   hermes/       │   │                 │
 │ config+MCP+     │   │ config+MCP+     │   │                 │
 │ SOUL+memory+    │   │ SOUL+memory+    │   │                 │
 │ skills+cron     │   │ skills+cron     │   │                 │
 └────────┬────────┘   └────────┬────────┘   └────────┬────────┘
          │ API/ws              │                     │
          └─────────────────────┴─────────────────────┘
                                │
                    DELNO cabinet HermesStage
                    (bridge: tenant session → that runtime)
```

### 3.1. Содержимое home tenant (обязательный минимум)

Путь: `/opt/delno/data/tenants/<tenant_id>/hermes/` (= `HERMES_HOME`).

| Файл / каталог | Кто наполняет | Зачем |
|----------------|---------------|-------|
| `config.yaml` | Provisioner DELNO + правки агента | model, mcp_servers, delegation, tool filters |
| `.env` | Vault→env inject (**не** в git) | API keys, `DELNO_TENANT_TOKEN`, MCP secrets |
| `SOUL.md` | Шаблон DELNO + self-edit агента | личность «офисный сотрудник компании X» |
| `AGENTS.md` / `.hermes.md` | Онбординг из KB/сайта | контекст компании |
| `memories/` | Hermes learning loop | память только этого tenant |
| `skills/` | агент создаёт сам | процедурная память |
| `cron/` | агент / owner | расписания только этого офиса |
| `state.db` / sessions | Hermes | диалоги кабинета |

### 3.2. MCP / tools: не общий QO catalog

Один **DELNO Office MCP** (или несколько), но каждый runtime получает:

```yaml
mcp_servers:
  delno_office:
    url: "https://…/mcp"
    headers:
      Authorization: "Bearer ${DELNO_TENANT_TOKEN}"
```

Токен = tenant_id + scopes из `agent_connector_grants` / vault.  
Инструменты, на которые нет grant → MCP/API возвращает `not_authorized` (fail closed).  
Shared broker token «на всех» — **запрещён** (уже обожглись).

Встроенные Hermes tools (web/browser/delegate/cron) остаются; office write — только через scoped MCP + DELNO confirmation bridge.

### 3.3. Субагенты

Не отдельные tenants и не отдельные DELNO DIY workers:

- Owner: «собери 200 клиентов» → Hermes `delegate_task` batch **внутри** runtime T1  
- «Следи за почтой» → cron в **этом** home + mail tools из scoped MCP  
- Глубина/бюджет — caps в `config.yaml` delegation + DELNO spend limits

### 3.4. Self-setup («сам себя настраивал»)

Цепочка:

1. Tenant создан → DELNO provisioner клонирует template profile (`hermes profile create` / копирование skeleton).  
2. Пишет `.env` с model key (платформенный или BYOK) + tenant MCP token.  
3. Кабинет: «подключи почту» → credential form DELNO → grant → **переписывает** MCP scopes / optional skill.  
4. Hermes сам: `manage_connections` / skills / cron / SOUL — в рамках policy (что можно менять без approve).  
5. Health: DELNO периодически `hermes.capabilities`-эквивалент через bridge (reachable runtime + MCP ping).

«Сам работает» = cron + event hooks (DELNO webhooks → сообщение в session runtime), не HTTP chat на 120 секунд.

### 3.5. Кабинет UI

`HermesStage` → **thin client**:

- auth DELNO → выбирает runtime URL/socket tenant  
- стрим progress/tool events от Hermes  
- critical actions → DELNO ConfirmCard (если policy)  
- DIY `_try_cabinet_llm_tools` → fallback/onboarding only, потом выключить как primary

### 3.6. Frontline vs Owner Hermes

Как в Office OS: **два мозга**.

- **Owner Hermes** = Nous runtime (этот документ)  
- **Frontline** (клиент TG/телефон) = отдельный контур; может звать tools, но не обязан быть полным Hermes profile  
- Телефония Codex (`trunk_id`→tenant) остаётся в DELNO; Hermes owner **не** получает чужой DID

---

## 4. Где план Codex нужно усилить

1. **Файл плана на сервер/git** — сейчас только реестр; положить `HERMES_ORIGINAL_INTEGRATION_PLAN.md` в `/opt/delno/docs/` + repo.  
2. **Явная схема home path + provision API** — create/suspend/destroy runtime.  
3. **Process model** — systemd/docker one unit per active tenant; hibernate idle (Modal/Daytona optional later).  
4. **MCP isolation proof** — тест: tenant A MCP tool list ≠ tenant B; A token не видит B KB.  
5. **Approval bridge** — map Hermes dangerous/approval → DELNO `pending_confirmation`.  
6. **Billing** — meter tokens/tools per `tenant_id` из runtime usage.  
7. **Не путать** `HERMES_AGENT_ARCHITECTURE.md` stages 1–3 (DIY subagents) с Nous `delegate_task` — stage 1 durable tables ок; stage 3 «писать своих подагентов» — **нет**, звать upstream.  
8. **Multiplex later** — только когда `#67605` закроют *или* все tenants шарят один MCP shape (маловероятно).  
9. **Pin version** — commit/tag hermes-agent; не `install.sh | bash` на prod без pin.  
10. **Dogfood** — только `quantum-labs` runtime сначала.

---

## 5. Оценка «насколько верен» одним абзацем

Решение Codex (**Nous = engine, DELNO = multi-tenant control plane, phase-1 isolated runtime per tenant из‑за process-global MCP discovery**) — **архитектурно правильное** и подтверждается upstream docs. Неполнота сейчас: полный текст плана не на сервере; не расписаны provision/UI/approvals/billing/Frontline split. Документ `HERMES_AGENT_ARCHITECTURE.md` полезен как control-plane, опасен если его читать как «пишем свой оркестратор вместо Hermes». Cursor-курс (`HERMES_NOUS_INTEGRATION.md`) с этим согласован.

---

## 6. Рекомендуемый порядок (Cursor + Codex, без ссоры файлов)

1. Codex выкладывает полный `HERMES_ORIGINAL_INTEGRATION_PLAN.md` в `/opt/delno/docs` + git.  
2. Совместно зафиксировать pin hermes-agent + skeleton home.  
3. Staging: **один** runtime `quantum-labs`, smoke: chat + `delegate_task` + MCP ping scoped.  
4. Isolation: второй dummy tenant runtime, негативные тесты.  
5. Bridge кабинета.  
6. Только потом cron/owner channels; telephony не в этот PR.

Фильтр на каждое действие: *не вредит изоляции tenant и не overwrite AVA routing.*
