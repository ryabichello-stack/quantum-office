# calendar — multi-provider calendar broker

Sources (tools-first — without tokens return stub slots / staged create):

| source | backend | env |
|--------|---------|-----|
| `mailru` | Mail.ru CalDAV | `MAILRU_CALDAV_*` + `MAILRU_CALENDAR_URL` |
| `yandex` | Яндекс.Календарь CalDAV | `YANDEX_CALDAV_*` + `YANDEX_CALENDAR_URL` |
| `google` | Google Calendar API | `GOOGLE_CALENDAR_TOKEN`, optional `GOOGLE_CALENDAR_ID` |
| `outlook` | Microsoft Graph | `OUTLOOK_CALENDAR_TOKEN` / `MICROSOFT_GRAPH_TOKEN` |

Default source: `CALENDAR_DEFAULT_SOURCE=mailru`.

## API

```http
GET /api/calendar/providers

POST /api/calendar/check
{"start":"2026-07-22T17:00:00","timezone":"Europe/Moscow","source":"google"}

POST /api/calendar/suggest
{"start":"2026-07-22T17:00:00","duration_min":30,"source":"yandex"}

POST /api/calendar/create
{
  "start": "2026-07-22T17:00:00",
  "summary": "Созвон с клиентом",
  "source": "outlook",
  "attendee_email": "ivan@example.com",
  "create_telemost": true
}
```

Health: `GET /health` — lists all providers + `configured` flags.

## Telemost

При `create_telemost=true` calendar вызывает  
`POST {CONFERENCE_BASE_URL}/api/conferences` и кладёт `join_url` в событие.

## Прод / DELNO

| | |
|--|--|
| path | `/opt/delno/calendar` (или `/opt/ava-calendar`) |
| port | `8014` host `18014` |
| unit / compose | `delno-calendar` |
