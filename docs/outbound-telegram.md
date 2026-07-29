# Исходящие звонки из Telegram (text-bot → Quantum Console)

Управление one-shot исходящими через **ava-text-bot** (owner) без правок Asterisk/Mango/VPN.

## Цепочка

1. Владелец в Telegram: «позвони 7900…, задача: …»
2. Бот сразу `draft_outbound_call` и в **первом** ответе показывает полный сценарий
   (номер + задача + Greeting + Script). Если модель пишет только «черновик готов»,
   secretary подставляет `owner_message` сам.
3. После «да, звони» → `outbound_dial` с этими полями
4. `await_outbound_result` → сводка только по этому звонку
5. Console → AVA per-call `provider_overrides` (без рестарта)

## После исходящего

- Письмо «Новый лид» **не** отправляется (только для входящих `default`).
- Расшифровка и реплики — в Console → вкладка **Звонки** (фильтр outbound),
  и через tools `list_outbound_calls` / `get_outbound_call` / `await_outbound_result`.

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
