# Исходящие звонки из Telegram (text-bot → Quantum Console)

Управление one-shot исходящими через **ava-text-bot** (owner) без правок Asterisk/Mango/VPN.

## Цепочка

1. Владелец в Telegram: «позвони 7900… / смени скрипт outbound / покажи звонки»
2. Сценарий `outbound` + tools в `ava_client.py`
3. Quantum Console `:8013` (`X-Console-Token`)
4. Dial / scenario / call_history

## Env (text-bot)

```bash
AVA_CONSOLE_BASE=http://127.0.0.1:8013
CONSOLE_TOKEN=<тот же, что CONSOLE_TOKEN в /opt/quantum-console/.env>
CONSOLE_ENABLED=true
```

## Tools (только owner)

| Tool | Действие |
|------|----------|
| `outbound_dial` | `POST /api/outbound/dial` — нужен `confirm=true` |
| `get_outbound_scenario` | `GET /api/scenario?context=outbound` |
| `update_outbound_scenario` | `PUT /api/scenario` только `context=outbound` (+ optional restart) |
| `list_outbound_calls` | `GET /api/calls?context=outbound` |
| `get_outbound_call` | `GET /api/calls/{id}` |

Входящий профиль `default` из бота **нельзя** менять этими tools.

## Примеры фраз

- «Позвони на 79001234567, цель — квалификация ломбарда»
- «Покажи скрипт исходящих»
- «Обнови greeting исходящих на … и перезапусти engine»
- «Покажи последние исходящие / расшифровку call_id=…»

UI Console по-прежнему: https://a.47z.ru/_quantum_console/
