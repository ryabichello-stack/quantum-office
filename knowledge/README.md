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
- корпус `content/quantum_labs.md` (на проде читается живой `/root/ava/config/knowledge/quantum_labs.md`);
- можно добавлять файлы в `content/topics/*.md` без ломки всего корпуса.

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

## Дальше: Second Brain

Текущий сервис — совместимый FAQ/keyword слой для агентов.  
ADR-0001 **Accepted** (security amendments). Код платформы: `platform/` (Phase 0 schemas + negative-security tests).  
Канонический Vault → отдельный private repo **`quantum-brain`**. Production `:8017` в Phase 0 **не меняется**; switch voice/text — только с отдельным approval.

- [`docs/architecture/ADR-0001-second-brain.md`](../docs/architecture/ADR-0001-second-brain.md)
- [`docs/architecture/SECOND_BRAIN_ROADMAP.md`](../docs/architecture/SECOND_BRAIN_ROADMAP.md)
- [`platform/README.md`](./platform/README.md)

```bash
PYTHONPATH=. pytest knowledge/platform/tests -q
```

