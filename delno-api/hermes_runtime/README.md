# DELNO Hermes Runtime (Nous) — single combat pool

Pinned upstream: see `PINNED_VERSION` (`v0.23.2`). The Gate 1 image applies an
exact-revision patch at build time. It refuses to build if upstream changed.

## Architecture (combat)

**One** Hermes gateway container (`delno-hermes-pool`) serves **all** companies.

```
/data/hermes-profiles/workers/pool/          ← HERMES_HOME of the only worker
  config.yaml                                ← multiplex root
  profiles/<profile_id>/                     ← one company cabinet
```

DELNO API calls `/p/<profile_id>/v1/runs`. Isolation = separate profile home +
per-run MCP token + namespaced session — **not** a second container.

Gate 1 patch (activated only with `DELNO_MCP_RUN_SCOPE_ENABLED=1` on the pool):
the API server binds `X-Delno-Run-Token`, the DELNO run ID, and
the selected profile to a `ContextVar` for one turn. `delno_office` business
tool calls go directly to the internal DELNO MCP endpoint with those headers.
The existing MCP connection uses a profile key for schema discovery only when
`DELNO_MCP_LEGACY_CATALOG_ONLY=1`; business calls through that key fail. A
missing run context fails closed. Other MCP servers are unchanged.

Migration flags on **DELNO API** (all disabled by default):

1. `DELNO_MCP_REQUIRE_RUN_BINDING=1`: each run token must match a live server
   binding, including tenant, actor, grants, agent and profile.
2. `DELNO_MCP_LEGACY_CATALOG_ONLY=1`: old per-profile key can list schemas but
   cannot call business tools.
3. `DELNO_MCP_DENY_LEGACY_KEY=1`: with catalog-only enabled, reject all other
   legacy key usage. Do not set these in production until the patched pool has
   passed real two-tenant E2E and the rollback is rehearsed.

Capacity: `HERMES_WORKER_MAX_PROFILES` (default **256**). Raise the env when
approaching the ceiling. A second worker is optional scale-out only
(`HERMES_ENABLE_EXTRA_WORKERS=1`) — not part of the default combat topology.

## Lab

```bash
cd delno-api/hermes_runtime
docker compose -f docker-compose.hermes.yml up --build -d
API_SERVER_KEY=dev-hermes-key-aaaaaaaa ./scripts/lab_smoke.sh
```

## Do not

- Deploy over Asterisk / `trunk_id` telephony
- Put a shared `DELNO_MCP_KEY` on the **worker process** (per-tenant keys only in `profiles/<id>/.env`)
- Bring back dogfood A/B containers “just in case”
- `curl | bash` unpinned install on prod
