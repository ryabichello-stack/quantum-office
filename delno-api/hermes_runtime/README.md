# DELNO Hermes Runtime (Nous) — multiplex pool

Pinned upstream: see `PINNED_VERSION` (`v0.23.1`).

## What this is

**Multiplex pool workers** running **NousResearch/hermes-agent**. Each worker is one
Hermes gateway root (`HERMES_HOME=/data/hermes-profiles/workers/<worker_id>`).
Company cabinets live as named profiles:

```
workers/<worker_id>/profiles/<profile_id>/
```

DELNO API talks to them at `/p/<profile_id>/v1/runs` (OpenAI-compat fallback
`/p/<profile_id>/v1/chat/completions`). Business tools come from DELNO MCP with
**scoped run tokens**. Worker process env keeps `DELNO_MCP_KEY` empty; each
company profile `.env` may hold that tenant's own MCP key for Hermes MCP connect.

Capacity per worker: `HERMES_WORKER_MAX_PROFILES` (default **64**). Two dogfood
workers → up to 128 companies without adding containers. Raise the env or add
workers to the catalog when the pool is full.

## Isolation lab

`docker-compose.hermes.yml` starts **two** multiplex gateways (A on `:18642`, B on `:18643`).

```bash
cd delno-api/hermes_runtime   # or /opt/delno/lab/hermes_runtime
docker compose -f docker-compose.hermes.yml build
API_SERVER_KEY=dev-hermes-key-aaaaaaaa API_SERVER_KEY_B=dev-hermes-key-bbbbbbbb \
  ./scripts/lab_smoke.sh
```

Image build uses **Python 3.14** + `uv sync --frozen --extra messaging`.

## Do not

- Deploy over Asterisk / `trunk_id` telephony
- Set a shared `DELNO_MCP_KEY` on the **worker process** (put per-tenant keys only in `profiles/<id>/.env`)
- `curl | bash` unpinned install on prod
- Point two workers at the **same** `workers/<id>` root (each worker owns its subtree)
