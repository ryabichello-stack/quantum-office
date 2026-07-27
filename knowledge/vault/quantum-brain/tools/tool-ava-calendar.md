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
source: tools#ava-calendar
shard: tool-ava-calendar
---

# Инструмент: ava-calendar

Отдельный сервис проверки и создания событий (Mail.ru CalDAV).

- Путь: `/opt/ava-calendar`
- Порт: `8014`
- Unit: `ava-calendar.service`

## API

- `POST /api/calendar/check` — занятость слота
- `POST /api/calendar/suggest` — предложить свободные окна
- `POST /api/calendar/create` — создать событие; опционально Телемост через conference-сервис

При `create_telemost=true` вызывает `ava-conference :8016` и кладёт `join_url` в событие.

Timezone по умолчанию: `Europe/Moscow`.
