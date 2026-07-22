# conference — отдельный сервис Телемост + приглашения

**Зачем:** создание видеовстречи по запросу, без привязки к post-call / calendar-only flow в mailer.

## API

```http
POST /api/conferences
X-Webhook-Token: <WEBHOOK_TOKEN>
Content-Type: application/json

{
  "title": "Срочный созвон с Иваном",
  "invitees": ["ivan@example.com", "office@quantumlabs.ru"],
  "when_text": "сегодня 17:00 МСК",
  "message": "Нужно обсудить договор",
  "send_invites": true
}
```

Ответ:

```json
{
  "ok": true,
  "conference_id": "...",
  "join_url": "https://telemost.yandex.ru/j/...",
  "invites": [{"email":"ivan@example.com","sent":true,"error":""}],
  "message": "Конференция создана: ..."
}
```

Health: `GET /health`

## Голосовой сценарий (следующий шаг)

AVA tool `create_conference` → `POST http://127.0.0.1:8013/api/conferences`  
Фраза: «срочно создай конференцию, пригласи Ивана на ivan@…»

## Прод (когда задеплоим)

| | |
|--|--|
| path | `/opt/ava-conference` |
| port | `8013` |
| unit | `ava-conference.service` |
| secrets | `/opt/ava-conference/.env`, `yandex_oauth_tokens.json` |

Mailer (`:8000`) пока сам умеет Telemost внутри `calendar/create` — это не ломаем. Позже можно перевести calendar на вызов этого сервиса.
