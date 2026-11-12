# Рецензия: `HERMES_ORIGINAL_INTEGRATION_PLAN.md` (Codex)

Дата рецензии: 2026-11-13 (МСК). Автор: Cursor.  
Объект: `/opt/delno/docs/HERMES_ORIGINAL_INTEGRATION_PLAN.md` (Codex, ~00:58 МСК, 117 строк).  
Статус: **согласовано с планом**; расхождения — уточнения, не блокер. Prod/telephony не трогались.

---

## Вердикт одной фразой

План Codex **архитектурно верен и достаточно глубок**, чтобы им пользоваться как каноном внедрения: Nous = engine, DELNO = multi-tenant control plane, сначала **отдельный runtime/home на компанию**, потом возможно уплотнение после A/B. Это именно то, что нужно для «у каждого свой Гермес».

---

## По разделам

| § | Тема | Оценка | Комментарий |
|---|------|--------|-------------|
| 1 | Upstream как движок; DIY loop = rollback | ✅ | Верно идентифицирует `agent.py` как не-Hermes |
| 2 | Изоляция tenant / user / agent / task / subagent | ✅ **сильно** | Правило «не отдавать всем профиль владельца» — критично (память на profile) |
| 3 | Отдельный runtime сначала; multiplex MCP contradiction | ✅ | Docs действительно противоречат (user guide vs internals `#67605`); Codex правильно требует proof, не веру |
| 3 | Не gateway на каждого *user* | ✅ | Экономика + общий office-контекст компании |
| 4 | JWT → scoped capability token per run; vault; approvals API | ✅ **обязательно** | Без этого MCP снова «на абу» |
| 4 | Запрет terminal к `/opt/delno` / чужим homes | ✅ | Sandbox allowlist |
| 5 | KB в DELNO; Hermes memory ≠ source of truth | ✅ | Иначе CRM/KB разъедутся |
| 5 | Слоистый контекст + поиск, не dump всей KB | ✅ | Оптимальность токенов |
| 6 | Cron зеркало в `agent_tasks`; events через DELNO; durable ≠ live delegate | ✅ | Upstream: `delegate_task` привязан к родительской сессии — долгое = этапы DELNO |
| 6 | Постоянный спец-агент = profile, не subagent | ✅ | Совпадает с моделью Nous Profiles/Bots |
| 7 | UI → DELNO → Hermes `/v1/runs` + progress в БД | ✅ | Thin client; наблюдаемые шаги, не CoT |
| 8 | Этапы 0→6 | ✅ | Порядок правильный: prototype → isolation → MCP → cabinet → tasks → voice last |
| 9 | Open questions (token per run, resume, process-global tools, scale) | ✅ | Честный research gate |
| 10 | 8 vCPU / 15 GiB: 100 tenants ≠ 100 gateways | ✅ | Сценарный расчёт корректен как warning |
| 11 | MVP: 2 компании, cron заявок, изоляция A↛B | ✅ | Хороший dogfood bar |

---

## Что усилить / зафиксировать рядом (не опровергает план)

1. **Pin commit/tag** hermes-agent в этапе 0 — явно в CI/image digest (в плане есть, держать железным).  
2. **Self-setup онбординг** (§8.3) — ок; добавить: кто пишет skeleton `SOUL.md`/`config.yaml` (DELNO provisioner), что агенту **можно** менять самому (skills/cron/SOUL), что **нельзя** (MCP URL, vault, egress).  
3. **Frontline vs Owner** — план голос/каналы (§8.5) правильный «последним»; явно назвать, что inbound AVA/`trunk_id` (Codex telephony) **не** переписывается этим планом и не живёт внутри Hermes run.  
4. **Billing meters** — упомянуть привязку usage к `tenant_id/agent_id/run_id` (логично из §4 token).  
5. **Feature flag** cabinet switch (§8.3) — сохранить до green isolation tests.  
6. Когда Codex/Cursor выложат image — не `curl | bash` на prod.

Ни одно из усилений не меняет выбранную ось плана.

---

## Согласованность с соседними docs

| Документ | Отношение |
|----------|-----------|
| `HERMES_AGENT_ARCHITECTURE.md` | Control plane (`agent_tasks/runs/…`) — **вкладывается** в §§6–7 плана; не конкурирует с Nous |
| `HERMES_NOUS_INTEGRATION.md` (Cursor) | Согласован по направлению |
| `DELNO_OFFICE_OS_ARCHITECTURE.md` | Hermes Supervisor = Owner Nous runtime; Frontline отдельно — план это уважает |
| Telephony / `AGENT_CHANGE_REGISTER` stop-rules | План не трогает Asterisk; этап 5 явно last |

---

## Практическое правило для Cursor и Codex

Реализуем **этот** файл как source of truth интеграции.  
Любой PR: (1) не ломает tenant isolation A/B, (2) не выдаёт shared MCP key, (3) не overwrite telephony, (4) cabinet → только через DELNO backend.
