# DELNO — MASTER KNOWLEDGE BASE FOR CURSOR
Версия: 2026-09-01

## 0. Суть проекта
DELNO — multi-tenant SaaS с ИИ-сотрудником для бизнеса.

Ключевой тезис: **«Не пять отдельных ботов. Один ИИ-сотрудник.»**

Текущая точка входа — автоматизация первой линии: сайт, телефон, Telegram, MAX, email. ИИ-сотрудник отвечает, консультирует, принимает заявки, записывает, квалифицирует и передаёт человеку, работая по базе знаний компании.

Долгосрочно DELNO развивается в **AI Operating Layer / Business OS для SMB**: предприниматель говорит, что нужно сделать, а DELNO через инструменты управляет коммуникациями, CRM, booking, маркетингом, автоматизациями и подключёнными сервисами.

## 1. Текущее позиционирование
Главный оффер: **«Ваш новый ИИ-сотрудник»**.

Что он делает:
- отвечает клиентам на сайте;
- принимает и совершает звонки;
- отвечает в Telegram;
- отвечает в MAX;
- отвечает по email;
- знает услуги, цены, FAQ и правила компании;
- консультирует;
- принимает заявки;
- записывает клиентов;
- работает 24/7.

Роли, которыми можно объяснять продукт: секретарь, администратор, оператор, консультант, менеджер первой линии.

Не позиционировать как «ещё один чат-бот», «конструктор ботов» или «CRM 2.0» на текущем этапе.

## 2. Текущий milestone — Phase 1: сайт
Главный приоритет сейчас — закончить продающий сайт.

Текущая версия: https://delno-site.indigo-ant-8325.chatgpt.site/v4
Основной домен бренда: **dlno.ru**.

Критерий готовности: незнакомый с DELNO человек за 5–10 секунд должен понять:
1. DELNO — ИИ-сотрудник для бизнеса.
2. Он отвечает клиентам вместо человека.
3. Работает по телефону, на сайте и в мессенджерах.
4. Консультирует, принимает заявки и записывает.
5. Можно начать с одного канала.
6. Понятно, как попробовать продукт.

## 3. Визуальная стратегия сайта
Сайт должен выглядеть как продуктовая компания мирового уровня, а не generic SaaS landing.

Визуальный характер: точность Linear + глубина Stripe + ясность Apple + живость современного AI-продукта, без буквального копирования.

Ключевые решения:
- фирменный DELNO orb / ядро как главный визуальный объект;
- premium channel chips: логотип/иконка + подпись;
- активный канал — мягкий glow;
- Hero как продуктовая сцена «канал → DELNO → действие → результат»;
- меньше декоративных pills;
- больше воздуха и крупной типографики;
- asymmetric bento grid для capabilities;
- restrained motion storytelling;
- единые design tokens: radius, border, glow, shadow, spacing, motion.

Каналы: Сайт, Звонки, Telegram, MAX, Почта.

## 4. Критичные UX-правки сайта
Lead modal должна открываться строго по центру viewport, с overlay/backdrop blur, body scroll lock, adaptive width, корректным mobile UX, Escape-close и focus trap.

Lead form не должна открывать mail client. Должна отправлять данные в backend/CRM/DB.

Поля: имя, телефон, email, сайт компании (optional).

Будущий flow: lead submitted → DELNO backend → automatic follow-up → AI call/message.

## 5. Тарифы
### Диалоги — 2 990 ₽/мес
- 300 ИИ-диалогов;
- база знаний;
- Telegram;
- MAX;
- другие поддерживаемые мессенджеры;
- голосовой виджет на сайт;
- 30 минут голосового общения.

### Звонки — 5 990 ₽/мес
Всё из «Диалогов» плюс:
- 100 минут голосовых разговоров;
- входящие телефонные звонки;
- исходящие звонки;
- передача человеку.

Expansion revenue: overage минут/диалогов, дополнительные номера, дополнительные ИИ-сотрудники, CRM, booking, automations, integrations, industry packs, marketplace commissions.

## 6. Репозитории и кодовая база
Есть существующий проект **Quantum Office**. В нём уже реализованы: IP-телефония, входящие/исходящие звонки, автодозвон, голосовой бот, Telegram, MAX, email, база знаний, ИИ-логика и сопутствующий backend/API.

Целевая структура:
```
workspace/
├── quantum-office/
└── delno-platform/
```

Правила:
- quantum-office = reference/read-only;
- delno-platform = новый самостоятельный коммерческий SaaS;
- не коммитить изменения DELNO в Quantum Office;
- переиспользовать идеи/адаптеры/паттерны, но не создавать жёсткую зависимость;
- DELNO должен отдельно build/deploy/run.

## 7. Целевая архитектура
Принцип: **API-first multi-tenant SaaS**.

На старте — **Modular Monolith**, не микросервисы.

Основные ядра:
- Tenant Core
- Auth / RBAC
- AI Core
- Communication Core
- Knowledge Core
- Automation Core
- Billing / Usage
- Analytics
- Partner / Growth
- Supervisor / Operations

Рекомендуемый контур: backend API, PostgreSQL, migrations, Redis/workers по необходимости, pgvector/vector storage, Docker, versioned REST API, OpenAPI, webhooks, background jobs.

## 8. Multi-tenant модель
Базовые сущности: Tenant, User, Role, Permission, Contact, Company, Lead, Deal, Conversation, Message, Call, Channel, ChannelAccount, Campaign, Automation, AutomationRun, KnowledgeBase, KnowledgeDocument, AI Agent, AgentPrompt, AgentTool, Task, Event, Integration, Webhook, Usage, Subscription, AuditLog.

Минимальные роли: platform_admin, tenant_owner, tenant_admin, manager, operator, viewer.

## 9. Tenant isolation — критично
Никакого смешивания данных компаний.

Каждый tenant имеет свои knowledge, settings, channels, conversations, memory, credentials, analytics и users.

Ключевое правило: **LLM никогда не выбирает tenant_id и не передаёт произвольный tenant_id в tool.**

Плохо: `get_knowledge(tenant_id=123)`.
Правильно: `get_knowledge()` — tenant берётся backend из authenticated context.

Дополнительно: tenant-scoped DB queries, желательно PostgreSQL RLS, encrypted secrets, AuditLog, signed webhooks, rate limiting, request IDs, cross-tenant isolation tests.

## 10. Unified Conversation Model
Телефон, Telegram, MAX, email и web-chat должны сводиться к общей модели Conversation/Message.

Нужны channel adapters, а не разрозненная бизнес-логика.

Communication Core должен поддерживать общие операции: receive_message, send_message, start_call, receive_call_event, transfer_to_human, attach_contact, update_conversation_state.

## 11. Tenant AI Operator
Центральный UX личного кабинета.

Пользователь говорит: «По субботам теперь работаем до 16:00», «Подключи Telegram», «Почему MAX не отвечает?», «Добавь услугу», «Если спрашивают про опт — передавай Александру».

Оператор не кликает UI мышью — он вызывает backend tools.

Cursor/Codex = dev tools. Tenant Operator = runtime agent DELNO.

## 12. Tool API для Tenant Operator
Минимально:
- get_account_status
- get_company_profile / update_company_profile
- get_working_hours / update_working_hours
- get_knowledge_status
- import_knowledge_from_url
- add_knowledge_item / update_knowledge_item
- get_integrations
- connect_telegram / test_telegram
- connect_max / test_max
- connect_email / test_email
- get_telephony_status / test_call
- get_usage
- create_automation / update_automation
- diagnose_problem

Позже: create_pipeline, create_booking, create_campaign, launch_followup, recommend_partner_service, request_human_approval.

## 13. Scope Guard
Tenant Operator не должен быть бесплатным универсальным ChatGPT.

В scope: DELNO, настройки, компания клиента, база знаний, каналы, workflows, adjacent domain best practices, необходимые для работы бизнеса.

Out of scope: случайные бытовые/энциклопедические/учебные запросы, unrelated creative work.

Три уровня: system policy → cheap classifier IN_SCOPE/OUT_OF_SCOPE → limited tools.

## 14. Confirmation + Audit
Read/diagnostics могут выполняться автоматически. Критичные writes требуют подтверждения: удаление знаний, отключение каналов, массовые сообщения, платные действия, billing-sensitive changes и т.п.

Все AI-действия логируются: tenant, user, agent, action, timestamp, old_value, new_value, result.

## 15. Telegram
Два режима.

**Instant:** общий DELNO Bot / Mini App + opaque deep links. Token backend-side связывается с tenant/specialist/service/campaign/source.

**Branded:** клиент сам создаёт bot через BotFather, получает token и передаёт DELNO. DELNO валидирует, настраивает webhook, knowledge, scenarios, тестирует и запускает. Tenant Operator ведёт пользователя пошагово.

## 16. MAX
Основной сценарий — branded.

Клиент сам создаёт и верифицирует MAX-бота, остаётся владельцем, передаёт token/ключ DELNO. DELNO валидирует, связывает с tenant, настраивает webhook/knowledge/agent, тестирует и запускает.

## 17. Web / Voice Widget
На клиентских сайтах: floating orb, voice-first, text fallback, human handoff, lead capture, attribution «Работает на DELNO».

Будущая установка может быть через JS snippet с data-tenant.

Widget также является growth-loop через referral attribution.

## 18. Voice и model providers
Для low-latency voice предпочтительны realtime transport + tool calling.

API keys только backend-side.

Модель/провайдер должны быть replaceable. DELNO не конкурирует с OpenAI/Google/Anthropic на уровне базовой модели; использует лучшие модели как инфраструктуру.

## 19. Moat против крупных AI-платформ
Строить DELNO так, будто через 2–3 года интеллект модели станет дешёвым и одинаково хорошим у всех.

Moat: Action Layer, Deep Business Context, Integrations, Workflow History, Distribution, Vertical Templates, Marketplace, Trust/Security/Operations, Self-healing, Switching Cost.

Если новая модель дешевле/лучше — это должно снижать себестоимость DELNO, а не обнулять продукт.

## 20. Supervisor Agent
Отдельный платформенный агент владельца DELNO.

Следит за Telegram/MAX, SIP, email, KB gaps, billing/payment failures, AI/voice errors, usage spikes, onboarding failures, latency, API errors.

Flow: Incident → Diagnosis → auto-fix? → fix + verify + audit → при необходимости действие клиента → escalation owner только если не решено.

Severity: INFO / WARNING / CRITICAL.

## 21. Daily Owner Digest
Активные tenant, новые tenant, incidents, auto-resolved, waiting for customer, owner action required, MRR, AI cost, telephony cost, churn risk, failed payments, usage anomalies.

## 22. Операционная цель
Главный KPI: **Human minutes per active customer per month**.
Цели: <10 мин → <3 мин → близко к 0.

Второй KPI: **Autonomous Resolution Rate**, целевая зрелая система 90%+ типовых проблем без человека.

## 23. Automation Engine
Trigger → Condition → Action.

Triggers: lead.created, message.received, call.completed, form.submitted, usage.limit_reached, payment.failed, integration.error, timer.

Actions: send_message, send_email, make_call, run_agent, update_lead, create_task, send_webhook, notify_owner.

## 24. Knowledge
У каждого tenant отдельная KB. Источники: сайт, FAQ, документы, цены, услуги, инструкции, text, будущие integrations.

Retrieval всегда tenant-scoped. В UI желательно показывать provenance/source.

## 25. Self-service onboarding
Идеальный путь: registration → company name → website URL → auto-import knowledge → choose first task → choose channel → connect → test → production.

Target Time to Value < 15 minutes.

## 26. Self-selling loop
Traffic → Website → Live demo → Lead/signup → Payment → Automated onboarding → First value → Usage → Contextual upsell → Referral → New traffic.

Регулярно повторяющиеся операции должны автоматизироваться.

## 27. Partner Program
Категории: тренеры, курсы, бизнес-клубы, ассоциации, web/marketing agencies, CRM/telephony/1C integrators, consultants, AI consultants, communities.

Сущности: Partner, ReferralLink, Referral, PromoCode, Commission, Payout.

Уровни: Referral, Partner, Reseller.

Принцип: recurring revenue share.

## 28. Банки как distribution-channel
Долгосрочные модели: Referral, Reseller, Embedded in internet banking, Bundled, White Label, Revenue Share, Wholesale.

Ценность банку: recurring non-interest revenue, SMB retention, ценность РКО, cross-sell, сервис без собственной разработки.

## 29. Marketplace
DELNO должен стать интерфейсом к сторонним B2B-продуктам: телефония, эквайринг, РКО, бухгалтерия, онлайн-кассы, сайты/домены, реклама, SMS, ЭП, HR, delivery, insurance, business lending.

Принцип: **PARTNER → LEARN → BUILD**.

## 30. CRM strategy
Сейчас не строить Bitrix24 2.0.

Сначала интегрировать внешние CRM.

Triggers для CRM Lite: около 300 активных tenant и >30% CRM-like usage; около 1000 tenant и внешние CRM становятся bottleneck; значимая готовность платить за unified CRM.

CRM Lite: Contact, Company, Lead, Deal, Pipeline, Task, Note, Conversation timeline, Source attribution, AI summary, Next best action.

UX: «CRM для людей, которые не хотят пользоваться CRM». Управление голосом/естественным языком через tools.

## 31. Booking strategy
Для service verticals booking может быть важнее CRM.

Сначала integrate/partner, затем build при подтверждённой экономике.

Единые сущности: Company, Specialist, Service, Schedule, Booking, Customer, Channel.

Один Booking Engine для site/Telegram/MAX/phone.

## 32. Долгосрочная эволюция
Stage A — DELNO Employee: отвечает, консультирует, записывает, звонит.

Stage B — DELNO Manager: анализирует, настраивает, создаёт automations, делает proactive recommendations.

Stage C — DELNO Business OS: CRM, booking, automation, analytics, marketing, partners, payments integrations.

Stage D — DELNO Autopilot: управляет значительной частью repeatable operations и эскалирует человеку только исключения.

Долгосрочная формулировка: **«Просто скажите, что нужно бизнесу. DELNO сделает остальное.»**

## 33. High-stakes ограничения
DELNO может собирать данные, объяснять общие варианты, готовить drafts и маршрутизировать к профильному специалисту, но не должен изображать лицензированного врача/юриста/финансового советника там, где требуется профессиональная ответственность.

## 34. Roadmap по tenant
### 0–100
Website, AI employee, web/voice, Telegram/MAX/email, telephony, knowledge, onboarding, billing.

### 100–300
Supervisor, self-healing, partner cabinet, referral, scope guard, industry templates, proactive upsell, automatic support.

### 300–1 000
CRM Lite, booking, calendar, pipelines, extra AI employees, analytics, premium automations.

### 1 000–5 000
Bank/reseller distribution, marketplace, advanced CRM, industry packs, white label, embedded B2B services.

### 5 000+
DELNO Business OS, own CRM default, marketplace ecosystem, developer platform/API, deeper financial/business services, vertical products.

## 35. Что НЕ делать сейчас
Не строить: Kubernetes, десятки микросервисов, отдельную VM/модель/БД на tenant, отдельный Cursor на tenant, гигантскую CRM, ERP, мобильное приложение без доказанной необходимости, ручное внедрение как стандарт.

## 36. Build / Partner / Replace
Перед разработкой нового модуля оценивать adoption, customer spend, partner margin, build/support cost, strategic data value, switching cost, time-to-value, ARPU impact.

Строить своё только когда экономика и стратегическая ценность подтверждены.

## 37. North Star
**DELNO = AI Operating Layer for SMB.**

Не самый большой набор функций и не самый дешёвый бот, а один ИИ-сотрудник/оператор, через которого предприниматель управляет бизнесом и подключёнными сервисами естественным языком.

## 38. Правила для Cursor
1. Читать этот файл до product/architecture решений.
2. Изучить delno-platform.
3. Quantum Office использовать только как reference.
4. Не переписывать работающие части без причины.
5. Не добавлять архитектурную сложность без requirement.
6. Все новые core entities — multi-tenant.
7. Integrations — через adapters/interfaces.
8. Agent actions — только через backend tools.
9. Critical writes — confirmation + audit.
10. Не смешивать future roadmap с текущим milestone.
11. Material decisions отражать в Decision Log и Changelog.

## 39. Документы в repo
Рекомендуемая структура:
```
docs/
├── 00_MASTER_SPEC.md
├── 01_PRODUCT.md
├── 02_ARCHITECTURE.md
├── 03_TENANT_MODEL.md
├── 04_TENANT_AI_OPERATOR.md
├── 05_CHANNELS.md
├── 06_KNOWLEDGE.md
├── 07_AUTOMATION.md
├── 08_SUPERVISOR.md
├── 09_GROWTH.md
├── 10_PRICING.md
├── 11_ROADMAP.md
├── 12_DECISIONS.md
├── 13_CHANGELOG.md
├── 14_MARKETPLACE.md
├── 15_CRM_STRATEGY.md
└── 16_SITE_PHASE_1.md
```

## 40. Важнейшие решения
DEC-001: DELNO = ИИ-сотрудник, не chatbot platform.
DEC-002: Quantum Office — отдельный reference.
DEC-003: DELNO = multi-tenant SaaS.
DEC-004: Cursor/Codex = dev tools, не runtime клиентов.
DEC-005: tenant isolation обязательна.
DEC-006: tenant_id определяет backend, не LLM.
DEC-007: Tenant AI Operator — центральный UX кабинета.
DEC-008: Operator ограничен scope DELNO/бизнеса клиента.
DEC-009: MAX branded bots создаёт/подтверждает клиент.
DEC-010: Telegram поддерживает Instant и Branded.
DEC-011: Widget имеет attribution/growth-loop.
DEC-012: Supervisor Agent решает проблемы до escalation owner.
DEC-013: Human minutes/customer — основной ops KPI.
DEC-014: Partner model = recurring.
DEC-015: Банки = strategic distribution-channel.
DEC-016: Future DELNO = AI Operating Layer / Business OS.
DEC-017: Model providers replaceable.
DEC-018: Moat строится выше LLM.
DEC-019: CRM — позже, по usage/economics.
DEC-020: Marketplace = PARTNER → LEARN → BUILD.
DEC-021: Текущий приоритет — сайт.
DEC-022: Hero должен проходить 5–10 second clarity test.
DEC-023: Visual language = premium/product-first, не generic SaaS.
DEC-024: Form modal центрирована и отправляет лид в backend.
DEC-025: Не обещать то, что ещё не работает надёжно.

## 41. Следующая задача после сайта
После Phase 1:
- провести аудит delno-platform / Quantum Office;
- сформировать Unified DELNO Backend;
- начать Multi-Tenant Core;
- затем Customer Cabinet;
- затем Tenant Voice Operator.

До этого не начинать большую CRM/Marketplace/Business OS реализацию.
