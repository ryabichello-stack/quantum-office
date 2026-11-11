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

# Инструмент: ava-conference (мультипровайдер ВКС)

Создание видеовстречи и email-приглашений по запросу.

Провайдеры: `yandex` (Телемост), `google_meet`, `zoom`, `teams`, `jitsi`.

- Путь: `/opt/ava-conference`
- Порт: `8016`
- Unit: `ava-conference.service`

## API

`GET /api/conferences/providers` — список провайдеров и `configured`.

`POST /api/conferences` с `X-Webhook-Token`:

- `title`, `provider`, `invitees[]`, `when_text`, `message`, `send_invites`

Ответ: `conference_id`, `join_url`, `provider`, `stub`, статус инвайтов.

Без кредов — stub URL (`stub.<provider>.delno.local`); Jitsi работает сразу (публичная комната).

Голосовой/текстовый сценарий: «создай конференцию / Meet / Zoom / Teams / Jitsi, пригласи …».
