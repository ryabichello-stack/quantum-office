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
source: platform#second-brain-plan-stages
shard: second-brain-plan-stages
---

# Second Brain — этапы плана до идеала

Связанные документы в git: `docs/architecture/SECOND_BRAIN_IDEAL_PLAN.md`, `ADR-0001-second-brain.md`, `SECOND_BRAIN_ROADMAP.md`, `OPERATIONAL_MEMORY.md`.

## База данных (B)

- **B1** Postgres + pgvector на проде — готово.
- **B2** Схема documents/chunks/contacts/graph/audit — готово.
- **B3** Миграция SQLite→Postgres (sync-pg, counts) — готово; dual-write период.
- **B4** Physical zones — lite (guards + views); полный split ещё впереди.

## Поиск (S)

- **S1** Hybrid на pgvector HNSW — готово.
- **S2** Citations — готово.
- **S3** Eval harness — готово.

## Граф (G)

- **G1** GraphStore таблицы — готово.
- **G2** Rebuild из contacts/threads — готово.
- **G3** Graph-in-retrieve — готово.

## Vault (V)

- **V1–V2** Шарды + frontmatter — готово (lite в office-репо).
- **V3** Publish bundle — готово.
- **V4** export-monolith → generated FAQ md — готово.
- Private GitHub `quantum-brain` — ещё нет.

## Агенты (A)

- **A2** Cursor MCP — готово.
- **A3** Voice switch `KNOWLEDGE_READ_MODE=brain` — готово на проде (с rollback на legacy).

## Критерии «идеально»

- [x] Hybrid FTS+vector(+graph) с ACL
- [x] Граф person–company–thread–doc
- [x] Ingest faq/files/mail/vault без молчаливой потери
- [x] Eval + citations
- [x] Voice+text+Cursor на brain (voice через режим brain)
- [ ] Postgres-only write store
- [ ] Vault git repo = внешний SoT
- [ ] Нет dual path `/root/ava` vs git vs индекс
- [ ] Полный physical zone split
