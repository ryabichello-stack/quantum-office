# Quantum Outreach — что уже сделано (as-is)

Документ для внешнего ревью и операторов.  
Связанный ориентир: [OUTREACH_ARCHITECTURE.md](./OUTREACH_ARCHITECTURE.md).

## Контекст

Внутренний **оркестратор B2B-касаний** Quantum Labs (ниша: ломбарды). Не ESP и не Sales Engagement Platform.

| Интеграция | Роль |
|------------|------|
| Bitrix24 | CRM, сделки, timeline |
| Mail.ru `office@` | SMTP + IMAP |
| DaData | ИНН → ФИО, адрес, TZ |
| AVA / телефония | Post-call → Bitrix |

**Объём:** ~1785 компаний, ~3121 контакт. **Лимит:** ~15 писем/день, один ящик.

**Прод:** `ava-outreach.service` `:8012`, UI через Quantum Console `?v=ops14`.

---

## Зрелость по слоям

| Слой | Статус | Содержание |
|------|--------|------------|
| **A** | ✅ | Локальные B2B-окна, geo KPI, колонка «Окно», настройки = движок |
| **B** | ✅ | Фильтры очереди, row actions, deferred hint, inbox badges |
| **C** | ✅ | Праздники РФ, OOO-pause, TZ fairness, auto-geo после sync |
| **D** | ✅ | Next actions + alerts, campaign collapse, CI pytest+sync |
| **E** | ✅ | Push notify (email/Telegram), step analytics, consent ledger |
| **F** | ✅ | Bulk queue, company card, on-call webhook, consent CSV |
| **F+** | ✅ | Server calendar API, consent export filters + legal hold |

---

## Движок отправки

- Outbox + **цепочки 5 шагов** (industry packs: дни 0 / 3 / 6 / 10 / 15) — intro → сценарии → …
- Play / Pause / Stop, warmup, jitter, domain/company caps
- **Локальные окна** получателя (10:00–11:30, 14:30–16:30, пн–пт, вт–чт preferred)
- Праздники РФ, fairness восток/запад (`rotate_daily`)
- Follow-up якорится от даты первого письма
- OOO / автоответ → **пауза** цепочки (`OOO_PAUSE_DAYS`), не стоп

---

## UI (6 вкладок)

**Кампания · Очередь · Входящие · Результат · Клиенты · Настройки**

Общее:
- KPI-полоска (очередь / сегодня / sent / opens / replies / Geo TZ / статус)
- **Алерты** (mailbox pause, IMAP, runner stopped)
- **Следующие действия** — приоритетная лента (входящие, callback, due follow-up)
- Старт / Пауза / Стоп в шапке

| Вкладка | Есть | Профи-уровень (ещё нет) |
|---------|------|-------------------------|
| **Кампания** | Pack, 5-step chain (collapse), брендинг, тест | Wizard, template versions, approval gate |
| **Очередь** | Due + первые, TZ/окно, фильтры, row actions, **bulk**, **14-day calendar API**, **company card** | Assignee |
| **Входящие** | Классификация, badges, «Готово», company card | Thread view, reply from UI, assignee |
| **Результат** | Воронка, по дням, последние, **step analytics API** | Cohort export, in-UI step funnel |
| **Клиенты** | Sync+geo+rebuild (auto-geo), city/TZ table, **company card**, **data quality** | Bulk geo repair |
| **Настройки** | Окна, праздники, fairness, OOO, anti-ban, **notify + on-call webhook** | Deliverability dashboard, DNS check |

### API оператора

- `GET /api/ops/summary` — alerts + next actions
- `GET /api/ops/health` — SMTP/IMAP/Bitrix/mailbox pause
- `GET /api/dashboard` — полная сводка
- `GET /api/modules/analytics/sequence-steps` — воронка по шагам цепочки
- `GET /api/modules/consent/ledger` — журнал DNC/consent

### Уведомления (Layer E)

**Quantum Panel** — общий канал оператору (email + @Quantum_panel_bot) для всего центра управления.  
Настройка: **Пульт Console** или Outreach → «Уведомления Quantum Panel».  
Сейчас события Outreach помечаются как `Quantum Panel · Outreach`; Console/звонки — через `POST /api/ops/notify` (`notify_panel_event()`).  
API: `POST /api/ops/notify`, `POST /api/ops/telegram/verify|discover|test|apply-branding`, статус в `GET /api/ops/health`.  
`apply-branding`: `include_profile_photo=false` при сохранении настроек; `true` — кнопка «Применить брендинг».

Статика: `outreach/static` → `console/static/outreach` (`?v=ops14`).

### Layer F ✅

- Company card, bulk queue, on-call webhook, consent CSV, data quality

### Layer F+ ✅

- **Календарь очереди** — `GET /api/modules/sequences/calendar?days=14` (МСК), UI во вкладке «Очередь»
- **Consent export** — `created_from` / `created_to`, `legal_hold` snapshot

---

## Что намеренно не делаем (lean)

- Smartlead / ESP-ферма / ротация From
- AI-классификация ответов
- PostgreSQL / Celery (пока SQLite хватает)
- RBAC (один UI-token)
- Click-tracking

---

## Риски и следующий приоритет

| Риск | Митигация сейчас | Следующий шаг |
|------|------------------|---------------|
| Репутация `office@` | Warmup, caps, pause | Отдельный sending domain при росте |
| Потеря ответов | IMAP + inbox + **push notify** | Telegram wizard в настройках |
| Compliance | Unsub, suppression, **consent ledger** | Экспорт / legal hold |
| Один email/компания | Архитектура outbox | Multi-contact targeting |

---

## Тесты и deploy

```bash
cd outreach && python -m pytest tests/ -q
bash scripts/sync-outreach-ui.sh
```

CI: `.github/workflows/outreach.yml`

Статика: `outreach/static` → `console/static/outreach` (обязательно синхронизировать).

---

## Принципы

1. Не ломать телефонию и prod-почту.
2. UI управляет тем же, чем движок (локальные окна, не «тихое» МСК).
3. Сделка в Bitrix — от **сигнала** (ответ / звонок), не от open.
4. Сначала репутация ящика, потом масштаб.
