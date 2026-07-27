# Structure map (names only — no knowledge bodies)

## Pack tree

```text
quantum-brain-structure/
├── README.md
├── DEPLOY.md
├── STRUCTURE.md
├── .env.example
├── .gitignore
├── docker-compose.yml
├── mcp.cursor.example.json
├── schema/
│   ├── schema_postgres.sql      # pgvector + FTS + graph + zone views
│   └── schema_sqlite.sql        # legacy/dev sqlite
├── systemd/
│   ├── ava-knowledge.service
│   ├── ava-brain-ingest.service
│   └── ava-brain-ingest.timer
├── scripts/
│   ├── init-postgres.sh         # create DB/role + apply schema
│   └── install-structure.sh     # rsync vault/content to /opt/ava-knowledge
├── eval/
│   └── cases.example.yaml
├── content/
│   ├── index.yaml               # topics: []
│   ├── inbox/README.md
│   ├── topics/README.md
│   └── quantum_labs.md          # empty generated placeholder
├── data/                        # runtime only (gitignored)
└── vault/
    ├── README.md
    ├── _templates/NOTE.template.md
    ├── _meta/
    │   ├── taxonomy.yaml
    │   ├── acl-roles.yaml
    │   ├── service-principals.yaml
    │   ├── service-principals.md
    │   ├── shards.yaml
    │   └── README.md
    ├── products/_stub.md
    ├── lombards/_stub.md
    ├── ops/_stub.md
    ├── platform/_stub.md
    ├── meetings/_stub.md
    └── legacy/
```

## Live office vault areas (prod content NOT in this pack)

On a filled deploy, `vault/quantum-brain/` typically contains shards under:

- `products/` — product FAQ
- `lombards/` — vertical playbooks
- `ops/` — AVA ops
- `platform/` — Second Brain self-docs
- `_meta/` — manifests (not ingested as documents)

## App code (not duplicated here)

From `quantum-office/knowledge/`:

- `main.py`, `store.py`, `brain_platform/**`
- `scripts/install_prod.sh`, MCP runner, publish-bundle helpers

## HTTP surface (empty corpus still exposes)

- `GET /health`
- `POST /api/knowledge/query|compare|get|reload`
- `/api/brain/*` (search, graph, ingest, …)

## Env flags (structure)

See `.env.example`: `BRAIN_STORE`, `BRAIN_VAULT_PATH`, `KNOWLEDGE_READ_MODE`, `BRAIN_VOICE_PRINCIPAL`, …
