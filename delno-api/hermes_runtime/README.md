# DELNO Hermes Runtime (Nous) — Stage 0

Pinned upstream: see `PINNED_VERSION` (`v0.23.1`).

## What this is

Per-tenant container running **NousResearch/hermes-agent** with its own `HERMES_HOME`.
DELNO API talks to it via `/v1/runs` (and OpenAI-compat `/v1/chat/completions` as fallback).
Business tools come from DELNO MCP with **scoped run tokens** — never a shared long-lived key in the model prompt.

## Isolation lab

`docker-compose.hermes.yml` starts **two** runtimes (A on `:18642`, B on `:18643`) for A↛B tests.

## Do not

- Deploy over Asterisk / `trunk_id` telephony
- Enable `gateway.multiplex_profiles` for different MCP catalogs until `#67605` proven
- `curl | bash` unpinned install on prod
