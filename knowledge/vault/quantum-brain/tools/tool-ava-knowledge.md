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
source: tools#ava-knowledge
shard: tool-ava-knowledge
---

# Инструмент: ava-knowledge (Second Brain)

Общая база знаний для голоса и текста.

- Путь: `/opt/ava-knowledge`
- Порт: `8017`
- Unit: `ava-knowledge.service`

## API

- Legacy/compat: `/api/knowledge/query|topics|get|reload|compare`
- Second Brain: `/api/brain/*` (search, contacts, threads, graph, ingest)
- Voice mode: `KNOWLEDGE_READ_MODE=brain|legacy|dual_compare`

Подробности про саму базу — в vault `platform/second-brain-*.md`.

Mailer проксирует knowledge query на этот сервис. Text-bot ходит напрямую.
