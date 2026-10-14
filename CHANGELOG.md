# Changelog

Все значимые изменения этого репозитория фиксируются здесь.

Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/),
версии — по [Semantic Versioning](https://semver.org/lang/ru/).

Каждый merge в `main` обязан обновлять этот файл.
Секреты (`.env`, OAuth tokens, credentials) в changelog и в git **не** попадают.

## [Unreleased]

### Fixed

- MCP `kb.search` / `knowledge.query`: больше не висят на PG-локах Second Brain — сначала `mode=legacy` (markdown), brain опционально ≤4s; в knowledge soft-timeout + `lock_timeout`/`statement_timeout` на Postgres.
- Outreach `inbound_replies`: сохраняется `body_text` (в т.ч. HTML→text); `POST /api/replies/backfill` + MCP `outreach.replies_backfill` дозаполняет пустые тела.

### Added

- Text-bot / MCP: чтение и отправка Telegram/Max — `GET /api/messenger/{status,chats,history,messages}`, `POST /api/messenger/send`; tools `messenger.chats`, `messenger.history`, `messenger.messages`, `telegram.history`, `max.history`. Gateway `0.3.2` / `schema_revision=2026-10-14-messenger-history`.
- Text-bot: синхронизация полноценного секретаря (каналы Max/Business/WhatsApp/VK, owner alerts) в git; stub `max_client` убран.
- MCP gateway `0.3.3` / `schema_revision=2026-10-14-kb-legacy-first-replies`.

### Fixed

- MCP gateway `0.3.1` + `schema_revision`: Grok/Cursor могут проверить, что каталог tools не stale; `/health` явно флагает `mailru.send_text_body`.
- MCP: `mailru.send` принимает `subject`+`body` без `path` → текстовое письмо через `office@` (не ходить в WebDAV); path без расширения больше не уходит в Облако.
- MCP `kb.search`: сначала быстрый `knowledge.query`, потом brain (короткий timeout) — меньше таймаутов у Grok.
- Outreach `GET /api/packs`: в списке есть `subject` / `plain_preview` (текст был только в `pack_get`).

### Added

- Files/MCP: `files.upload` / `mailru.upload` + `POST /api/files/upload` — сохранение файлов на Mail.ru Облако (text или base64); ассистент может писать на корпоративный диск, не только читать/отправлять.
- Outreach MCP: `mail.send` + `POST /api/mail/send` — обычные письма (text/html, cc, reply_to, mailbox=office|cold); холодный ящик через `OUTREACH_COLD_MAIL_*` (не `quantumlabs.ru`).
- Outreach: модуль `sending_accounts` + gate на `send_batch`/`send_one` — cold marketing только с ACTIVE marketing-аккаунта; `office@` остаётся для тёплой переписки.
- Outreach: `POST /api/leads/import` / `leads/check` + MCP `outreach.leads_import` / `lead_check` — CSV (компания, сегмент, сайт, email, телефон, ЛПР, источник) с дедупом по Bitrix clients + истории outbox.
- Outreach packs: `agents_fintech`, `agents_1c`, `agents_accounting`, `construction`, `blogger_agencies`, `agri`, `rental`.
- Replies: полный `body_text` в `/api/replies` и `check_replies` (для разбора ответов ассистентом).
- Knowledge: `knowledge.get("audience")` и другие catalog topic id резолвятся в секции темы (раньше `not_found`).
- MCP: `OUTREACH_UI_TOKEN` предпочитается над `WEBHOOK_TOKEN` для outreach API; таймауты `kb.search` / `knowledge.query` = 120s.
- `office-mcp/` — полноценный MCP stdio-сервер для office-стека (Grok/Cursor/Claude): телефония in/out, Sheets-кампания, календарь/Телемост, Second Brain, outreach, Telegram/Max, **Mail.ru Облако** (`mailru.list/search/read`); remote HTTPS пример `mcp.remote.example.json`; nginx snippet `deploy/nginx-office-api.conf.snippet` для `/_ava_files|knowledge|calendar|conference|sheets_campaign/`.
- `office-mcp` HTTP gateway для Grok: `https://a.47z.ru/_office_mcp/` + `OFFICE_MCP_API_KEY` (`POST /tools/call`, `POST /mcp`).
- `files`: `POST /api/files/read` — чтение текста из Mail.ru Cloud / Yadisk для агентов; text-bot: `/api/messenger/*` + `/api/chat` для MCP.
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

### Fixed

- Dial: при обрыве до гудка в ответе явный `sip_cause` (например `486 Busy Here`), не маскируем под «ok».
- Исходящие: SIP signaling биндится на `45.147.178.172` (+ SNAT) — с primary `5.35.86.62` Mango отвечал 486/403 без гудков.
- Console `POST /api/outbound/dial`: `mode=auto` — Mango callback только если API **live**; иначе SIP/ARI с проверкой жизни канала (`ok:false` если канал сразу умер).
- Dialplan: extension `12` (Mango callback) → `AI_CONTEXT=outbound` + per-call script из AstDB (не входящий секретарь).
- Status: `outbound.mango_api_live` / `preferred` по живому probe (не по наличию ключей); сейчас API = Service disabled → preferred `sip_pjsip`.

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
