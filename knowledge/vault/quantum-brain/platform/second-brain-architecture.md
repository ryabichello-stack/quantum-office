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
source: platform#second-brain-architecture
shard: second-brain-architecture
---

# Second Brain — архитектура и слои

## Схема

```text
SOURCES                VAULT (канон)            INDEXES (производные)
───────                ───────────              ─────────────────────
FAQ / vault MD   ┐
Mail IMAP        ├──►  quantum-brain shards  ├──►  Postgres FTS
Server files     │     + frontmatter ACL     ├──►  pgvector HNSW
Meetings/CRM*    ┘                           ├──►  Graph entities/edges
                                             └──►  zones public|private

                              │
                              ▼
                    Search Gateway (hybrid + ACL)
                              │
              voice · text-bot · Cursor MCP · outreach
```

\* CRM/Bitrix и meeting notes — в плане ingest, ещё не основной поток.

## Поиск

- Режимы: `keyword` | `semantic` | `hybrid` (по умолчанию hybrid).
- Hybrid: FTS + embeddings + RRF; опционально graph-in-retrieve (`BRAIN_GRAPH_IN_RETRIEVE`).
- Ответы содержат citations (источник/заголовок).
- ACL фильтрует **внутри** запроса (principal → visibility/channels).

## База данных

- Postgres 16 + расширения `vector` (pgvector) и `pg_trgm`.
- БД: `quantum_brain`, приложение под ролью app-user.
- Таблицы: documents, chunks (+ embedding vector), contacts, emails, threads, files, entities, edges, audit/ingest meta.
- Dual-write: при `BRAIN_DUAL_WRITE` изменения из SQLite-пути копируются в Postgres.
- Ideal next: Postgres-only writes (убрать SQLite как write SoT).

## Граф знаний

- Сущности: person, company, project, thread_topic, product, document.
- Рёбра: works_at, participant_of, mentions, about_company, related_to и др.
- API: `POST /api/brain/graph/expand`; CLI: `brain graph expand`, `brain graph rebuild`.
- Text-bot: tool `expand_office_graph`.

## Vault

Дерево `vault/quantum-brain/`:

- `products/` — продукт и короткий FAQ
- `lombards/` — вертикаль ломбардов
- `ops/` — runbooks / AVA ops
- `platform/` — документы про саму базу знаний
- `_meta/` — манифесты (не ingest’ятся в индекс)

Каждый шард: YAML frontmatter (tenant, visibility, classification, channels, publication).

## Zones и безопасность

- Логические зоны: private (по умолчанию) / public (только после manual approve).
- B4 lite: zone guards — mail/PII никогда не в public; PG views `brain_public` / `brain_private`.
- Safety scan на ingest; credentials → quarantine.
- Default deny для неизвестных principals.
