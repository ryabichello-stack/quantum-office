# Architecture: Files broker

```mermaid
flowchart LR
  Client[API / agent / AVA]
  Files[ava-files :8015]
  Local[local allowlist]
  GH[GitHub repo]
  Ya[Yandex Disk]
  MR[Mail.ru Cloud]
  SMTP[SMTP email]
  TG[Telegram Bot API]

  Client -->|POST /api/files/send| Files
  Files --> Local
  Files --> GH
  Files --> Ya
  Files --> MR
  Files -->|via=email| SMTP
  Files -->|via=telegram| TG
```

## Boundary

| Owns | Does not own |
|------|----------------|
| Fetch + send files | Bitrix outreach sequences |
| Source adapters | Asterisk / AVA docker |
| Allowlist / size limits | Polyhub trading |
| Email+TG delivery of attachments | Full CRM |

## Safety

- Local paths must stay under `FILES_LOCAL_ALLOWLIST`
- `FILES_MAX_BYTES` caps payload (Telegram-friendly)
- Tokens only in `.env`
