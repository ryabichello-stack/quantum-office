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

## Связь с conference/ и mailer/

При `create_telemost=true` (или `CREATE_TELEMOST_BY_DEFAULT=true`) calendar вызывает  
`POST {CONFERENCE_BASE_URL}/api/conferences` и кладёт `join_url` в событие.

После create (если есть `attendee_email`) calendar ставит welcome в очередь:  
`POST {MAILER_BASE_URL}/api/welcome/presentation` (`WELCOME_VIA_MAILER=true`).

## Прод

| | |
|--|--|
| path | `/opt/ava-calendar` |
| port | `8014` |
| unit | `ava-calendar.service` |

Голосовая AVA (`ai-agent.local.yaml`) ходит сюда для `check_calendar` / `create_calendar_event`.  
Legacy calendar routes на mailer `:8000` ещё живы, но voice tools на них не указывают.
