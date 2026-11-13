# DELNO Hermes Runtime (Nous) — Stage 0

Pinned upstream: see `PINNED_VERSION` (`v0.23.1`).

## What this is

Per-tenant container running **NousResearch/hermes-agent** with its own `HERMES_HOME`.
DELNO API talks to it via `/v1/runs` (and OpenAI-compat `/v1/chat/completions` as fallback).
Business tools come from DELNO MCP with **scoped run tokens** — never a shared long-lived key in the model prompt.

## Isolation lab

`docker-compose.hermes.yml` starts **two** runtimes (A on `:18642`, B on `:18643`) for A↛B tests.

```bash
# On dogfood host only — never overwrite prod telephony
cd /opt/delno/lab/hermes_runtime   # or delno-api/hermes_runtime
docker compose -f docker-compose.hermes.yml build
API_SERVER_KEY=lab-hermes-key-aaaa API_SERVER_KEY_B=lab-hermes-key-bbbb \
  ./scripts/lab_smoke.sh
```

Image build uses **Python 3.14** + `uv sync --frozen --extra messaging` (plain pip fails on Pillow/browser-harness overrides; aiohttp required for API server).

Without provider keys, `/v1/models` still responds; `/v1/chat/completions` returns a structured `agent_error` (expected until `OPENAI_API_KEY` / Nous auth is set per tenant).

## Do not

- Deploy over Asterisk / `trunk_id` telephony
- Enable `gateway.multiplex_profiles` for different MCP catalogs until `#67605` proven
- `curl | bash` unpinned install on prod
