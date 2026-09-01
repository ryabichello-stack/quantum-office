# AGENTS.md — delno-api

**Master plan:** [`../docs/DELNO_MASTER_PLAN.md`](../docs/DELNO_MASTER_PLAN.md)

Product vision: `DELNO-site-v23/docs/00_MASTER_SPEC.md`

## Rules
1. All tables include `tenant_id`. LLM tools never accept arbitrary tenant_id.
2. Channel/knowledge/voice access only via `app/adapters/` (HTTP, env URLs).
3. Knowledge search uses **delno-knowledge** `/api/brain/search` with `X-Principal-Id` (see master plan §5.4).
4. Text and voice operator share `POST /v1/operator/chat` (voice = STT before, TTS after).
5. Critical writes use `critical_write` flag + `/v1/operator/confirm` + audit_logs.
6. Do not import Python code from quantum-office or `/opt/ava-*`.

## Add a tool
1. Implement class with `name`, `description`, `critical_write`, `run(db, ctx, **params)`.
2. Register in `app/operator/tools/__init__.py`.
3. Log via `write_audit`.
