# knowledge — общая база знаний Quantum Labs

Один сервис для **голосовой AVA** и **текстового секретаря**.

## Зачем отдельно

Раньше Knowledge жил только как один MD + слабый keyword-поиск внутри `ava-mailer`.
Так сложно:
- расширять темы;
- брать «ровно тарифы / НПД / СБП»;
- дебажить, что увидел бот.

Теперь:
- каталог тем `content/index.yaml` (id + aliases + match по заголовкам);
- **единый FAQ-корпус** `content/quantum_labs.md` = Часть A (продукт) + Часть B (ломбарды);
  на проде файл живёт в `/root/ava/config/knowledge/quantum_labs.md` и **ingest'ится в Second Brain**;
- **Источник правды для агентов — Second Brain** (`/api/brain/*`, SQLite/FTS + ACL);
  legacy `/api/knowledge/*` остаётся compat/fallback (voice), не SoT;
- `content/topics/*.md` — только **доп.** темы, которых ещё нет в `quantum_labs.md`
  (не дублировать ломбарды/FAQ из основного корпуса).

## API

| | |
|--|--|
| health | `GET /health` |
| список тем | `GET /api/knowledge/topics` |
| поиск | `POST /api/knowledge/query` `{"topic":"СБП тарифы"}` или `{"topic_id":"tariffs"}` |
| секция | `POST /api/knowledge/get` `{"id":"..."}` |
| reload | `POST /api/knowledge/reload` |

Ответ `query` совместим с голосом/текстом:

```json
{"ok": true, "topic": "...", "topic_id": "tariffs", "text": "...", "chars": 1234, "matches": [...]}
```

## Прод

| | |
|--|--|
| path | `/opt/ava-knowledge` |
| port | `8017` |
| unit | `ava-knowledge.service` |
| install | `sudo bash scripts/install_prod.sh` |

Голос (AVA) по-прежнему может бить в mailer `:8000/api/knowledge/query` — mailer проксирует сюда.
Текст-бот ходит напрямую: `AVA_KNOWLEDGE_BASE=http://127.0.0.1:8017`.

## Обновление контента

1. Править docx / пересобрать md скриптом в `/root/ava/scripts/build_quantum_knowledge_base.py`
2. Или править `quantum_labs.md` / `content/topics/*.md` + `index.yaml`
3. `curl -X POST http://127.0.0.1:8017/api/knowledge/reload`

## Дальше: Second Brain (реализовано additive)

**Миссия:** операционная память — контакты, почта in/out, файлы, проекты + FAQ.

Runtime: пакет `brain_platform/` + API **`/api/brain/*`** на том же `:8017`.  
Legacy **`/api/knowledge/*`** для voice/text **не менялся** (switch — отдельный approval).

```bash
PYTHONPATH=knowledge pytest knowledge/brain_platform/tests -q
# на проде после deploy:
PYTHONPATH=/opt/ava-knowledge /opt/ava-knowledge/venv/bin/python -m brain_platform ingest --sources faq,files,mail
```

Документы: ADR-0001, OPERATIONAL_MEMORY, `brain_platform/README.md`.

