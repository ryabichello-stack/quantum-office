# Phase 0 / transitional meta for Second Brain.

- `taxonomy.yaml` — types, visibility, channels, index zones, approved backends
- `service-principals.yaml` — voice-public, voice-office, text-secretary, outreach, cursor-admin
- `acl-roles.yaml` — human/group role hints + import defaults

Canonical Vault + `_meta/` after Phase 1 live in the **private** repository `quantum-brain`.
This directory keeps freeze artifacts and schema stubs so Phase 0 tests run in `quantum-office`
without embedding corporate knowledge into application images.
