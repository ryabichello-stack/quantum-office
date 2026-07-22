# Quantum Outreach — что уже сделано (as-is)

Документ для внешнего ревью: описание текущего контура и просьба о идеях доработок.  
Связанный ориентир по архитектуре модулей: [ARCHITECTURE.md](./ARCHITECTURE.md).

## Контекст и позиционирование

Внутренняя система **Quantum Labs** для B2B-касаний по базе российских **ломбардов**. Не отдельный ESP и не SMTP-сервер: это **оркестратор** вокруг уже существующей инфраструктуры:

- CRM: **Bitrix24** (`b24-m5614z.bitrix24.ru`)
- Почта: **Mail.ru Business**, ящик `office@quantumlabs.ru` (тот же SMTP/IMAP, что у AVA-mailer)
- Телефония: **AVA** (Asterisk/Mango) → post-call в mailer → fan-out в outreach → Bitrix
- Обогащение: **DaData** по ИНН
- Хостинг: отдельный systemd-сервис `ava-outreach` на prod (`:8012`, UI `https://a.47z.ru/_ava_outreach/ui/`), **изолирован** от Asterisk/AVA docker/VPN — их не трогаем

**Сознательный выбор:** cold/outreach идёт с **стабильного From** (`office@`), без ротации плюс-адресов и без Smartlead/Instantly. Репутация ящика важнее «фермы доменов» на текущем объёме.

Объём базы (ориентир на момент написания): **~1785 компаний**, **~3121 контакт**, почти у всех есть ИНН и директор из DaData; отрасль в Bitrix выставлена **«Ломбарды»**.

---

## Стек

- Python + **FastAPI**
- UI: простой admin (HTML/JS), русскоязычный, token-auth
- Хранение: **SQLite** (`outbox.db`, `clients.db`, `modules.db`, `settings.db`)
- Модульная архитектура (`modules/*` + registry), чтобы наращивать фичи без связки с телефонией

Прод-путь кода: `/opt/ava-outreach`. Репозиторий: `extras/quantum-outreach/`.

---

## Что умеет система сегодня

### 1. База компаний и контактов

- Полный sync из Bitrix: компании/контакты со всеми полями (`*`, `UF_*`), EMAIL/PHONE/WEB/IM
- Реквизиты (ИНН, ОГРН и т.д.) → локальное зеркало `clients.db`
- UI «Клиенты»: просмотр, sync, rebuild очереди без онлайн-Bitrix
- **DaData:** lookup/enrich по ИНН → ФИО директора, адрес, ОКВЭД и др. → push обратно в Bitrix (реквизиты/директор)
- Массово проставлена отрасль **Ломбарды**

### 2. Кампания и отправка

- Одна очередь outbox + **sequence 3 шага** (день 0 / +3 / +7): intro → bump → route
- Управление: **Play / Pause / Stop**, kill-switch `OUTREACH_ENABLED` (по умолчанию выкл.)
- Лимиты: дневной ≤**15**, warmup 3→15, jitter 60–180 с
- **domain cap** 2/сутки + **company cap** 1 + cooldown 14д до второго контакта
- Atomic claim `pending→sending→sent` с Message-ID до SMTP
- После SMTP: **timeline на компании**, сделка **не** создаётся
- Сделка — от **ответа** / telephony qualify / вручную
- **Contact policy** AVA↔email: refuse/meeting → стоп sequence; reply → cooldown

### 3. Engagement / replies (P0+P1)

- Open pixel; bounce hard/soft/policy/auth + stop rules
- HTTPS unsubscribe + mailto
- Локальная verification (syntax/MX/role)
- Rule-based reply class + UI **Inbox** (необработанные) + Bitrix task на human/positive
- Домен: **`office@quantumlabs.ru`** с жёсткой защитой, без фермы

### 4. Ответы

- IMAP watcher каждые ~2 мин
- Сопоставление с outbox (From / Message-ID)
- UI «Ответы»
- Событие в Bitrix + notify на `office@`

### 5. Deliverability / anti-ban (базовый Control Center)

- Stable From (не ротируем)
- Warmup, domain cap, suppression (bounce / unsubscribe / manual)
- Kill-switch и дневной лимит
- UI вкладка Anti-ban

### 6. Телефония → CRM

После звонка AVA mailer шлёт structured lead в `POST /api/telephony/lead`:

- upsert **контакт** (телефон/email)
- upsert **компания** (отрасль Ломбарды)
- сделка `SOURCE=CALL` при квалификации (интерес / встреча / email / company / summary)
- комментарий в **timeline**
- идемпотентность по `call_id`

Каналы **звонок** и **email** сходятся в одном Bitrix.

### 7. Чего намеренно нет

- Нет Smartlead/Instantly и своей SMTP-фермы
- Нет multi-step sequences / A/B / сегмент-билдера
- Нет верификации email через внешний API
- Нет click-tracking и antibot
- Нет AI-классификации ответов
- Нет импорта реестра ЦБ с diff (источник правды сейчас Bitrix + DaData)
- Нет RBAC/ролей — один UI-token
- Нет PostgreSQL/Redis/Celery/Next.js — сознательно lean

---

## UI (вкладки)

Обзор · Отчёт · Клиенты · Очередь · Ответы · Письмо · Anti-ban · Расписание · Настройки

---

## Принципы, которыми уже руководствуемся

1. Не ломать телефонию и prod-почту ради outreach.
2. Не врать в UI про «доставлено во входящие» только по SMTP 2xx.
3. Bitrix — система продаж; outreach — касания + события.
4. Лид в CRM от **сигнала** (ответ / квалификация звонка), не от одного open.
5. Сначала репутация ящика и маленькие лимиты, потом масштаб.

---

## Просьба к ревьюеру

Ниже по смыслу ориентируемся на полное ТЗ «идеальной» cold-email платформы (event-driven, Smartlead, сегменты, Deliverability Center, AI replies и т.д.). Мы **не** планируем переписывать текущую систему в этот продукт целиком.

Нужны идеи в формате:

1. **Что добавить в наш lean-контур в ближайшие 1–2 итерации** (максимум пользы при минимальной сложности).
2. **Что из ТЗ имеет смысл позже**, когда вырастем с `office@` / упрёмся в репутацию.
3. **Что сознательно не делать** в нашей модели (свой SMTP + Bitrix + AVA).
4. Есть ли **дыры**, из-за которых мы сейчас теряем сделки или жжём ящик (bounce policy, sequences, классификация ответов, отдельные sending domains, verification и т.п.).

### Ограничения для идей

- объём базы ~2k ломбардов;
- один рабочий ящик `office@quantumlabs.ru`;
- Bitrix уже есть и наполнен;
- телефония AVA уже пишет лиды в Bitrix;
- стек FastAPI + SQLite + простой UI — менять можно только если выгода очевидна.

---

## Внутренний черновик приоритетов (не догма)

Уже обсуждали как разумный порядок внутри lean-контура:

1. Честные статусы + event timeline по письму  
2. Hard/soft bounce + auto-pause  
3. Задачи в Bitrix на positive reply  
4. Sequences 2–3 касания  
5. Классификация ответов  
6. Только потом — отдельный sending domain / внешний ESP, если объём вырастет  
