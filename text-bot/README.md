# Quantum Labs — Telegram text secretary + channel curate

## Secretary bot
`TELEGRAM_BOT_TOKEN` — личный/офисный ИИ-секретарь (poll loop `personal`).

## Channel curate (переписывание постов)

Отдельный бот-админ канала: владелец **пересылает** пост боту → бот переписывает текст (OpenAI) и публикует в канал как **новое** сообщение (не forward), сохраняя фото / видео / документы / альбомы, и добавляет подпись со ссылкой на канал.

| | |
|--|--|
| Env token | `TELEGRAM_CHANNEL_BOT_TOKEN` (пришлёте отдельно) |
| Channel | `TELEGRAM_CURATE_CHANNEL_ID` (default `@epoch_z`) |
| Footer | `📣` + ссылка `TELEGRAM_CURATE_CHANNEL_LINK` / title |
| Owners | `SECRETARY_OWNER_IDS` или `TELEGRAM_CURATE_OWNER_IDS` |

Пока токена нет — `/health` → `telegram_curate.enabled=false`, поллер не стартует.

### Как пользоваться после ключа

1. Добавить бота админом канала с правом постить.
2. Прописать `TELEGRAM_CHANNEL_BOT_TOKEN` в `/opt/ava-text-bot/.env`.
3. `systemctl restart ava-text-bot`
4. Переслать боту пост (текст/фото/видео/файл) — уйдёт в канал с подписью.
