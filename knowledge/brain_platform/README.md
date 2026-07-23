# knowledge/brain_platform — Second Brain runtime

Deployed with `ava-knowledge` to `/opt/ava-knowledge/brain_platform/`.

## What it does

- **Source of truth** for agents: hybrid search over operational memory
- SQLite + FTS5 + **vector embeddings** with **in-query ACL**
- Hybrid mode: keyword (FTS) + semantic (cosine) fused with **RRF**
- Contacts directory, mail ingest (IMAP), file ingest, FAQ ingest
- HTTP API under **`/api/brain/*`** (legacy `/api/knowledge/*` unchanged for voice)

## Vector stack (v1)

| Piece | Choice |
|-------|--------|
| Embeddings | OpenAI `text-embedding-3-small` (auto) or local hash fallback |
| Vector store | `sqlite_json` (vectors in `chunks.embedding_json`) |
| Search modes | `keyword` \| `semantic` \| `hybrid` (default) |
| Fusion | Reciprocal Rank Fusion (k=60) |
| ACL | Applied in SQL before vector ranking |
| Future | `BRAIN_VECTOR_BACKEND=pgvector` when Postgres is provisioned |

## API

| Route | Purpose |
|-------|---------|
| `GET /api/brain/health` | stats + imap flag |
| `POST /api/brain/search` | `{query, mode: hybrid\|semantic\|keyword, …}` |
| `POST /api/brain/contacts/find` | contact directory |
| `POST /api/brain/threads/list` | correspondence threads |
| `POST /api/brain/ingest/run` | faq + files + mail (+ optional `embed_backfill`) |
| `GET /api/brain/ingest/status` | last ingest markers |

Headers: `X-Principal-Id`, `X-Tenant-Id`, `X-Groups`, `X-User-Id`, `X-Admin`.

```bash
curl -s http://127.0.0.1:8017/api/brain/search \
  -H 'Content-Type: application/json' \
  -H 'X-Principal-Id: service:cursor-admin' \
  -H 'X-Admin: true' -H 'X-User-Id: denis' \
  -d '{"query":"положительная разница ломбард","mode":"hybrid"}'
```

## CLI

```bash
cd /opt/ava-knowledge
PYTHONPATH=. ./venv/bin/python -m brain_platform init-db
PYTHONPATH=. ./venv/bin/python -m brain_platform ingest --sources faq,files,mail
PYTHONPATH=. ./venv/bin/python -m brain_platform embed-backfill --limit 800
PYTHONPATH=. ./venv/bin/python -m brain_platform search "договор Альфа" --mode hybrid --principal service:cursor-admin --admin
```

## Timer

Ingest + embed backfill every ~15 minutes via `ava-brain-ingest.timer`.

## Security

- Default deny; `voice-public` never sees mail/PII/private FAQ
- Secret / explicit local-only docs → local embeddings
- Quarantine on credential scan (no index / no embed)
- Cache/audit keyed by principal (redacted query)

## Postgres / pgvector

Interface is ready (`VectorStore`). Prod v1 uses SQLite JSON vectors for immediate hybrid search.
When Postgres+pgvector is provisioned, set `BRAIN_VECTOR_BACKEND=pgvector` and migrate.
