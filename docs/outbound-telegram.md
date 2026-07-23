# Исходящие звонки из Telegram (text-bot → Quantum Console)

Управление one-shot исходящими через **ava-text-bot** (owner) без правок Asterisk/Mango/VPN.

## Цепочка

1. Владелец в Telegram: «позвони 7900… / смени скрипт outbound / покажи звонки»
2. Сценарий `outbound` + tools в `ava_client.py`
3. Quantum Console `:8013` (`Authorization: Bearer` и/или `X-Console-Token`)
4. Dial / script / call_history

## Env (text-bot)

```bash
AVA_CONSOLE_BASE=http://127.0.0.1:8013
CONSOLE_TOKEN=<тот же, что CONSOLE_TOKEN в /opt/quantum-console/.env>
CONSOLE_ENABLED=true
```

## Tools (только owner)

| Tool | Действие |
|------|----------|
| `outbound_dial` | `POST /api/outbound/dial` — `confirm=true`; опционально `greeting` / `script` / `use_knowledge` **только для этого звонка** |
| `get_outbound_scenario` | `GET /api/outbound/script` |
| `update_outbound_scenario` | `PUT /api/outbound/script` — постоянный greeting+script (+ optional restart) |
| `list_outbound_calls` | `GET /api/calls?context=outbound` |
| `get_outbound_call` | `GET /api/calls/{id}` |

Входящий профиль `default` из бота **нельзя** менять этими tools.

## Пример dial (Console API)

```bash
curl -sS -X POST "https://a.47z.ru/_quantum_console/api/outbound/dial" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "phone": "79001234567",
    "greeting": "Алло, это Анна из Acme. Удобно 20 секунд?",
    "script": "Ты Анна из Acme. Цель: демо Acme Cloud.",
    "use_knowledge": true
  }'
```

Из Telegram то же самое: владелец даёт номер + скрипт → бот подтверждает → `outbound_dial` с теми же полями.

## Примеры фраз

- «Позвони на 79001234567, цель — квалификация ломбарда»
- «Позвони 7900… от имени Анны из Acme, скрипт: …»
- «Покажи скрипт исходящих»
- «Обнови постоянный greeting исходящих на …»
- «Покажи последние исходящие / расшифровку call_id=…»

UI Console: https://a.47z.ru/_quantum_console/
