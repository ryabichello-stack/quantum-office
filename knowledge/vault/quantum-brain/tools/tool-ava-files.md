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
source: tools#ava-files
shard: tool-ava-files
---

# Инструмент: ava-files (брокер файлов)

Доставка файлов из источников в email или Telegram.

- Путь: `/opt/ava-files`
- Порт: `8015`
- Unit: `ava-files.service`

## API

- `POST /api/files/send` — скачать/взять файл и отправить
- `POST /api/files/fetch` — только проверить/прочитать

## Источники (`source`)

| source | описание |
|--------|----------|
| local | allowlist локальных путей |
| repo / github | файл из GitHub-репозитория |
| yadisk | Яндекс.Диск |
| mailru | Mail.ru Облако WebDAV |

## Каналы (`via`)

- `email` → адрес почты
- `telegram` → chat_id

Типичный кейс: отправить презентацию Quantum Payouts клиенту.
