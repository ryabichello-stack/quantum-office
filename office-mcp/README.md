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
| Telegram / Max | `messenger.status/chats/history/messages/send/chat`, `telegram.send|history`, `max.send|history` |
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

## HTTP gateway для Grok (точка доступа + ключ)

Публичный URL:

```text
https://a.47z.ru/_office_mcp/
```

Auth (один ключ):

```http
Authorization: Bearer <OFFICE_MCP_API_KEY>
```

| Method | Path | Назначение |
|--------|------|------------|
| GET | `/health` | без ключа |
| GET | `/tools` | каталог tools |
| GET | `/openapi-lite` | компактная схема для LLM |
| POST | `/tools/call` | `{"name":"mailru.list","arguments":{"path":"/"}}` |
| POST | `/mcp` | MCP JSON-RPC (initialize / tools/list / tools/call) |

Ключ на проде: `/opt/quantum-office-mcp/.env` → `OFFICE_MCP_API_KEY`  
Сервис: `quantum-office-mcp-gateway.service` (`:8019`).

Пример:

```bash
curl -sS https://a.47z.ru/_office_mcp/tools/call \
  -H "Authorization: Bearer $OFFICE_MCP_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name":"mailru.list","arguments":{"path":"/"}}'
```

## Remote MCP (нет локальных серверов)

MCP-процесс крутится у Cursor/Grok на вашей машине и ходит на **прод по HTTPS**:

| Env | Public URL |
|-----|------------|
| `CONSOLE_BASE` | `https://a.47z.ru/_quantum_console` |
| `OUTREACH_BASE` | `https://a.47z.ru/_ava_outreach` |
| `TEXT_BOT_BASE` | `https://a.47z.ru/_ava_secretary` |
| `FILES_BASE` | `https://a.47z.ru/_ava_files` ← Mail.ru Cloud |
| `AVA_KNOWLEDGE_BASE` | `https://a.47z.ru/_ava_knowledge` |
| `CALENDAR_BASE` | `https://a.47z.ru/_ava_calendar` |
| `CONFERENCE_BASE` | `https://a.47z.ru/_ava_conference` |
| `CAMPAIGN_BASE` | `https://a.47z.ru/_ava_sheets_campaign` |

Конфиг: [`mcp.remote.example.json`](mcp.remote.example.json) / [`mcp.cursor.example.json`](mcp.cursor.example.json).

Сейчас снаружи без site-login уже отвечают: console, outreach, secretary.  
Для Mail.ru / knowledge / calendar / conference / sheets нужен nginx-фрагмент:

[`deploy/nginx-office-api.conf.snippet`](deploy/nginx-office-api.conf.snippet)  
→ вставить в `a.47z.ru` **до** редиректа на `/login`, затем `nginx -t && systemctl reload nginx`.

Токены берутся с прода (`/opt/*/.env`) и кладутся **только** в локальный MCP env клиента — в чат не присылать.

## Запуск

```bash
cd office-mcp
cp .env.example .env   # CONSOLE_TOKEN + WEBHOOK_TOKEN (+ OUTREACH_UI_TOKEN)
# для remote: выставить *_BASE на https://a.47z.ru/_…
PYTHONPATH=. python3 -m quantum_office_mcp
```

## Env

| Переменная | Зачем |
|------------|--------|
| `CONSOLE_TOKEN` | dial, calls, line, scenario |
| `WEBHOOK_TOKEN` | campaign, calendar, conference, files/**mailru**, text-bot |
| `OUTREACH_UI_TOKEN` | **обязателен** для `outreach.*` и `mail.send` (значение из `/opt/ava-outreach/.env`; не подменять `WEBHOOK_TOKEN`) |
| `OUTREACH_TOKEN` | fallback-алиас `OUTREACH_UI_TOKEN` |
| `*_BASE` | URL сервисов (localhost ports по умолчанию) |
| `BRAIN_MCP_*` | ACL Second Brain |

Секреты Mail.ru WebDAV лежат только в `/opt/ava-files/.env` — MCP их не дублирует.

## Тесты

```bash
cd office-mcp && PYTHONPATH=. python3 -m pytest tests -q
```
