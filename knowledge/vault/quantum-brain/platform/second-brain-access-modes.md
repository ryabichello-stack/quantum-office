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
source: platform#second-brain-access-modes
shard: second-brain-access-modes
---

# Second Brain — доступ, режимы и API

## Service principals (ACL)

| Principal | Доступ |
|-----------|--------|
| service:voice-public | только public zone |
| service:voice-office | assistant-safe канал (`office-assistant`) |
| service:text-secretary | assistant-safe + owner memory tools |
| service:text-guest | assistant-safe FAQ |
| service:outreach | public + team:sales |
| service:cursor-admin | полный admin доступ (личный admin auth) |

Voice path (A3) использует `BRAIN_VOICE_PRINCIPAL=service:voice-office`.  
Из voice-ответов дополнительно вычищаются типы `email` / `mail` / `thread`.

## KNOWLEDGE_READ_MODE (голос / compat)

Переменная сервиса `ava-knowledge`:

| Значение | Поведение |
|----------|-----------|
| `legacy` | текст из markdown SoT (rollback) |
| `dual_compare` | legacy текст + блок `brain_compare` |
| `brain` | Second Brain primary (faq-safe); при пусто/ошибке — legacy fallback |

Прод (cutover A3): `KNOWLEDGE_READ_MODE=brain`.  
Мгновенный откат: поставить `legacy` и перезапустить `ava-knowledge`.

Mailer не имеет отдельного флага — проксирует `/api/knowledge/query` на `ava-knowledge` и наследует режим.

## Основные HTTP API

Сервис `ava-knowledge` (`:8017`):

- `GET /health` — статус, в т.ч. `knowledge_read_mode`
- `POST /api/knowledge/query` — voice/compat запрос
- `POST /api/knowledge/compare` — явный legacy vs brain (диагностика)
- `POST /api/knowledge/get` — секция legacy markdown по id
- `POST /api/knowledge/reload` — перечитать markdown
- `/api/brain/*` — search, get, contacts, threads, ingest, graph expand/rebuild

## Cursor MCP

Stdio MCP tools: `kb.search`, `kb.get`, `kb.related`, `kb.ingest_status`, `kb.find_contact`, `kb.list_threads`.  
Пример конфига: `mcp.cursor.example.json`, запуск `scripts/run_cursor_mcp.sh`.

## CLI

Из каталога knowledge: `python -m brain_platform …`

Полезные команды: `ingest`, `search`, `stats`, `eval`, `graph expand|rebuild`, `sync-pg`, `embed-backfill`, `publish-bundle`, `export-monolith`, `shard-vault`.

## Text-bot

`ava-text-bot` использует brain tools (поиск, контакты, граф) как SoT для office memory; knowledge_base указывает на `http://127.0.0.1:8017`.
