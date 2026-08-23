# Changelog

Все значимые изменения этого репозитория фиксируются здесь.

Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/),
версии — по [Semantic Versioning](https://semver.org/lang/ru/).

Каждый merge в `main` обязан обновлять этот файл.
Секреты (`.env`, OAuth tokens, credentials) в changelog и в git **не** попадают.

## [Unreleased]

### Added

- **RBAC** (`modules/rbac`): roles owner/ops/analyst/viewer; `OUTREACH_RBAC_ENABLED` + `OUTREACH_ROLE_TOKENS`; `GET /api/v1/me`; write-path permission gates
- **Owned-page listen stub** (`radar/owned_listen`): `OWNED_TG_CHANNELS` / `OWNED_VK_GROUPS` → Radar signals via `POST /api/modules/radar/owned/poll` (never auto-outreach)
- **YouTube Data API client skeleton** (`video_studio/youtube_client.py`): private-only upload path via `YOUTUBE_CLIENT_SECRETS` / `YOUTUBE_TOKEN_PATH`
- UI ops22: роль + usage в Студии/Настройках; кнопка Owned poll; gate write-кнопок при RBAC
- **Social Publish** (`modules/social_publish`): каналы TG/VK/Instagram/YouTube, мультиплатформенные посты + SVG-картинки, репост после approve (`SOCIAL_PUBLISH_ENABLED`)
- UI ops23: вкладка Студия → «Соцсети» (каналы, генерация, репост)
- **Content Flywheel** (`modules/content_flywheel`): parse news → KB inbox → dedup memory → editorial slots (3×/day) → proposals → social post + talking-head video brief
- **Thematic analysis** (`content_flywheel/thematic`): macro-financial / money-flows lens per news; min score gate; product KB optional (`FLYWHEEL_USE_PRODUCT_KB`)
- UI ops24: вкладка «Флайвил» (sources, poll, run-cycle, approve)
- Архитектура: `docs/architecture/CONTENT_FLYWHEEL.md`
- **AI Revenue OS Stage 0** — architecture pack in `docs/architecture/` (AS_IS, TARGET, GAP, DATA_MAPPING, SOCIAL_CAPABILITY_MATRIX, MIGRATION_PLAN, BACKLOG)
- **Stage 1 data core** (`outreach/modules/accounts`): Account / Person / Employment / ContactPoint / Lead / `domain_events`; lifecycle `NEW`…`BLACKLISTED`; SoT local + Bitrix company id (Accept R1/R2)
- **Slice A inbound**: IMAP reply → resolve Account/Person/Lead + `message.received` / `message.classified`; Console call watcher → `call.completed` via `/api/modules/accounts/resolve-inbound`
- Inbox peel-away **enrichment panel** (Account / Person / Lead) + rules-first **suggested next action** + APPROVAL_REQUIRED reply draft («Вставить черновик»); thread API field `enrichment`
- API: `/api/modules/accounts/*`, `/meta/enrichment`, `/meta/suggest-next`, `/meta/events`, `/meta/leads`
- Tenant seed: `outreach/config/tenants/quantum-labs/` (product / ICP / roles / channel policy)
- **Slice B scaffold** (`outreach/modules/social`): SocialSourceAdapter registry (clients, dadata, web_import, telegram + stubs vk/ok/tenchat/linkedin); `LPRSearchRun` / candidates / score / identity cluster (APPROVAL_REQUIRED); coverage matrix; `SocialActionTask` without auto-DM; API `/api/modules/social/*`
- **ЛПР UI** — вкладка «ЛПР» в Outreach (search / coverage / approve-reject / task)
- **Send guards** — единый gate: suppression + consent DNC + Account `BLACKLISTED` перед send
- **Second Brain citations** в suggested reply (best-effort `KNOWLEDGE_BASE` / `/api/brain/search` → fallback `/api/knowledge/query`)
- **Orchestrator scaffold** (`modules/orchestrator`): journey definitions, enroll, dry-run, stop-on-reply + sequence stop
- **Content Studio MVP** (`modules/content_studio`): objection → draft pack letters, APPROVAL_REQUIRED
- **Intent Radar MVP** (`modules/radar`): ingest signals + verify suggest action (never auto-outreach)
- **Video Studio MVP** (`modules/video_studio`): private draft + approve → queue private upload (YouTube stub)
- **UI ops20**: вкладки ЛПР (карточки + покрытие) и Студия (Контент / Radar / Видео)
- **API v1 facade** `/api/v1/accounts|people|conversations|leads` (+ tenant bootstrap)
- **Bitrix Lead sync adapter** (`bitrix_leads.py`, `POST .../leads/{id}/sync-bitrix`)
- **Identity cluster merge** (`POST /social/clusters/{id}/merge` + кнопка в ЛПР UI)
- **YouTube private upload queue** flag `YOUTUBE_UPLOAD_ENABLED` (без auto-publish)
- **Usage metering lite** (`usage_meter` + `GET /api/v1/usage`)
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
- 2026-08-23 (cont.): ЛПР UI, send guards, SB citations, orchestrator scaffold — redeploy outreach
- 2026-08-23 (cont.2): content_studio + radar modules + orchestrator body-param fix
- 2026-08-23 (cont.3): FastAPI JSON body fix; sync 300 accounts from clients; POST APIs verified
- 2026-08-23 (cont.4): UI ops20 ЛПР+Студия; Video Studio scaffold; acceptance tests
- 2026-08-23 (cont.5): API v1, Bitrix lead sync, cluster merge UI, tenant bootstrap, ops21
- 2026-08-23 (cont.6): usage metering lite on prod
- 2026-08-23 (cont.7): RBAC module + owned listen + YouTube client skeleton; UI ops22 on prod
- 2026-08-23 (cont.8): Social Publish (TG/VK/IG/YT posts, images, repost); UI ops23
- 2026-08-23 (cont.9): Content Flywheel MVP; UI ops24
- 2026-08-23 (cont.10): KB enrich (Second Brain + product profile) in posts; ops25
- 2026-08-23 (cont.11): thematic macro-financial analysis per news; ops26
- 2026-08-23 (cont.12): tenant-defined content themes (any niche) + UI editor; ops27
- 2026-08-23 (cont.13): default tenant generic, industry presets, neutral post/video templates; ops28

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
