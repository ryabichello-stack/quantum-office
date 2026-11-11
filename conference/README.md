# conference — multi-provider video meetings + invites

**Providers:** `yandex` (Telemost) · `google_meet` · `zoom` · `teams` · `jitsi`

Tools-first: without provider credentials returns deterministic stub join URLs
(`https://stub.<provider>.delno.local/...`). Jitsi works without OAuth (public room URL).

## API

```http
GET /api/conferences/providers
X-Webhook-Token: <WEBHOOK_TOKEN>
```

```http
POST /api/conferences
X-Webhook-Token: <WEBHOOK_TOKEN>
Content-Type: application/json

{
  "title": "Срочный созвон с Иваном",
  "provider": "jitsi",
  "invitees": ["ivan@example.com"],
  "when_text": "сегодня 17:00 МСК",
  "message": "Нужно обсудить договор",
  "send_invites": true
}
```

`provider` aliases: `telemost`→`yandex`, `gmeet`/`google`→`google_meet`,
`ms_teams`/`msteams`→`teams`. Default: `CONFERENCE_DEFAULT_PROVIDER` or `yandex`.

Ответ:

```json
{
  "ok": true,
  "provider": "jitsi",
  "conference_id": "...",
  "join_url": "https://meet.jit.si/...",
  "stub": false,
  "invites": [],
  "message": "..."
}
```

Health: `GET /health` — lists all providers + `configured` flags.

## Credentials (optional)

| Provider | Env |
|----------|-----|
| yandex | `YANDEX_OAUTH_*` / `YANDEX_TELEMOST_OAUTH_TOKEN` |
| google_meet | `GOOGLE_MEET_TOKEN` or `GOOGLE_CALENDAR_TOKEN` |
| zoom | `ZOOM_ACCESS_TOKEN` or `ZOOM_ACCOUNT_ID`+`CLIENT_ID`+`SECRET` |
| teams | `TEAMS_TOKEN` / `MICROSOFT_GRAPH_TOKEN` |
| jitsi | `JITSI_BASE_URL` (default `https://meet.jit.si`), `JITSI_ENABLED=true` |

`CONFERENCE_STUB_WHEN_UNAUTH=true` (default) → stub instead of hard fail.

## Голосовой / DELNO tool

`create_conference` → `POST …/api/conferences` with optional `provider`.

## Прод

| | |
|--|--|
| path | `/opt/ava-conference` (QO) / `/opt/delno/conference` (DELNO) |
| port | `8016` / host `18016` |
| secrets | `.env` (mode 600), `yandex_oauth_tokens.json` |
