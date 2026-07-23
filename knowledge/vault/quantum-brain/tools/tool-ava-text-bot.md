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
| Владелец | `SECRETARY_OWNER_IDS` | личный секретарь, память/почта/контакты brain |
| Гость | остальные | офисный тон, FAQ, календарь, конференция, файлы |

## Сценарии (`scenarios.yaml`)

`secretary`, `calendar`, `conference`, `knowledge`, `memory`, `files`, `briefing`, `client_prep`, `office`.

Команды: `/start` `/help` `/reset` `/режимы` `/режим calendar` `/режим сброс`.

## Связанные модули

- knowledge `:8017` (Second Brain + FAQ)
- calendar `:8014`
- conference `:8016`
- files `:8015`
- mailer `:8000`

Owner tools: `search_office_memory`, `find_office_contact`, `list_office_threads`, `expand_office_graph` → brain API.
