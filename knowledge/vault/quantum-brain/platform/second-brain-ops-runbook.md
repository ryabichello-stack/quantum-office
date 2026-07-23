---
tenant_id: quantum-labs
visibility: company
classification:
  level: internal
  contains_personal_data: false
channels: [office-assistant]
ai_processing:
  allow_external_embed: true
publication:
  manual_approve: false
source: platform#second-brain-ops-runbook
shard: second-brain-ops-runbook
---

# Second Brain — операционный runbook

## Сервисы

| Сервис | Порт | Роль |
|--------|------|------|
| ava-knowledge | 8017 | Second Brain + legacy knowledge API |
| ava-text-bot | 8011 | Telegram secretary, brain tools |
| ava-mailer | 8000 | почта/oauth; proxy knowledge query → 8017 |

## Типовые операции

### Переиндексировать vault

1. Обновить файлы в `/opt/ava-knowledge/vault/quantum-brain/`
2. `cd /opt/ava-knowledge && ./venv/bin/python -m brain_platform ingest --sources vault`
3. При новых текстах: `./venv/bin/python -m brain_platform embed-backfill --limit 2000`
4. Smoke: `brain search "Second Brain" --principal service:voice-office`

### Проверить eval качества

`./venv/bin/python -m brain_platform eval` — смотреть pass rate (порог `BRAIN_EVAL_MIN_PASS_RATE`).

### Пересобрать граф

`./venv/bin/python -m brain_platform graph rebuild`

### Voice rollback

`KNOWLEDGE_READ_MODE=legacy` в `.env` → `systemctl restart ava-knowledge`.

### Снова включить brain primary

`KNOWLEDGE_READ_MODE=brain` → restart → `/health` показывает `knowledge_read_mode=brain`.

## Env (без секретов)

Ключевые флаги: `BRAIN_ENABLED`, `BRAIN_STORE=postgres`, `BRAIN_SEARCH_MODE=hybrid`, `BRAIN_GRAPH_IN_RETRIEVE`, `BRAIN_DUAL_WRITE`, `BRAIN_VAULT_PATH`, `KNOWLEDGE_READ_MODE`, `BRAIN_VOICE_PRINCIPAL`.

Секреты (токены, DATABASE_URL, OPENAI_API_KEY, IMAP пароли) хранятся только в `.env`, не в vault и не в ответах агентам.

## Диагностика

- `/api/knowledge/compare` — сравнить legacy vs brain на одном запросе.
- `journalctl -u ava-knowledge -n 50` — логи сервиса.
- `brain stats` — counts documents/chunks/contacts/emails.
