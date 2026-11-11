# Changelog

Все значимые изменения этого репозитория фиксируются здесь.

Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/),
версии — по [Semantic Versioning](https://semver.org/lang/ru/).

Каждый merge в `main` обязан обновлять этот файл.
Секреты (`.env`, OAuth tokens, credentials) в changelog и в git **не** попадают.

## [Unreleased]

### Added

- Docs/ops: `delno-files` broker live on Cloud4Box (`FILES_BASE_URL=http://files:8015`, :18015)
- Docs/ops: CRM-lite funnel + outreach staging stubs (27 MCP tools, 5 connectors incl. outreach)
- Docs/ops: multi-tenant MCP gateway + Hermes profile (`/v1/mcp`, `/v1/hermes/profile`)
- Docs/ops: office connectors stubs (mail/calendar/files/conference) + tenant-beta dogfood
- Docs/ops: политика tools-first; admin :3010; GET /v1/tenant/tools; ответ по AVA/Asterisk multi-tenant (E4)
- Docs: на Cloud4Box поднят канонический marketing site v2 (`DELNO-site-v23`) на `/` вместо заглушки
- Docs: bootstrap DELNO на Cloud4Box VPS (`docs/DELNO_VPS_BOOTSTRAP.md`) — Phase A live, cabinet/widget/brain, dogfood tenant `quantum-labs`, план Phase B (OpenAI/TG/DaData)
- Docs: полный аудит инструментов Quantum Office (`docs/QUANTUM_OFFICE_TOOLS_AUDIT.md`) — сервисы, MCP, каналы, DaData, CRM, пробелы для переноса на DELNO

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

### Changed

- Console UI: единый тонкий шрифт Manrope, компактные кнопки, понятнее подписи на пульте
- Вкладка «Задание на звонок»: режимы «своя тема» / «база знаний», русские подписи tools, автосборка сценария
- Outreach UI: полностью в стиле «Задание на звонок» — surface/поля/mode-cards, акцент Console, Кампания первой вкладкой; Рассылка / Очередь / Настройки тем же паттерном
- Outreach «Отчёт»: доли / воронка / по дням / пояснения / последние письма — в панелях с тонкой разлиновкой
- Отраслевые пакеты: финал писем через `{signature}` вместо жёсткой подписи; HTML — `{logo_header}` + корректный `{phone_line}`

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
