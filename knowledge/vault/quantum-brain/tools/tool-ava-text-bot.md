---
tenant_id: quantum-labs
visibility: company
classification:
  level: internal
  contains_personal_data: false
channels: [office-assistant]
ai_processing:
  allow_external_embed: true
publication:
  manual_approve: false
source: tools#ava-text-bot
shard: tool-ava-text-bot
---

# Инструмент: ava-text-bot (ИИ-секретарь)

Channel-agnostic секретарь Quantum Labs. Telegram + HTTP API.

- Путь: `/opt/ava-text-bot`
- Порт: `8011`
- Unit: `ava-text-bot.service`
- Бот: @Quantum_office_bot

## Роли

| Роль | Кто | Возможности |
|------|-----|-------------|
| Владелец | `SECRETARY_OWNER_IDS` | личный секретарь, память/почта/контакты brain, исходящие звонки |
| Гость | остальные | офисный тон, FAQ, календарь, конференция, файлы |

## Сценарии (`scenarios.yaml`)

`secretary`, `calendar`, `conference`, `knowledge`, `memory`, `files`, `briefing`, `client_prep`, `outbound`, `office`.

Команды: `/start` `/help` `/reset` `/режимы` `/режим outbound` `/режим сброс`.

## Исходящие звонки (owner)

Через Quantum Console `:8013`:

- `outbound_dial` — позвонить (нужно confirm)
- `get_outbound_scenario` / `update_outbound_scenario` — скрипт профиля outbound
- `list_outbound_calls` / `get_outbound_call` — отчёты/расшифровки

Входящий профиль `default` этими tools не меняется. Env: `AVA_CONSOLE_BASE`, `CONSOLE_TOKEN`.

## Связанные модули

- knowledge `:8017` (Second Brain + FAQ)
- calendar `:8014`
- conference `:8016`
- files `:8015`
- mailer `:8000`
- quantum-console `:8013`

Owner tools: `search_office_memory`, `find_office_contact`, `list_office_threads`, `expand_office_graph` → brain API.
