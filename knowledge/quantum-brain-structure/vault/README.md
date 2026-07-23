# Quantum Brain vault — structure scaffold (no knowledge content)

Canonical layout for FAQ/playbooks. Fill stubs before ingest.

## Layout

```
vault/quantum-brain/   (deployed path)
  _meta/           taxonomy, ACL, principals, shards manifest (not ingested as docs)
  _templates/      NOTE.template.md
  products/        product FAQ shards
  lombards/        vertical playbooks
  ops/             runbooks
  platform/        meta about the knowledge system itself
  meetings/        meeting notes
  legacy/          optional import staging
```

## Frontmatter

See `_templates/NOTE.template.md`. Public requires `publication.manual_approve: true`.
