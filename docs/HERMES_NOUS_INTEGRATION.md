# ИСПРАВЛЕНИЕ: база — Nous Research Hermes Agent, не самописный цикл DELNO

Дата: 2026-11-13 (МСК). Автор: Cursor.  
Статус: **коррекция ошибки**. Runtime / telephony Codex не трогаем.

## В чём была ошибка Cursor

Владелец имел в виду **оригинальный [Hermes Agent (Nous Research)](https://hermes-agent.nousresearch.com/docs)** — MIT, субагенты (`delegate_task`), cron, memory/skills, MCP, gateway, 70+ tools.

Cursor (и часть предыдущих выводов) работал с **омонимом**: брендом UI/цикла в DELNO (`HermesStage`, `_try_cabinet_llm_tools` в `agent.py`) — самописный sync loop «модель → tool → ответ» **без** Nous runtime.

Документ `docs/HERMES_AGENT_ARCHITECTURE_ANALYSIS.md` описывал, *как изобрести* задачи/субагентов с нуля. Это **неверный порядок**. Сначала — взять готовый Hermes Agent и встроить в multi-tenant DELNO. Самописная «залипуха» не заменяет продукт уровня Nous.

Codex уже зафиксировал на проде: `/opt/delno/docs/HERMES_AGENT_ARCHITECTURE.md` (durable tasks) и отдельно признал, что **Nous hermes-agent на сервере не установлен**.

## Факт-чек Cloud4Box (read-only)

| Проверка | Результат |
|----------|-----------|
| `NousResearch/hermes-agent` clone / install | **Нет** |
| Процесс `hermes` / gateway / docker image | **Нет** |
| Код с именем Hermes | Только DELNO: `HermesStage`, `agent.py`, `hermes_progress`, tests |
| Что умеет UI сейчас | Свой cabinet loop (~34 tools) + progress Codex |

Поэтому кабинет «тупой»: он бьёт в **подделку цикла**, а не в Hermes Agent.

## Что уже есть у настоящего Hermes (не изобретать)

Источник: официальные docs / architecture / delegation / cron.

- **AIAgent loop** — полноценный агент, не phrase-router  
- **`delegate_task`** — изолированные субагенты, parallel batch (до N concurrent)  
- **Cron** — `cronjob_manage`, natural language schedules, delivery на платформы  
- **Memory + Skills** — learning loop, agentskills.io  
- **MCP** — подключение внешних tool servers  
- **Web/browser/terminal** — нормальный toolset (не DDG≤10 как единственный research)  
- **Profiles** — `hermes -p <name>` → отдельный `HERMES_HOME`, config, memory, sessions, gateway PID  
- **Gateway** — Telegram/Discord/… (у DELNO свои каналы — стыковать осторожно)  
- **API server / library entry** — точки для встраивания в продукт

## Правильный порядок работ (заменяет «пишем субагентов в DELNO»)

### 0. Стоп самописного оркестратора как «решения»

Не выдавать `agent_tasks` / DIY workers за обязательный путь, пока не оценена посадка **настоящего** Hermes. Durable tables DELNO могут понадобиться как **обёртка multi-tenant** (учёт, billing, approvals), но ядро агента — Nous.

### 1. Изучение исходников (без выкатки в prod telephony)

- Repo: https://github.com/NousResearch/hermes-agent  
- Docs: https://hermes-agent.nousresearch.com/docs  
- Ключевые точки: `run_agent.py` / `agent/conversation_loop.py`, `tools/delegate_tool.py`, `cron/`, `tools/mcp_tool.py`, profile/`HERMES_HOME`, gateway API server  
- Lab install на **отдельной** машине/VM или staging path (не затирать `/opt/delno/api` и Asterisk)

### 2. Модель встраивания в DELNO (multi-tenant)

**Запрещено:** один общий Hermes-процесс с общими tools/creds на всех клиентов.

**Целевой паттерн:**

```
DELNO cabinet (HermesStage)
    → auth TenantContext
    → delno-hermes-gateway (тонкий слой)
         → per-tenant Hermes profile
              HERMES_HOME=/opt/delno/data/tenants/<tenant_id>/hermes/
              config: model, MCP, tool allowlist, spend limits
              memory/skills/sessions изолированы
         → optional: hermes -p tenant_<slug> gateway
```

Стыковка:

| DELNO | Hermes Nous |
|-------|-------------|
| Tenant login / cabinet chat | Profile + session keyed by tenant_id |
| `credentials.open_form` / vault | Env/credential passthrough **только** этого profile |
| Tenant-safe office MCP (когда будет) | `mcp_servers` в config profile |
| `critical_write` confirm cards | Hermes approval + DELNO approval bridge |
| Billing | Meter Hermes usage per tenant |
| AVA telephony routing (Codex) | **Не смешивать** в один sandbox без tenant DID grants; phone tools только через DELNO adapters |

Profiles в Hermes уже дают изоляцию home/config/memory — это естественный рычаг multi-tenant, не «один бот на всех».

### 3. UI

`HermesStage` должен стать **клиентом** к настоящему агенту (stream progress, tool events, artifacts), а не хостом самописного `_try_cabinet_llm_tools` как единственного мозга. Старый loop можно оставить fallback/onboarding до cutover.

### 4. Что не делать

- Не деплоить Cursor-ветки с «улучшенным DIY loop» как замену Nous  
- Не включать shared QO MCP в общий процесс  
- Не трогать Codex telephony/`trunk_id`  
- Не ставить один `hermes gateway` с доступом ко всем tenant data  

## Связь с предыдущими документами

| Документ | Статус |
|----------|--------|
| `HERMES_AGENT_ARCHITECTURE_ANALYSIS.md` | **Устарел как стратегия** — описывал DIY. Оставляем как аудит *текущей* залипухи DELNO; roadmap субагентов с нуля — отвергнут. |
| `/opt/delno/docs/HERMES_AGENT_ARCHITECTURE.md` (Codex) | Полезен как **DELNO control plane** (tasks/runs/approvals/tenant grants), но ядро исполнения → Nous Hermes, не reinvent. |
| Этот файл | **Source of truth** по направлению интеграции |

## Следующий конкретный шаг (после ОКнения владельца)

1. Staging: установить Hermes Agent (CLI) на изолированный path Cloud4Box **вне** overwrite api, один profile `quantum-labs` smoke (web research + delegate_task).  
2. Спроектировать `delno-hermes-bridge`: cabinet message → Hermes session этого tenant.  
3. Только потом — cutover UI и отключение DIY loop как primary.

До шага 1 Cursor **не** пилит самописные subagents «чтобы было как у больших».
