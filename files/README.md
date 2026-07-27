# files — брокер файлов (источник → email / Telegram)

По тому же принципу, что `conference/`: отдельный API-сервис office-стека.

## API

```http
POST /api/files/list
```json
{ "source": "mailru", "path": "/" }
```

Returns folders + files for one directory level (with `created_at` / `modified_at`).

POST /api/files/search
```json
{ "source": "mailru", "query": "банк", "path": "/", "limit": 40 }
```

Name search (Mail.ru = recursive BFS under `path`).

POST /api/files/send
X-Webhook-Token: <WEBHOOK_TOKEN>
Content-Type: application/json

{
  "source": "yadisk",
  "path": "/Презентации/quantum.pdf",
  "via": "email",
  "to": "ivan@example.com",
  "caption": "Презентация Quantum Labs",
  "subject": "Материалы"
}
```

Telegram:

```json
{
  "source": "local",
  "path": "quantum_payouts_presentation.pdf",
  "via": "telegram",
  "to": "123456789",
  "caption": "Вот файл"
}
```

Только проверить, что файл читается:

```http
POST /api/files/fetch
{"source":"repo","path":"mailer/assets/quantum_payouts_presentation_small.pdf"}
```

Health: `GET /health`

## Источники

| source | описание |
|--------|----------|
| `local` | файлы под `FILES_LOCAL_ALLOWLIST` |
| `repo` / `github` | файл из GitHub (`FILES_GITHUB_REPO`) |
| `yadisk` | Яндекс.Диск (`YADISK_TOKEN`) |
| `mailru` | Mail.ru Облако WebDAV (`MAILRU_WEBDAV_*`, fallback на `MAIL_*`) |

## Каналы

| via | to |
|-----|-----|
| `email` | адрес почты |
| `telegram` | `chat_id` |

## Прод (когда задеплоим)

| | |
|--|--|
| path | `/opt/ava-files` |
| port | `8015` |
| unit | `ava-files.service` |
| secrets | `/opt/ava-files/.env` |
