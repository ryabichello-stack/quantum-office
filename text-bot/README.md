# Quantum Labs ИИ-секретарь (channel-agnostic)

Ядро: `secretary.py` — диалог + память + tools + **сценарии поведения**.  
Каналы: Telegram + HTTP API (и дальше Bitrix/web).

## Кто вы для бота

| | |
|--|--|
| Владелец | `SECRETARY_OWNER_IDS` (Telegram chat_id) → личный секретарь |
| Гость | все остальные → офисный секретарь |

Пока owners не заданы, Telegram по умолчанию считается owner (`SECRETARY_TELEGRAM_DEFAULT_OWNER=true`).

## Сценарии

Файл: `scenarios.yaml`

| id | для кого | когда |
|----|----------|--------|
| `secretary` | owner | общий личный секретарь (default) |
| `calendar` | owner/guest | запись / слоты |
| `conference` | owner/guest | срочный Телемост |
| `knowledge` | owner/guest | продукт / FAQ из Knowledge + Brain |
| `memory` | owner | почта / контакты / треды Second Brain |
| `files` | owner/guest | презентации и файлы |
| `briefing` | owner | «что сегодня / план» |
| `client_prep` | owner | тезисы перед клиентом (+ почта) |
| `outbound` | owner | исходящие звонки AVA + скрипт + отчёты |
| `office` | guest | внешний офисный тон |

Owner tools: `search_office_memory`, `find_office_contact`, `list_office_threads` → `:8017/api/brain/*`.  
Outbound (owner): `outbound_dial`, `get/update_outbound_scenario`, `list/get_outbound_call` → Quantum Console `:8013` (`Authorization: Bearer` + `X-Console-Token`). Per-call `greeting`/`script`/`use_knowledge` on dial; persistent script via `/api/outbound/script`.

Автовыбор по ключевым словам. Закрепить вручную:

```
/режимы
/режим calendar
/режим сброс
```

## Telegram

Бот: [@Quantum_office_bot](https://t.me/Quantum_office_bot)  
Команды: `/start` `/help` `/reset` `/режимы`

## HTTP API

```http
POST /api/chat
X-Webhook-Token: <token>
Content-Type: application/json

{
  "channel": "telegram",
  "user_id": "963782",
  "text": "Создай Телемост",
  "scenario": "conference"
}
```

`user_id` владельца + опционально `"channel":"owner"` тоже включает owner-роль.

## Modules

- knowledge `:8017`
- calendar `:8014`
- conference `:8016`
- files `:8015`
- quantum-console `:8013` (outbound dial + scenario, owner)
