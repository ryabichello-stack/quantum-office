# DELNO × Nous Hermes — единый план (продукт + изоляция + UI + порядок работ)

Дата: 2026-11-13 (МСК). Автор: Cursor.  
Статус: **канон внедрения** после уточнения владельца.  
Связано: [`PRODUCT_LOOP.md`](PRODUCT_LOOP.md) · [`HERMES_ORIGINAL_INTEGRATION_PLAN.md`](../HERMES_ORIGINAL_INTEGRATION_PLAN.md) (Codex, платформа) · `DELNO_OFFICE_OS_ARCHITECTURE.md`.

---

## 0. Да — полная картина процесса

Мы строим **не** «умный чат» и **не** только «изолированные контейнеры».  
Мы строим **мультитенантный офисный ИИ-сотрудник**:

```
Много компаний (tenant)
  └── у каждой СВОЯ изолированная среда
        ├── свой Hermes (Nous profile / runtime)
        ├── свой набор тулзов (grants + vault)
        ├── своя база знаний
        ├── своя память / skills / cron
        └── свой кабинетный UI-сеанс
```

**Что делает Гермес для владельца**

1. **Онбординг** — сам ведёт по подключению нужных инструментов.  
2. **Знания** — сам собирает и обогащает KB (сайт, каталог, текст, файлы; потом из работы).  
3. **Работа** — сам решает, как выполнить поручение: план → выбор тулзов → при необходимости `delegate_task` (субагенты) → прогресс в UI → результат / подтверждение.  
4. **Интерфейс** — современный, красивый, понятный: видно *что делает*, *что дальше*, *что нужно от человека*.

Движок рассуждения/субагентов/cron/memory = **оригинальный Nous Hermes**.  
DELNO = аккаунты, tenant-границы, vault, KB, approvals, биллинг, **UI**.

DIY `_try_cabinet_llm_tools` — временный fallback, не продукт.

---

## 1. Архитектура (одна схема)

```
┌─────────────────── Кабинет (delno-web) ───────────────────┐
│  Hermes UI: онбординг · план · шаги · confirm · KB · tools │
└──────────────────────────┬────────────────────────────────┘
                           │ JWT
┌──────────────────────────▼────────────────────────────────┐
│  DELNO API  — tenant auth, flags, vault, KB, approvals     │
│  bridge → /v1/hermes-nous/runs  + progress mirror           │
│  MCP gateway ← scoped run token (только grants этого run)  │
└─────────────┬───────────────────────────────┬─────────────┘
              │                               │
   ┌──────────▼──────────┐         ┌──────────▼──────────┐
   │ Runtime tenant A    │         │ Runtime tenant B    │
   │ Nous hermes-agent   │         │ Nous hermes-agent   │
   │ HERMES_HOME_A       │         │ HERMES_HOME_B       │
   │ MCP → DELNO (token) │         │ MCP → DELNO (token) │
   │ delegate_task/cron  │         │ delegate_task/cron  │
   └─────────────────────┘         └─────────────────────┘

Frontline (клиенты TG/телефон) читает KB; Owner Hermes строит и дирижирует.
Телефония Codex (trunk→tenant) — снаружи, не ломать.
```

**Изоляция (жёстко):** A не видит tools/list, KB, memory, cron, sessions B.  
Один общий Hermes на всех — запрещён.  
До доказательства MCP per-profile в multiplex — **отдельный runtime на компанию**.

---

## 2. Слои ответственности

| Слой | Кто | Что |
|------|-----|-----|
| UI | `delno-web` HermesStage+ | Онбординг-wizard, live plan/steps, confirm cards, KB preview, tool readiness |
| Control plane | DELNO API | JWT, flags, vault forms, KB CRUD, run mirror, approvals, billing |
| Brain | Nous Hermes | Планирование, субагенты, memory, skills, cron |
| Hands | DELNO MCP (scoped) | Реальные действия только с grant + probe |
| Voice/PSTN | Codex telephony | Last; не overwrite в этих этапах |

---

## 3. Продуктовый цикл (не меняется)

См. подробно [`PRODUCT_LOOP.md`](PRODUCT_LOOP.md).

Коротко: регистрация → Гермес ведёт setup → сайт/текст/каталог → KB → коннекторы по шагам → ready → поручения с субагентами → KB обогащается в работе.

**Преимущество перед конкурентами:** клиент не сам собирает интеграции и wiki — Гермес это делает *с ним* и потом *за него работает*.

---

## 4. UI — first-class требование

Не «потом причешем чат». Интерфейс = часть продукта.

### Must-have в кабинете Hermes

1. **Онбординг-поверхность** — чеклист готовности (KB / почта / TG / телефон…), следующий шаг одной кнопкой/формой, без «угадай команду».  
2. **Живой ход работы** — план → текущий шаг → следующий → ожидание подтверждения (уже задел `hermes_progress` / HermesStage — развивать, не ломать).  
3. **KB в контексте** — превью черновика после импорта сайта, diff «что добавим», confirm.  
4. **Тулзы** — статус каждого коннектора (не настроен / нужен секрет / живой / ошибка).  
5. **Поручения** — список задач/cron после того, как офис ready.  
6. **Современный вид** — единая визуальная система кабинета; мобильная читаемость; без перегруза карточками в hero-зоне чата; motion только для статуса шагов.

Техдолг UI: `HermesStage` сейчас завязан на DIY loop — перевести на Nous runs/events **без потери** progress UX от Codex.

---

## 5. Последовательность реализации (обязательный порядок)

Правило: **не прыгать к cron/голосу**, пока не работает онбординг+KB+один коннектор в UI на изолированном Nous.

### P0 — Платформа-минимум

- [x] Pin Nous (`v0.23.1`), skeleton `HERMES_HOME`, flag `hermes_nous_runtime`
- [x] Scoped run tokens + MCP filter
- [x] Bridge `/v1/hermes-nous/*`, DIY fallback
- [x] Isolation smoke script `hermes_runtime/scripts/isolation_smoke.sh`
- [ ] Live image build + A/B на staging (нужен docker+сеть; не блокирует API/UI)

### P1 — Продукт «первый вау»

- [x] Onboarding SOUL + skill в templates
- [x] Office loop API (`/office-loop`, kb-draft/confirm)
- [x] Tool pack `onboarding` (KB + web + setup)
- [x] UI: путь офиса + CTA в HermesStage panel
- [x] Lab image build + `/v1/models` A/B smoke on C4B (`/opt/delno/lab/hermes_runtime`, telephony untouched)
- [x] Lab `/v1/runs` returns `202` + `run_id`; wrong/cross-tenant API keys → `401`
- [ ] Live E2E site→KB→task with provider keys + flag on dogfood tenant

### P2 — Тулзы под дирижёра

- [x] Tool pack `conduct` (mail/calendar/crm/phones read+draft)
- [x] Cabinet soft-route uses conduct pack when Nous on
- [x] Confirm cards уже в UI (existing ConfirmCard / credential forms)
- [ ] Live `delegate_task` smoke against pinned image (needs provider keys)

### P3 — Постоянная работа

- [x] Migration `007_agent_tasks_runs_steps`
- [x] API tasks/runs/steps + bridge records AgentRun
- [x] UI panel «Поручения»
- [x] `lead.created` → durable AgentTask + queued AgentRun (`events_dispatch.on_lead_created`)
- [ ] Scheduler worker to drain queued runs against live Hermes (staging)

### P4 — Каналы клиентов и голос

- [x] `GET /channels-map` + `P4_CHANNELS.md`
- [ ] Full channel session binding polish
- [ ] Telephony last — Codex only

### P5 — Масштаб

- [x] `hermes_nous.run_started` meter event + `scale-notes` API + `P5_SCALE.md`
- [ ] Idle RSS measurement on real image
- [ ] Hardening evals suite

---

## 6. Что НЕ делаем в ближайших итерациях

- Не пишем свой оркестратор субагентов вместо Nous `delegate_task`.  
- Не включаем shared QO MCP с общими ключами.  
- Не деплоим unpinned `curl | bash` Hermes на prod.  
- Не трогаем Asterisk / AVA routing Codex.  
- Не делаем «красивый UI ради UI» без онбординг+KB пути.  
- Не ставим голос раньше P1–P2.

---

## 7. Критерии «готово показывать инвестору / первому клиенту»

1. Две компании изолированы.  
2. Новая компания: Гермес в UI проводит setup → KB с сайта → один канал.  
3. Поручение с видимым планом и субагентом (хотя бы research).  
4. Владелец понимает экран без инструкции «как пользоваться MCP».  
5. DIY loop выключен для dogfood tenant (flag on, runtime up).

---

## 8. Роли Cursor / Codex

| | Cursor | Codex |
|--|--------|-------|
| Сейчас | PRODUCT_LOOP + этот MASTER + Stage0 bridge/UI path | Telephony, hermes_progress coexistence, platform plan |
| Дальше | P1 onboarding+KB+UI на Nous; не overwrite phone | Дописать в свой plan § Product loop / MVP = P1; phone last |

Конфликт файлов: merge, не overwrite. Реестр: `AGENT_CHANGE_REGISTER.md`.

---

## 9. Источники правды

| Вопрос | Файл |
|--------|------|
| Зачем / цикл владельца | `PRODUCT_LOOP.md` |
| Порядок работ / UI / фазы | **этот файл** |
| Runtime, tokens, multiplex | `HERMES_ORIGINAL_INTEGRATION_PLAN.md` |
| Office OS (Hermes vs Frontline) | `DELNO_OFFICE_OS_ARCHITECTURE.md` |
| Что сделано на сервере | `AGENT_CHANGE_REGISTER.md` |
