# knowledge/brain_platform — Second Brain runtime

Deployed with `ava-knowledge` to `/opt/ava-knowledge/brain_platform/`.

## What it does

- SQLite + FTS5 corpus with **in-query ACL** (tenant, visibility, allow lists, zones)
- Contacts directory (email/phone/title/company)
- Mail ingest (IMAP INBOX + Sent) → threads + contacts + searchable docs
- File ingest (allowlisted server roots)
- Legacy FAQ ingest → `office-assistant` channel (not voice-public)
- HTTP API under **`/api/brain/*`** (legacy `/api/knowledge/*` unchanged)

## API

| Route | Purpose |
|-------|---------|
| `GET /api/brain/health` | stats + imap flag |
| `POST /api/brain/search` | ACL search / RAG assemble |
| `POST /api/brain/contacts/find` | contact directory |
| `POST /api/brain/threads/list` | correspondence threads |
| `POST /api/brain/ingest/run` | faq + files + mail |
| `GET /api/brain/ingest/status` | last ingest markers |

Headers: `X-Principal-Id`, `X-Tenant-Id`, `X-Groups`, `X-User-Id`, `X-Admin`.

Examples:

```bash
curl -s http://127.0.0.1:8017/api/brain/search \
  -H 'Content-Type: application/json' \
  -H 'X-Principal-Id: service:cursor-admin' \
  -H 'X-Admin: true' -H 'X-User-Id: denis' \
  -d '{"query":"комиссия СБП"}'

curl -s http://127.0.0.1:8017/api/brain/ingest/run \
  -H 'Content-Type: application/json' \
  -H 'X-Principal-Id: service:cursor-admin' -H 'X-Admin: true' -H 'X-User-Id: denis' \
  -d '{"sources":["faq","files","mail"]}'
```

## CLI

```bash
cd /opt/ava-knowledge
PYTHONPATH=. ./venv/bin/python -m brain_platform init-db
PYTHONPATH=. ./venv/bin/python -m brain_platform ingest --sources faq,files,mail
PYTHONPATH=. ./venv/bin/python -m brain_platform search "договор" --principal service:cursor-admin --admin
PYTHONPATH=. ./venv/bin/python -m brain_platform contacts --q office
```

## Timer

```bash
cp ava-brain-ingest.service ava-brain-ingest.timer /etc/systemd/system/
systemctl enable --now ava-brain-ingest.timer
```

## Security

- Default deny; `voice-public` never sees mail/PII/private FAQ
- Quarantine on credential scan
- Cache/audit keyed by principal (redacted query)
- Voice/text **legacy** tools still use `/api/knowledge/*` until separate approval to switch

## Postgres / pgvector

v1 ships on SQLite+FTS for immediate deploy. Schema column names match ADR; migrate to Postgres+pgvector behind `VectorStore` when DB is provisioned.
