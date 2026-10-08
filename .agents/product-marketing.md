# DELNO — Product Marketing Context

**Status:** Living document · facts from repo/KB only · **UNKNOWN** = needs validation  
**Last updated:** 2026-10-08  
**Canonical for marketing skills:** this file (legacy alias: `product-marketing-context.md`)

---

## Product

**DELNO** — multi-tenant SaaS: ИИ-сотрудник первой линии для малого и среднего бизнеса. Единая база знаний для сайта, мессенджеров, почты и (в расширенном тарифе) телефона.

**Not in scope for marketing claims without qualification:** self-service PSTN для любого оператора; полная замена CRM; гарантия % автономных решений.

---

## ICP (primary)

| Segment | Signals | Jobs To Be Done |
|--------|---------|-----------------|
| Малый сервисный бизнес (клиники, салоны, автосервис, B2C услуги) | Много входящих в чат/мессенджеры/звонки; нанимают администраторов | Не терять обращения; ответить 24/7; записать клиента |
| Специалист / микробизнес | Один канал (сайт или Telegram) | Быстро отвечать без найма |

**Secondary ICP:** UNKNOWN — validate with sales calls.

---

## Pain points (validated in copy/KB)

- Клиенты пишут и звонят — не успевают отвечать.
- Разные боты/каналы без общего контекста.
- Страх «бот придумает ответ» → DELNO передаёт человеку с контекстом.

---

## Desired outcomes

- Первый сценарий в проде за несколько дней (зависит от KB и интеграций — не обещать «за час» без scope).
- Меньше рутины на первой линии; сохранение записи/заявки/итога разговора.

---

## Alternatives / competitors

**UNKNOWN** — formal competitor list and battle cards not in repo.  
Informal alternatives: отдельные чат-боты, колл-центр, администратор, Jivo + CRM, Mango без ИИ.

---

## Differentiation (supportable)

- Одна база знаний и история для всех каналов.
- Голос + текст на сайте (виджет); демо на лендинге.
- Прозрачные пакеты: **300 ИИ-диалогов/мес**, **30 мин** голоса в виджете, **100 мин** PSTN на тарифе 5 990 ₽.

---

## Positioning

**Canonical landing (`/`):** «Клиенты пишут и звонят. DELNO отвечает.» (owner-approved v2 — see `docs/P1.1_SITE_LANDING.md`).

**Experimental:** `/v4` not default; `/v2` conversion variant in development.

---

## Value propositions

1. Единое окно обращений вместо пяти отдельных ботов.
2. Ответы из ваших документов и правил, не «из головы модели».
3. Начать с одного канала, расширять без смены продукта.

---

## Proof

- Голосовое демо на сайте (dlno.ru / staging `/delno/`).
- Публичные тарифы и лимиты в KB (`delno-knowledge/vault/delno-demo/public/pricing.md`).
- **Case studies / logos:** UNKNOWN.

---

## Objections

| Objection | Response direction |
|-----------|-------------------|
| «Заменит ли людей?» | Первая линия + передача сложного человеку |
| «Подключится ли мой номер?» | SIP/переадресация/Mango — техническая проверка |
| «Сколько стоит сверх пакета?» | Минуты/массовые отправки по факту |

---

## Offers

- **Диалоги** — 2 990 ₽/мес (без PSTN).
- **Диалоги + звонки** — 5 990 ₽/мес (+ 100 мин телефонии).
- **Компания** — индивидуально.
- **Primary CTA:** голосовое демо / заявка на демо на вашем бизнесе.

---

## Pricing (public)

See KB pricing.md — do not invent tiers or limits.

---

## Brand voice

- Русский, деловой, конкретный.
- «Отвечает дельно. Работает по делу.»
- Избегать: «революционный», «бесшовный», «инновационный» без доказательства.

---

## Claims we CAN make

- 300 ИИ-диалогов, 30 мин виджет-голос, 100 мин PSTN (тариф 5 990).
- 24/7 на подключённых каналах.
- Единая KB для каналов.

---

## Claims we CANNOT make (without new proof)

- Guaranteed ROI or % automation.
- «Работает с любым оператором из коробки» for PSTN.
- Awwards-level performance SLAs.

---

## Conversions

| Priority | Action |
|----------|--------|
| Primary | Lead form / «Получить дemo» / голос `#demo` |
| Secondary | Telegram, MAX, 8 800, email |

---

## Analytics

**UNKNOWN** — GA4/event map not documented in repo. Use `analytics` skill when instrumenting.
