# Addendum к плану Codex (зафиксировано перед Stage 0)

1. **Pin:** `hermes-agent` **v0.23.1** (`delno-api/hermes_runtime/PINNED_VERSION`). Bump только после re-test isolation.
2. **Self-setup policy:** агент может менять `SOUL.md`, `skills/`, `cron/`, `memories/`; **нельзя** менять `mcp_servers.url`, vault, egress, `.env` секреты (см. provision `self_setup_policy`).
3. **Telephony:** inbound AVA / `trunk_id` routing **вне** этого runtime; не overwrite.
4. **Feature flag:** `hermes_nous_runtime` — кабинет/API Nous только когда enabled; иначе DIY fallback.
