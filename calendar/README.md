# calendar — отдельный модуль проверки и создания событий

Mail.ru CalDAV: check / suggest / create. Совместим по путям с тем, что раньше жило в mailer.

## API

```http
POST /api/calendar/check
{"start":"2026-07-22T17:00:00","timezone":"Europe/Moscow"}

POST /api/calendar/suggest
{"start":"2026-07-22T17:00:00","duration_min":30,"suggestions_count":3}

POST /api/calendar/create
{
  "start": "2026-07-22T17:00:00",
  "summary": "Созвон с клиентом",
  "attendee_email": "ivan@example.com",
  "create_telemost": true,
  "send_telemost_invite": false
}
```

Health: `GET /health`

## Связь с conference/

При `create_telemost=true` (или `CREATE_TELEMOST_BY_DEFAULT=true`) calendar вызывает  
`POST {CONFERENCE_BASE_URL}/api/conferences` и кладёт `join_url` в событие.

## Прод (когда задеплоим)

| | |
|--|--|
| path | `/opt/ava-calendar` |
| port | `8014` |
| unit | `ava-calendar.service` |

Mailer `:8000` calendar routes пока не трогаем — сначала выкат calendar, потом переключим AVA tools.
