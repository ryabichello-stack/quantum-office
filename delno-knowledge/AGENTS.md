# delno-knowledge — Second Brain fork

Ported from `/opt/ava-knowledge/brain_platform/` (prod).

- API: `/api/brain/*` (search, get, ingest, contacts, graph)
- ACL: `X-Principal-Id`, `X-Tenant-Id` headers — default deny
- Local dev: `docker compose up` or `uvicorn main:app --port 8021`
- Init DB: `PYTHONPATH=. python -m brain_platform init-db`
- Seed demo vault: `PYTHONPATH=. python -m brain_platform seed-demo --verify`
- Docker entrypoint runs init-db + seed-demo on start (idempotent)

Master plan: `../docs/DELNO_MASTER_PLAN.md`
