# Quantum Brain vault (V1 scaffold)

Canonical markdown knowledge for Quantum Labs Second Brain.

This tree is the future SoT for FAQ/playbooks. Until the private
`quantum-brain` GitHub repo is created and wired, prod still ingests from
`/root/ava/config/knowledge/quantum_labs.md` + local `knowledge/content/`.

## Layout

```
vault/quantum-brain/
  _meta/           taxonomy, ACL roles, service principals
  products/        product FAQ shards
  meetings/        meeting notes (future)
  ops/             runbooks
  lombards/        vertical playbooks
```

## Frontmatter (required on every note)

```yaml
---
tenant_id: quantum-labs
visibility: company          # public only with publication.manual_approve
classification:
  level: internal
  contains_personal_data: false
channels: [office-assistant]
ai_processing:
  allow_external_embed: true
publication:
  manual_approve: false
source: legacy#anchor
---
```

Public zone content must set `visibility: public` **and** `publication.manual_approve: true`.
