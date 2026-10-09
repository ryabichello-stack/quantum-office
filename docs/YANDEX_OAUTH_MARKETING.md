# Yandex OAuth — Метрика, Директ, Вебмастер

OAuth-приложение в [oauth.yandex.ru](https://oauth.yandex.ru) даёт один **ClientID** / **Client secret** для API, к которым вы отметили доступ в кабинете (Метрика, Директ, Вебмастер, при необходимости Вордstat и др.).

**Секреты только на сервере** — в `.env`, не в git. См. также `docs/PROD_MAP.md`.

## Переменные окружения

Используется тот же механизм, что и для Телемоста в `mailer/yandex_oauth.py`:

| Переменная | Назначение |
|------------|------------|
| `YANDEX_OAUTH_CLIENT_ID` | ClientID из кабинета OAuth |
| `YANDEX_OAUTH_CLIENT_SECRET` | Client secret |
| `YANDEX_OAUTH_REDIRECT_URI` | Redirect URI **как в кабинете** (часто `https://oauth.yandex.ru/verification_code` для ручного кода) |
| `YANDEX_OAUTH_SCOPE` | Права в URL авторизации (пробелы). Для Телемоста уже есть дефолт; при подключении Метрики/Директа/Вебмастера допишите scope из документации соответствующего API |
| `YANDEX_OAUTH_TOKEN_FILE` | Файл с `access_token` / `refresh_token` (prod: `/opt/ava-mailer/yandex_oauth_tokens.json`, `chmod 600`) |

Опционально одноразово:

| `YANDEX_TELEMOST_OAUTH_TOKEN` | Статический access token, если не используете refresh |

## Куда прописать на проде

```text
/opt/ava-mailer/.env          # ClientID, secret, redirect, scope
/opt/ava-mailer/yandex_oauth_tokens.json   # появится после обмена code → token
```

После правок:

```bash
systemctl restart ava-mailer
```

DELNO (`/opt/delno`) пока **не** дублирует эти ключи — маркeting API логично вешать на mailer или отдельный сервис позже; env-имена те же.

## Получить token после настройки ClientID/secret

1. Убедитесь, что в `.env` заданы `YANDEX_OAUTH_*`.
2. **Redirect `verification_code`:** откройте ссылку авторизации (ниже), войдите под аккаунтом с доступом к счётчикам/Директу/Вебмастеру, скопируйте **код** со страницы Yandex.
3. Обменяйте код (mailer, с `WEBHOOK_TOKEN` из `.env` mailer):

   - `GET /yandex/oauth/manual?token=…` — HTML с ссылкой «Войти в Yandex»
   - `POST /yandex/oauth/exchange?token=…&code=…` — сохранит tokens в `YANDEX_OAUTH_TOKEN_FILE`

   Либо callback-URL mailer, если redirect URI укажете на ваш домен (не `verification_code`).

4. Проверка: `GET /yandex/oauth/status?token=…` → `configured: true`, `has_refresh_token: true`.

## API после token

| Сервис | Документация (ориентир) |
|--------|-------------------------|
| Метрика | [API Метрики](https://yandex.ru/dev/metrika/doc/api2/concept/about.html) — заголовок `Authorization: OAuth <token>` |
| Директ | [API Директа](https://yandex.ru/dev/direct/doc/dg/concepts/about.html) |
| Вебмастер | [API Вебмастера](https://yandex.ru/dev/webmaster/doc/dg/concepts/about.html) |

Конкретные scope и лимиты — в картоchках доступа вашего приложения на oauth.yandex.ru.

## Безопасность

- Client secret и tokens **не коммитить** и не слать в открытые чаты/скриншоты в публичные каналы.
- Если secret засветился — **перевыпустите** secret в кабинете OAuth и обновите `.env` на сервере.
