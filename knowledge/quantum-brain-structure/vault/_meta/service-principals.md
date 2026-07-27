# Service principals (ACL) — structure reference

| Principal | Access |
|-----------|--------|
| service:voice-public | public zone only |
| service:voice-office | assistant-safe channels |
| service:text-secretary | assistant-safe + owner memory tools |
| service:text-guest | assistant-safe FAQ |
| service:outreach | public + team:sales |
| service:cursor-admin | all (personal admin auth) |

Canonical machine-readable copy: `service-principals.yaml` (this folder is `_meta` — not ingested as vault docs).
