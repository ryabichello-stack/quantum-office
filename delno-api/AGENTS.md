# AGENTS.md — delno-api

**Master plan:** [`../docs/DELNO_MASTER_PLAN.md`](../docs/DELNO_MASTER_PLAN.md)

Product vision: `DELNO-site-v23/docs/00_MASTER_SPEC.md`

## Rules
1. All tables include `tenant_id`. LLM tools never accept arbitrary tenant_id.
2. Channel/knowledge/voice/party-lookup access only via `app/adapters/` (HTTP, env URLs).
3. Knowledge search uses **delno-knowledge** `/api/brain/search` with `X-Principal-Id` (see master plan §5.4).
4. Text and voice operator share `POST /v1/operator/chat` (voice = STT before, TTS after).
5. Critical writes use `critical_write` flag + `/v1/operator/confirm` + audit_logs.
6. Do not import Python code from quantum-office or `/opt/ava-*`.

## Add a tool
1. Implement class with `name`, `description`, `critical_write`, `run(db, ctx, **params)`.
2. Register in `app/operator/tools/__init__.py`.
3. Log via `write_audit`.
4. OpenAI function names must match `^[a-zA-Z0-9_-]+$` — registry maps dotted internal names (`web.search`→`web_search`).

## Координация изменений Cursor и Codex
Перед изменением DELNO прочитайте [`../docs/AGENT_CHANGE_REGISTER.md`](../docs/AGENT_CHANGE_REGISTER.md)
(на проде: `/opt/delno/docs/AGENT_CHANGE_REGISTER.md`). После изменения добавьте запись:
дата МСК, автор, файлы, что изменено, как проверено и что осталось.
Не стирайте чужие записи и не записывайте секреты. Держите git-копию и `/opt/delno/docs/` в синхроне.
