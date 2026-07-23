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
source: tools#ava-conference
shard: tool-ava-conference
---

# Инструмент: ava-conference (Яндекс Телемост)

Создание видеовстречи и email-приглашений по запросу.

- Путь: `/opt/ava-conference`
- Порт: `8016`
- Unit: `ava-conference.service`

## API

`POST /api/conferences` с `X-Webhook-Token`:

- `title`, `invitees[]`, `when_text`, `message`, `send_invites`

Ответ содержит `conference_id`, `join_url` (telemost.yandex.ru), статус инвайтов.

Голосовой/текстовый сценарий: «создай конференцию / Телемост, пригласи …».  
Text-bot scenario `conference`; AVA tool может бить в этот сервис или в mailer calendar+telemost.
