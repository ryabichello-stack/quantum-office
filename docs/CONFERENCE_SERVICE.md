# Architecture: Conference service

```mermaid
flowchart LR
  Voice[AVA voice / office request]
  Manual[HTTP / UI / agent]
  Conf[ava-conference :8013]
  TM[Yandex Telemost API]
  SMTP[Mail.ru SMTP]
  Mailer[ava-mailer :8000]

  Voice -->|POST /api/conferences| Conf
  Manual -->|POST /api/conferences| Conf
  Conf --> TM
  Conf -->|invite emails| SMTP
  Mailer -.->|optional future: reuse| Conf
  Mailer -->|today: calendar/create still embeds Telemost| TM
```

## Boundary

| Owns | Does not own |
|------|----------------|
| Telemost create | Bitrix outreach |
| Invite emails | Asterisk / AVA docker |
| Yandex OAuth for Telemost | Polyhub trading |
| On-demand conference API | Full CalDAV scheduling (stays in mailer for now) |

## Request example (office)

«Срочно создай конференцию, пригласи Петра на petrov@firm.ru»

→ tool args:

```json
{
  "title": "Срочный созвон с Петром",
  "invitees": ["petrov@firm.ru"],
  "when_text": "сейчас",
  "message": "По запросу из офиса"
}
```
