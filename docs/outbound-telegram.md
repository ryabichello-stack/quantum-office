# Исходящие звонки из Telegram (text-bot → Quantum Console)

Управление one-shot исходящими через **ava-text-bot** (owner) без правок Asterisk/Mango/VPN.

## Цепочка

1. Владелец в Telegram: «позвони 7900…, задача: …»
2. Бот **сам** собирает `greeting` + `script` по задаче (додумывает пробелы) и **показывает черновик**
3. После «да, звони» → `outbound_dial` с этими полями
4. Quantum Console пишет per-call JSON → AVA `provider_overrides` (без рестарта)
5. Расшифровка: `list/get_outbound_call`

## Env (text-bot)

```bash
AVA_CONSOLE_BASE=http://127.0.0.1:8013
CONSOLE_TOKEN=<тот же, что CONSOLE_TOKEN в /opt/quantum-console/.env>
CONSOLE_ENABLED=true
```

## Tools (только owner)

| Tool | Действие |
|------|----------|
| `outbound_dial` | `POST /api/outbound/dial` — `confirm=true` + **обязательно** `goal` и/или `script` (иначе отказ: не уйдёт старый playbook выплат). Опционально `greeting` / `use_knowledge` (по умолчанию false для кастомного). `use_default_script=true` — явный YAML outbound |
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

Из Telegram: достаточно короткой задачи («позвони Свете, пригласи на свидание от Дениса»).
Бот дописывает greeting/script, показывает черновик, после «да» звонит.

## Примеры фраз

- «Позвони на 79001234567 — от Дениса пригласи Свету на свидание»
- «Позвони 7900… от имени Анны из Acme, цель демо»
- «Покажи последние исходящие / расшифровку call_id=…»

UI Console: https://a.47z.ru/_quantum_console/
