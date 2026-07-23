# Quantum Labs ИИ-секретарь (channel-agnostic)

Ядро: `secretary.py` — диалог + память + tools.  
Каналы: Telegram + HTTP API (и дальше Bitrix/web).

## Telegram
Бот: [@Quantum_office_bot](https://t.me/Quantum_office_bot)  
Команды: `/start` `/help` `/reset`

## HTTP API (любая среда)

```http
POST /api/chat
X-Webhook-Token: <token>
Content-Type: application/json

{
  "channel": "web",
  "user_id": "user-42",
  "text": "Создай конференцию и пригласи ivan@example.com"
}
```

```http
POST /api/chat/reset
{"channel":"web","user_id":"user-42"}
```

## Modules
- mailer knowledge
- calendar `:8014`
- conference `:8016`
- files `:8015`
