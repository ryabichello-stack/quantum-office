# Changelog

Все значимые изменения этого репозитория фиксируются здесь.

Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/),
версии — по [Semantic Versioning](https://semver.org/lang/ru/).

Каждый merge в `main` обязан обновлять этот файл.
Секреты (`.env`, OAuth tokens, credentials) в changelog и в git **не** попадают.

## [Unreleased]

### Added

- Outreach: отраслевые пакеты писем (ломбарды, МФО, trade-in, гиг, вторсырьё) с 3-шаговыми цепочками
- Юридический футер + «Отписаться» / List-Unsubscribe в шаблонах; презентация PDF на 1-м письме
- API `GET/POST /api/packs` (+ apply) и вкладка «Кампания» в UI (Console embed + standalone)
- Из Outreach: кнопка «Задание на звонок» → вкладка пульта через postMessage
- Цепочки по playbook ломбардов: 5 касаний (дни 0/3/6/10/15), позиционирование «платёжная инфраструктура + подбор банка»; тот же каркас для МФО / trade-in / гиг / вторсырьё
- Playbook: `outreach/content/playbooks/lombards.md`

### Changed

- Console UI: единый тонкий шрифт Manrope, компактные кнопки, понятнее подписи на пульте
- Вкладка «Задание на звонок»: режимы «своя тема» / «база знаний», русские подписи tools, автосборка сценария
- Outreach UI: полностью в стиле «Задание на звонок» — surface/поля/mode-cards, акцент Console, Кампания первой вкладкой; Рассылка / Очередь / Настройки тем же паттерном
- Outreach «Отчёт»: доли / воронка / по дням / пояснения / последние письма — в панелях с тонкой разлиновкой

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
