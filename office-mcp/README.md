# quantum-office MCP

Полноценный **MCP stdio-сервер** для стека Quantum Labs Office.
Grok / Cursor / Claude управляют телефонией, outreach, календарём, мессенджерами,
Second Brain и **Mail.ru Облаком** без сырого HTTP.

Паттерн: JSON-RPC + `Content-Length` (как Second Brain MCP), без внешних зависимостей.

## Покрытие

| Домен | Tools |
|-------|--------|
| Ops | `office.health`, `office.status` |
| Телефония входящая | `telephony.inbound_line_*`, `telephony.scenario_*` |
| Телефония исходящая | `telephony.assign_task`, `telephony.dial`, `telephony.callback`, `telephony.calls_*` |
| Sheets-кампания | `campaign.*` |
| Second Brain | `kb.search`, `kb.get`, `kb.related`, `kb.find_contact`, `kb.list_threads`, `kb.ingest_status` |
| Legacy knowledge | `knowledge.query`, `knowledge.topics`, `knowledge.get` |
| Календарь / Телемост | `calendar.*`, `conference.create` |
| Telegram / Max | `messenger.*`, `telegram.send`, `max.send` |
| Outreach email | `outreach.dashboard/outbox/send_*/packs/...` |
| **Mail.ru Облако** | `mailru.list`, `mailru.search`, `mailru.read`, `mailru.fetch`, `mailru.send`, `mailru.status` |
| Файлы (общее) | `files.*` (default `source=mailru`) |

### Mail.ru Cloud (данные компаний)

Сервис `ava-files` (`:8015`) ходит в Облако по WebDAV (`MAILRU_WEBDAV_*` в `/opt/ava-files/.env`).

Из MCP:

```json
{"name":"mailru.list","arguments":{"path":"/"}}
{"name":"mailru.search","arguments":{"query":"договор","path":"/"}}
{"name":"mailru.read","arguments":{"path":"/Клиенты/заметка.txt"}}
```

Текстовые файлы (md/txt/csv/…) читаются в `mailru.read`. PDF/Office — через `mailru.send` (email/Telegram), не как текст.

### Пример задачи на обзвон

```json
{
  "name": "telephony.assign_task",
  "arguments": {
    "phone": "+79001234567",
    "company": "ООО Пример",
    "goal": "найти ЛПР по выплатам и записать на консультацию",
    "find_lpr": true
  }
}
```

## Запуск

```bash
cd office-mcp
cp .env.example .env   # CONSOLE_TOKEN + WEBHOOK_TOKEN (+ OUTREACH_UI_TOKEN)
chmod +x scripts/run_cursor_mcp.sh
./scripts/run_cursor_mcp.sh
```

Cursor: `mcp.cursor.example.json` → подставить токены. Прод-путь: `/opt/quantum-office-mcp`.

## Env

| Переменная | Зачем |
|------------|--------|
| `CONSOLE_TOKEN` | dial, calls, line, scenario |
| `WEBHOOK_TOKEN` | campaign, calendar, conference, files/**mailru**, text-bot |
| `OUTREACH_UI_TOKEN` | outreach API (можно тем же значением в `WEBHOOK_TOKEN` / `OUTREACH_TOKEN`) |
| `*_BASE` | URL сервисов (localhost ports по умолчанию) |
| `BRAIN_MCP_*` | ACL Second Brain |

Секреты Mail.ru WebDAV лежат только в `/opt/ava-files/.env` — MCP их не дублирует.

## Тесты

```bash
cd office-mcp && PYTHONPATH=. python3 -m pytest tests -q
```
