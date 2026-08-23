# Changelog

Все значимые изменения этого репозитория фиксируются здесь.

Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/),
версии — по [Semantic Versioning](https://semver.org/lang/ru/).

Каждый merge в `main` обязан обновлять этот файл.
Секреты (`.env`, OAuth tokens, credentials) в changelog и в git **не** попадают.

## [Unreleased]

### Added

- **AI Revenue OS Stage 0** — architecture pack in `docs/architecture/` (AS_IS, TARGET, GAP, DATA_MAPPING, SOCIAL_CAPABILITY_MATRIX, MIGRATION_PLAN, BACKLOG)
- **Stage 1 data core** (`outreach/modules/accounts`): Account / Person / Employment / ContactPoint / Lead / `domain_events`; lifecycle `NEW`…`BLACKLISTED`; SoT local + Bitrix company id (Accept R1/R2)
- **Slice A inbound**: IMAP reply → resolve Account/Person/Lead + `message.received` / `message.classified`; Console call watcher → `call.completed` via `/api/modules/accounts/resolve-inbound`
- Inbox peel-away **enrichment panel** (Account / Person / Lead) + rules-first **suggested next action** + APPROVAL_REQUIRED reply draft («Вставить черновик»); thread API field `enrichment`
- API: `/api/modules/accounts/*`, `/meta/enrichment`, `/meta/suggest-next`, `/meta/events`, `/meta/leads`
- Tenant seed: `outreach/config/tenants/quantum-labs/` (product / ICP / roles / channel policy)
- **Slice B scaffold** (`outreach/modules/social`): SocialSourceAdapter registry (clients, dadata, web_import, telegram + stubs vk/ok/tenchat/linkedin); `LPRSearchRun` / candidates / score / identity cluster (APPROVAL_REQUIRED); coverage matrix; `SocialActionTask` without auto-DM; API `/api/modules/social/*`
- Outreach: отраслевые пакеты писем (ломбарды, МФО, trade-in, гиг, вторсырьё) с 3-шаговыми цепочками
- Юридический футер + «Отписаться» / List-Unsubscribe в шаблонах; презентация PDF на 1-м письме
- API `GET/POST /api/packs` (+ apply) и вкладка «Кампания» в UI (Console embed + standalone)
- Из Outreach: кнопка «Задание на звонок» → вкладка пульта через postMessage
- Цепочки по playbook ломбардов: 5 касаний (дни 0/3/6/10/15), позиционирование «платёжная инфраструктура + подбор банка»; тот же каркас для МФО / trade-in / гиг / вторсырьё
- Playbook: `outreach/content/playbooks/lombards.md`
- Письма: продающие хуки + **жирные** акценты; «не посредник — tech-партнёр, прямые договоры с банками, сильные ставки по рынку»
- Приветствие: ФИО руководителя / «Уважаемый руководитель»; при rebuild очереди подставляется director из DaData/Bitrix
- UI: прокрутка длинных textarea в iframe Outreach
- Кампания: редактируемая подпись (`OUTREACH_SIGNATURE` / `{signature}`), телефон из формы в превью и письме
- Микрологотип Quantum Labs в шапке HTML-письма + загрузка/сброс (`/api/brand/logo`, `assets/brand/logo-mark.png`)
- Outreach: HTML-превью кампании показывает body письма (не пустой белый блок); колесо мыши в полях iframe надёжнее
- Кампания: живое превью подписи + кнопка «Применить контакты» (телефон/компания/сайт сразу в подпись и settings)
- HTML-подпись: микрозначки сайт / почта / телефон (`assets/brand/icons/*.png`)
- Кампания: загрузка/замена PDF-презентации по отрасли (`/api/packs/{id}/presentation`, хранение в `data/presentations/`)
- Кампания: разовое тестовое письмо на указанный адрес (сохраняет поля → `/send-one`, с PDF по флажку)
- Письма: universal callback CTA — inline form + bulletproof кнопка (Gmail) + mailto fallback; one-screen landing
- Outreach Layers A–G3 control plane: B2B send windows, queue bulk/calendar, company peel-away, consent, Quantum Panel Telegram, ops notify, inbox thread+reply, call notify, step conversion %

### Changed

- Console UI: единый тонкий шрифт Manrope, компактные кнопки, понятнее подписи на пульте
- Вкладка «Задание на звонок»: режимы «своя тема» / «база знаний», русские подписи tools, автосборка сценария
- Outreach UI: полностью в стиле «Задание на звонок» — surface/поля/mode-cards, акцент Console, Кампания первой вкладкой; Рассылка / Очередь / Настройки тем же паттерном
- Outreach «Отчёт»: доли / воронка / по дням / пояснения / последние письма — в панелях с тонкой разлиновкой
- Отраслевые пакеты: финал писем через `{signature}` вместо жёсткой подписи; HTML — `{logo_header}` + корректный `{phone_line}`
- Accept R5: Social Intelligence живёт в `outreach/modules/social` (не отдельный сервис до нагрузки)

### Deployed

- 2026-08-23: `ava-outreach` + `quantum-console` на `5.35.86.62` (Stage 1 accounts + Slice A enrichment + Slice B social); asterisk/mailer не трогали

## [0.2.0] — 2026-08-20

### Added

- `console/` — Quantum Console как единый **пульт** секретаря (`:8013`)
  - вкладка «Пульт»: автолиния входящих, робот, outreach/campaign glance, последние звонки
  - API `GET/POST /api/line` (AstDB `quantum/inbound_line`)
  - dialplan `from-mango`: при `off` — Busy без Stasis/OpenAI
  - health calendar / conference / files / knowledge
- В git выгружены office-сервисы с прода (код без venv/секретов/БД):
  - `knowledge/` → `/opt/ava-knowledge`
  - `calendar/` → `/opt/ava-calendar`
  - `conference/` → `/opt/ava-conference`
  - `files/` → `/opt/ava-files`
  - `sheets-campaign/` → `/opt/ava-sheets-campaign`
- `CHANGELOG.md`, `CONTRIBUTING.md`, правила версионирования в `AGENTS.md`

### Changed

- `README.md` / `docs/PROD_MAP.md` / `AGENTS.md` — карта сервисов и пульта

## [0.1.0] — 2026-08-20

### Added

- Первичный импорт `outreach/`, `mailer/`, `text-bot/`, `docs/`
