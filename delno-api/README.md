# DELNO API

Platform backend for DELNO: multi-tenant foundation, operator (text + voice path), tools, audit.

## Quick start

```bash
cp .env.example .env
docker compose up --build
curl -s http://localhost:8020/v1/health
```

## API (v1)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/health` | Healthcheck |
| POST | `/v1/leads` | Create lead (tenant via `X-Tenant-Slug`) |
| POST | `/v1/operator/chat` | Operator turn (text or voice post-STT) |
| POST | `/v1/operator/voice` | Stub — STT/TTS pipeline later |
| POST | `/v1/operator/confirm` | Confirm critical tool write |
| GET | `/v1/operator/conversations` | Inbox list |

## Tenant context

All requests resolve tenant from header `X-Tenant-Slug` (default: `delno-demo`).

LLM tools never accept `tenant_id` — only `TenantContext` from middleware.

## Architecture

```
app/
├── api/v1/          REST endpoints
├── operator/        Agent loop + tool registry
├── adapters/        HTTP to ava-* (swappable URLs)
├── models/          PostgreSQL, tenant_id on all rows
└── services/        audit, leads
```

## Deploy prod (sketch)

- Port `127.0.0.1:8020`
- nginx: `a.47z.ru/delno-api/` → api
- `KNOWLEDGE_BASE_URL=http://127.0.0.1:8017`

See `deploy/install_prod.sh`.
