# Quantum Labs ИИ-секретарь (channel-agnostic)

Ядро: `secretary.py` — диалог + память + tools + **сценарии поведения**.  
Каналы: Telegram + HTTP API + WhatsApp / Max / VK (webhooks).

## Кто вы для бота

| | |
|--|--|
| Владелец | `SECRETARY_OWNER_IDS` (Telegram chat_id) → личный секретарь |
| Сотрудник (обучение) | `/обучение <PIN>` или `SECRETARY_TRAINEE_IDS` → тренер по продажам |
| Гость | все остальные → офисный секретарь |

Пока owners не заданы, Telegram по умолчанию считается owner (`SECRETARY_TELEGRAM_DEFAULT_OWNER=true`).

### Режим обучения сотрудников

Для менеджеров обзвона: продукт, скрипты, возражения, приглашение на ВКС.  
**Нет** доступа к внутренней почте, контактам и диску Mail.ru — только Knowledge/FAQ.

```
/обучение 482917
/режимы
/обучение выход
```

Env: `SECRETARY_TRAINING_PIN`, опционально `SECRETARY_TRAINEE_IDS`, `SECRETARY_TRAINING_ENABLED`.

## Сценарии

Файл: `scenarios.yaml`

| id | для кого | когда |
|----|----------|--------|
| `secretary` | owner | общий личный секретарь (default) |
| `calendar` | owner/guest | запись / слоты |
| `conference` | owner/guest | срочный Телемост |
| `knowledge` | owner/guest/trainee | продукт / FAQ из Knowledge + Brain |
| `memory` | owner | почта / контакты / треды Second Brain |
| `files` | owner/guest | презентации и файлы |
| `briefing` | owner | «что сегодня / план» |
| `client_prep` | owner | тезисы перед клиентом (+ почта) |
| `outbound` | owner | исходящие звонки AVA + скрипт + отчёты |
| `office` | guest | внешний офисный тон |
| `training` | trainee | тренер по продажам (default) |
| `training_script` | trainee | скрипт звонка |
| `training_objections` | trainee | возражения |

Owner tools: `search_office_memory`, `find_office_contact`, `list_office_threads` → `:8017/api/brain/*`.  
Outbound (owner): `outbound_dial`, `get/update_outbound_scenario`, `list/get_outbound_call` → Quantum Console `:8013` (`X-Console-Token`).

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


## Мессенджеры (WhatsApp / Max / VK)

Один секретарь (`secretary.py`) + адаптеры в `channels/`.  
В этих каналах роль всегда **guest** → Second Brain principal `service:text-guest` (FAQ, без почты/PII).

Публичный префикс (nginx): `https://a.47z.ru/_ava_secretary/`

| Канал | Endpoint | Включение |
|-------|----------|-----------|
| WhatsApp Cloud API | `GET/POST /webhooks/whatsapp` | `WHATSAPP_ENABLED=true` + token / phone id / verify token |
| Max Bot API | `POST /webhooks/max` | `MAX_ENABLED=true` + `MAX_BOT_TOKEN` (+ secret) |
| VK Callback API | `POST /webhooks/vk` | `VK_ENABLED=true` + group token + confirmation |

После заполнения `.env` — `systemctl restart ava-text-bot`.  
Nginx snippet: `scripts/nginx-ava-secretary.conf`.

Для Max: зарегистрировать subscription на `https://a.47z.ru/_ava_secretary/webhooks/max`  
(`POST https://platform-api2.max.ru/subscriptions`).


## Telegram Business — ответы «как вы», не как бот

Клиент пишет **вам в личку** (ваш аккаунт). Секретарь отвечает **от вашего имени**
через официальный Business Connection — без Telethon/userbot.

### Включение (один раз)

1. Откройте **@BotFather** → `/mybots` → `@Quantum_office_bot` → **Bot Settings** → **Business Mode** → Enable  
2. На телефоне: **Настройки → Telegram Business → Чат-боты** → добавьте `@Quantum_office_bot`  
3. Права: читать сообщения + отвечать. Можно ограничить «только новые чаты».  
4. `systemctl restart ava-text-bot` (уже поддерживает `business_message`)

После этого новые входящие к вам видны в обычном Telegram, а автоответ уходит
без пометки «бот» у собеседника. Если вы сами написали в чат — автоответ
паузится на `TELEGRAM_BUSINESS_OWNER_PAUSE_SECONDS` (по умолчанию 30 мин).
