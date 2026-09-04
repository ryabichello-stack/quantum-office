# Каналы — Tilda + Яндекс.Метрика

## Уже на проде

В пульте → **Каналы** (шестерёнка справа в шапке открывает подключение):

1. **Webhook Tilda** — заявки пишутся в БД и уходят владельцу в **Telegram + Max**.
2. **Метрика** — счётчик `104241036` (с сайта quantumpayouts.ru). Нужен один раз OAuth-токен.

## Telegram Mini App · сегодня

Откройте бота [@Quantum_office_bot](https://t.me/Quantum_office_bot) → кнопка меню **«Каналы сегодня»**.

Показывает за **сегодня (МСК)**:
- Яндекс.Метрика: визиты, пользователи, просмотры, отказы, среднее время
- Webhook Tilda: число заявок + список (имя / телефон / время)

URL: `https://a.47z.ru/_quantum_console/miniapp/`

Доступ только владельцам из `MINIAPP_ALLOWED_IDS` / `SECRETARY_OWNER_IDS` (сейчас `963782`). Авторизация — Telegram `initData`.

Зарегистрировать кнопку меню:

```bash
cd /opt/quantum-console && ./venv/bin/python scripts/set_miniapp_menu.py
# или: python3 scripts/set_miniapp_menu.py
```

## Tilda: куда вставить webhook

1. Откройте пульт → **Каналы** → блок «Подключение» → **Копировать** URL.
2. В Tilda: сайт **Выплаты** → **Настройки сайта → Формы → Webhook**  
   (или в настройках конкретного блока формы → отправка данных → Webhook).
3. Вставьте URL вида:
   `https://a.47z.ru/_quantum_console/api/channels/tilda/lead?token=…`
4. Сохраните, отправьте тестовую заявку с сайта.

Ответ API: `ok` + `notify.telegram` / `notify.max`.

Секрет: `TILDA_WEBHOOK_SECRET` в `/opt/quantum-console/.env` (fallback — `CONSOLE_TOKEN`).

## Метрика: выдать доступ (1 раз)

1. В пульте **Каналы** → **Получить OAuth Метрики** (откроется Яндекс).
2. Войдите аккаунтом, у которого есть доступ к счётчику **104241036**.
3. Разрешите `metrika:read`.
4. Из адресной строки скопируйте `access_token=…` (после `#`) и вставьте в поле пульта → **Сохранить токен**.

Токен пишется в `TILDA_METRIKA_TOKEN` (mode 600). После этого в отчёте появятся визиты, пользователи, просмотры, отказы и конверсия заявок.

Если приложение OAuth ругается на scope — в [oauth.yandex.ru](https://oauth.yandex.ru/) у приложения добавьте право **Яндекс.Метрика: чтение** (`metrika:read`), либо создайте отдельное приложение и пропишите `METRIKA_OAUTH_CLIENT_ID`.

## API

| Метод | Назначение |
|-------|------------|
| `GET /api/channels/report` | сводный отчёт |
| `GET /api/channels/setup` | webhook URL + статус Метрики |
| `GET /api/miniapp/today` | сегодня МСК: Метрика + webhook-заявки (Telegram initData) |
| `GET /api/miniapp/me` | кто открыл Mini App |
| `POST /api/channels/tilda/lead?token=` | публичный webhook форм |
| `GET /api/channels/metrika/authorize-url` | ссылка OAuth |
| `POST /api/channels/metrika/token` | сохранить access_token |
