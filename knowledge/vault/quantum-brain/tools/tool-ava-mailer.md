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
source: tools#ava-mailer
shard: tool-ava-mailer
---

# Инструмент: ava-mailer

Центральный office HTTP-сервис для голоса AVA и части text-bot flows.

- Путь: `/opt/ava-mailer`
- Порт: `8000` (`0.0.0.0`)
- Unit: `ava-mailer.service`

## Что умеет

- Календарь Mail.ru CalDAV (check / create) — также есть отдельный `ava-calendar :8014`
- Создание события + Яндекс Телемост + welcome email/PDF
- Proxy базы знаний: `POST /api/knowledge/query` → `ava-knowledge :8017`
- Post-call webhook: разбор звонка → письмо в office / fan-out
- SMTP `office@quantumlabs.ru`
- OAuth Яндекс (Телемост)

## Типовые API (голосом)

- `POST /api/calendar/check`
- `POST /api/calendar/create`
- `POST /api/knowledge/query`
- health: `GET /health`

Секреты только в `/opt/ava-mailer/.env` (не в базе знаний).
