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

**Прод:** `ava-outreach.service` `:8012`, UI через Quantum Console `?v=ops4`.

---

## Зрелость по слоям

| Слой | Статус | Содержание |
|------|--------|------------|
| **A** | ✅ | Локальные B2B-окна, geo KPI, колонка «Окно», настройки = движок |
| **B** | ✅ | Фильтры очереди, row actions, deferred hint, inbox badges |
| **C** | ✅ | Праздники РФ, OOO-pause, TZ fairness, auto-geo после sync |
| **D** | ✅ | Next actions + alerts, campaign collapse, CI pytest+sync |
| **E+** | 🔲 | RBAC, multi-campaign, step analytics, отдельный sending domain |

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
| **Очередь** | Due + первые, TZ/окно, фильтры, row actions | Bulk, calendar view, company drill-down |
| **Входящие** | Классификация, badges, «Готово» | Thread view, reply from UI, assignee |
| **Результат** | Воронка, по дням, последние | Step conversion, cohort, export |
| **Клиенты** | Sync+geo+rebuild (auto-geo), city/TZ table | Company card, data quality score |
| **Настройки** | Окна, праздники, fairness, OOO, anti-ban | Deliverability dashboard, DNS check |

### API оператора

- `GET /api/ops/summary` — alerts + next actions
- `GET /api/ops/health` — SMTP/IMAP/Bitrix/mailbox pause
- `GET /api/dashboard` — полная сводка

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
| Потеря ответов | IMAP watcher + inbox UI | Push-уведомления (email/Telegram) |
| Compliance | Unsub, suppression, 152‑ФЗ footer | Consent ledger per contact |
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
