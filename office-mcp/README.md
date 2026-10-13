# quantum-office MCP

Полноценный **MCP stdio-сервер** для стека Quantum Labs Office: Grok / Cursor / Claude
могут ставить исходящие звонки, смотреть транскрипты, крутить Sheets-кампанию,
календарь, Second Brain и outreach — без прямого HTTP.

Паттерн тот же, что у Second Brain MCP (`knowledge/brain_platform/mcp`): JSON-RPC
поверх stdio, `Content-Length`, **без внешних зависимостей**.

## Tools

| Tool | Назначение |
|------|------------|
| `office.health` | `/health` всех office-сервисов |
| `office.status` | статус пульта (Asterisk, units, линия) |
| `line.get` / `line.set` | автолиния входящих |
| `calls.assign_task` | **главный для sales/Grok**: задача → playbook → dial |
| `calls.dial` | сырой `POST /api/outbound/dial` |
| `calls.callback` | Mango callback originate |
| `calls.list` / `calls.get` | история и полный транскрипт |
| `calls.list_tools` | каталог in-call tools |
| `campaign.*` | start/stop/status/preview/results/script |
| `kb.search` / `kb.get` | Second Brain |
| `calendar.check` / `suggest` / `create` | CalDAV |
| `outreach.dashboard` / `status` / `packs` / `outbox` | email outreach |

### Пример задачи на обзвон

```json
{
  "name": "calls.assign_task",
  "arguments": {
    "phone": "+79001234567",
    "company": "ООО Пример",
    "contact_name": "Иван",
    "goal": "найти ЛПР по выплатам и записать на консультацию",
    "product": "массовые выплаты Quantum Labs",
    "notes": "Клиент из таблицы ломбардов, интересовался комиссией",
    "find_lpr": true,
    "book_meeting": true
  }
}
```

## Запуск

```bash
cd office-mcp
cp .env.example .env   # заполнить CONSOLE_TOKEN / WEBHOOK_TOKEN
chmod +x scripts/run_cursor_mcp.sh
./scripts/run_cursor_mcp.sh
```

Или: `PYTHONPATH=. python3 -m quantum_office_mcp`

### Cursor

Скопируйте `mcp.cursor.example.json` в MCP-конфиг Cursor и подставьте токены.
На проде удобно держать код в `/opt/quantum-office-mcp` (или рядом с console).

### Env

| Переменная | Зачем |
|------------|--------|
| `CONSOLE_TOKEN` | Console API (dial, calls, status, line) |
| `WEBHOOK_TOKEN` | campaign / calendar / outreach |
| `CONSOLE_BASE` и др. `*_BASE` | URL сервисов (по умолчанию localhost ports) |
| `BRAIN_MCP_*` | ACL для Second Brain |

Секреты только в `.env` на хосте (mode 600), в git не коммитить.

## Тесты

```bash
cd office-mcp
PYTHONPATH=. python3 -m pytest tests -q
```

## Связь с brain MCP

Отдельный `quantum-brain` MCP (`knowledge/`) остаётся для глубокой работы с vault.
Этот пакет **дублирует** `kb.search` / `kb.get` для удобства одного сервера у sales-бота.
