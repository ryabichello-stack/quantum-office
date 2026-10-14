# Что умеет quantum-office MCP (и почему «ничего не работает»)

## Письма

| Инструмент | Назначение |
|------------|------------|
| **`mail.send`** | Текстовое/HTML письмо с `office@` или `cold` |
| **`mailru.send`** | (1) файл с Облака **или** (2) то же текстовое письмо: `to`+`subject`+`body` без `path` |
| `outreach.send_one` / `send_batch` | Рассылка из outbox; нужен cold SMTP (`OUTREACH_COLD_*`) |

Если ассистент «не видит» `mail.send` — обновить список tools / перезапустить MCP gateway.  
`mailru.send` с `body` работает как запасной путь.

## Пакеты рассылок

- `outreach.packs` — список + `subject` / `plain_preview`
- **`outreach.pack_get`** — полный `plain` / `html` по шагам (сюда смотреть за текстом)

## База знаний

- `kb.search` → Second Brain; при lock/timeout → fallback `knowledge.query`
- `knowledge.get("audience")` — каталог тем

## Bitrix sync

Ошибка `401 ACCESS_DENIED: REST is available only by subscription` — у портала Bitrix24 **нет активного REST/подписки**, не «протухший ключ» в узком смысле.  
Нужно продлить Bitrix24 (или выдать новый inbound webhook на тарифе с REST) и обновить `BITRIX_WEBHOOK_URL` в `/opt/ava-outreach/.env`.

## Календарь / встречи / Облако

- `calendar.create` / `suggest` / `check`
- `conference.create` (Телемост)
- `files.upload` / `mailru.upload` — сохранить на Облако
- `files.send` / `mailru.send`+path — отправить файл с Облака
