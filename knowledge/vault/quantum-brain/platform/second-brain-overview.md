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
source: platform#second-brain-overview
shard: second-brain-overview
---

# Second Brain — что это

Second Brain (квантовый Second Brain / ava-knowledge) — единая рабочая база знаний Quantum Labs для голоса AVA, текстового секретаря и Cursor.

Цель: любой рабочий вопрос → один поиск → ответ с цитатой и правильным ACL. Корпус растёт через ingest; дублей нет; markdown/vault — канон, индексы производные.

## Что внутри корпуса

1. FAQ и продукт — шарды vault `quantum-brain` (Quantum Payouts, ломбарды, короткие ответы, ops AVA).
2. Почта — IMAP входящие/исходящие треды и контакты (только для authorized principals, не для voice-public).
3. Файлы сервера — allowlisted roots (assets, content).
4. Граф связей — люди ↔ компании ↔ треды ↔ документы (например, кто с кем работает).
5. Мета-документы про саму базу (этот раздел `platform/`).

## Источник истины

- Для агентов и office memory: Second Brain API `/api/brain/*` и поиск через BrainSearch.
- Для голоса (после cutover A3): `/api/knowledge/query` в режиме `KNOWLEDGE_READ_MODE=brain` читает Second Brain с ACL `service:voice-office`, при пустом ответе — fallback на legacy markdown.
- Vault `knowledge/vault/quantum-brain/` — канонические FAQ/playbook шарды; `content/quantum_labs.md` может быть сгенерирован из vault (`export-monolith`).

## Что Second Brain не делает

- Не трогает Polyhub / Asterisk / Mango / VPN.
- Не отдаёт почту и PII в public/voice-public канал.
- Не публикует `public` автоматически — только manual publish approval.

## Сервис на проде

- Сервис: `ava-knowledge` (порт `8017`).
- Text-bot: `ava-text-bot` (`8011`) ходит в brain tools.
- Mailer: проксирует `/api/knowledge/query` на `ava-knowledge`.
- Хранилище поиска: Postgres + pgvector (`BRAIN_STORE=postgres`); SQLite ещё участвует в dual-write при ingest.
