# DELNO Hermes Runtime (Nous) — single combat pool

Pinned upstream: see `PINNED_VERSION` (`v0.23.1`).

## Architecture (combat)

**One** Hermes gateway container (`delno-hermes-pool`) serves **all** companies.

```
/data/hermes-profiles/workers/pool/          ← HERMES_HOME of the only worker
  config.yaml                                ← multiplex root
  profiles/<profile_id>/                     ← one company cabinet
```

DELNO API calls `/p/<profile_id>/v1/runs`. Isolation = separate profile home +
per-run MCP token + namespaced session — **not** a second container.

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
