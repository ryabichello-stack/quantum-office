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
source: platform#second-brain-faq
shard: second-brain-faq
---

# Second Brain — частые вопросы про базу знаний

### Вопрос: Что такое Second Brain / база знаний Quantum Labs?

Ответ: Единый поисковый корпус и API для голоса AVA, текстового секретаря и Cursor. Ищет по FAQ, vault, файлам и (для authorized principals) почте/контактам с ACL и цитатами.

### Вопрос: Откуда берутся ответы голоса AVA?

Ответ: При `KNOWLEDGE_READ_MODE=brain` — из Second Brain с principal `service:voice-office` (только assistant-safe). Если мозг пуст или ошибка — fallback на legacy markdown. Откат: режим `legacy`.

### Вопрос: Видит ли голос почту клиентов?

Ответ: Нет. Voice-office не получает mail/thread документы; типы email/mail/thread дополнительно отфильтровываются на voice path.

### Вопрос: Где канонические FAQ?

Ответ: В vault `quantum-brain` (products, lombards, ops, platform). Их ingest’ят командой `brain ingest --sources vault`. Monolith `quantum_labs.md` может быть сгенерирован из шардов.

### Вопрос: Как устроен поиск?

Ответ: Hybrid по умолчанию: keyword FTS + semantic embeddings (pgvector) + RRF; опционально подмешивается граф связанных сущностей.

### Вопрос: Что такое граф знаний?

Ответ: Связи людей, компаний, тредов и документов. Пример: запрос «Парцуф» может раскрыть связь works_at с компанией/банком через `graph expand`.

### Вопрос: Как Cursor ходит в базу?

Ответ: Через MCP tools (`kb.search`, `kb.get`, `kb.related`, контакты/треды) или REST `/api/brain/*` с нужным principal.

### Вопрос: Как добавить новые знания?

Ответ: Добавить markdown шард в vault с frontmatter → `brain ingest --sources vault` (и embed при необходимости). Почта/файлы — через соответствующие ingest sources. Не класть секреты и токены в текст.

### Вопрос: Где смотреть здоровье сервиса?

Ответ: `GET http://127.0.0.1:8017/health` у `ava-knowledge`; поле `knowledge_read_mode` показывает текущий voice-режим.

### Вопрос: Что ещё не сделано?

Ответ: Private GitHub `quantum-brain`, полный отказ от SQLite write SoT, полный physical zone split, CRM/meetings ingest.
