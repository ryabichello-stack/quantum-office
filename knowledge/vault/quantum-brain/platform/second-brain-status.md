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
source: platform#second-brain-status
shard: second-brain-status
---

# Second Brain — статус cutover (2026-07-23)

## Готово на проде

- **B1–B3 / S1:** Postgres + pgvector; `BRAIN_STORE=postgres`; hybrid FTS+vector; sync-pg выполнен.
- **B4 lite:** zone guards (mail/PII never public); PG schemas/views `brain_public` / `brain_private`.
- **G1–G3:** GraphStore + rebuild/expand; graph-in-retrieve; text-bot `expand_office_graph`.
- **S2–S3:** citations в ответах; harness `brain eval` (эталонные кейсы).
- **V1–V4 lite:** vault shards + publish bundle + `export-monolith` → generated `quantum_labs.md`.
- **A2:** Cursor MCP tools.
- **Dual-write:** `BRAIN_DUAL_WRITE` копирует затронутые SQLite rows → Postgres при ingest.
- **A3:** voice `KNOWLEDGE_READ_MODE=brain` (faq-safe primary + legacy fallback).

## Ориентир по объёму корпуса (порядок величин)

Сотни документов, тысячи chunks+embeddings; контакты и почтовые треды проиндексированы; vault FAQ shards активны. Точные цифры: CLI `brain stats` или MCP `kb.ingest_status`.

## Дальше по плану

1. Private GitHub repo `quantum-brain` как внешний канон vault.
2. Postgres-only writes (убрать SQLite как write SoT).
3. Полный physical zone split.
4. Доп. ingest: Bitrix/CRM, meeting notes, Telegram export (опционально).

## Rollback voice

1. В `/opt/ava-knowledge/.env`: `KNOWLEDGE_READ_MODE=legacy`
2. `systemctl restart ava-knowledge`
3. Проверка: `GET /health` → `knowledge_read_mode=legacy`

## Не трогать

Polyhub, Asterisk, Mango, VPN — вне контура Second Brain.
