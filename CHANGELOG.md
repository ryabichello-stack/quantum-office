# Changelog

Все значимые изменения этого репозитория фиксируются здесь.

Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/),
версии — по [Semantic Versioning](https://semver.org/lang/ru/).

Каждый merge в `main` обязан обновлять этот файл.
Секреты (`.env`, OAuth tokens, credentials) в changelog и в git **не** попадают.

## [Unreleased]

### Added

- Hermes cabinet ChatGPT-class UI: empty state «Чем помочь?», refined composer, markdown/images in bubbles, toolkit panel (Ava telephony + connectors + generate_image)
- Hermes media: `generate_image` tool (OpenAI Images); video attachments (mp4/webm/mov) with Whisper audio transcript; `/v1/hermes-nous/toolkit`
- Voice dialogue: Whisper server fallback when browser SpeechRecognition fails; bridge polls `/v1/runs` for interactive replies
- Hermes night hardening: image-gen intents route to DIY `generate_image` (proxy models `gpt-image-1-mini` / `chatgpt-image-latest` + direct fast-path); Ava toolkit detail as readable RU status; user bubbles show video previews
- Hermes Nous: `lead.created` → `events_dispatch.on_lead_created` (durable AgentTask + queued AgentRun when `hermes_nous_runtime` on)
- Hermes Nous: detailed sqlite integration suite (`test_hermes_nous_integration.py`) — A/B run tokens, MCP fail-closed tool call, KB confirm, bridge runs+fallback, flag gate, hermes profile without long-lived key
- Hermes runtime Dockerfile: Python 3.14 + `uv sync --frozen --extra messaging`; lab smoke A/B on `:18642`/`:18643` (`scripts/lab_smoke.sh`); verified live `/v1/runs` → `completed` on C4B lab
- Hermes Nous P0–P5 implementation: office-loop/KB draft, tool packs, agent_tasks migration, Hermes UI path+tasks panels, channels/scale stubs
- Hermes Nous `MASTER_PLAN.md`: unified product+isolation+UI sequence (P0–P5)
- Hermes Nous product north star: `docs/hermes-nous/PRODUCT_LOOP.md` (онбординг → KB → тулзы → дирижирование)
- DELNO Hermes Nous Stage 0: pinned `hermes-agent` v0.23.1 runtime scaffold, per-tenant `HERMES_HOME` provision, scoped MCP run tokens, feature flag `hermes_nous_runtime`, bridge `/v1/hermes-nous/*` (DIY cabinet loop remains fallback)

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
