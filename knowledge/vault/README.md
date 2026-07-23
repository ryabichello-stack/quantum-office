# Knowledge Vault (Second Brain) — preparatory

Статус: **подготовка к миграции**. Платформа Second Brain **не реализована** до Accept ADR-0001.

- `legacy/` — замороженный снимок текущего корпуса (не удалять)
- `_meta/` — сюда попадут taxonomy/acl после Phase 1
- Целевая архитектура: `docs/architecture/ADR-0001-second-brain.md`

Runtime агентов пока читает `knowledge/content/` + `/root/ava/config/knowledge/quantum_labs.md` через `ava-knowledge :8017`.
