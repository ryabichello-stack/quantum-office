# Yandex OAuth — Метрика, Директ, Вебмастер, Вордstat

Одно OAuth-приложение в [oauth.yandex.ru](https://oauth.yandex.ru) → **один refresh/access token** (`YANDEX_MARKETING_OAUTH_*`) для всех включённых в кабинете API: **Метрика, Директ, Вебмастер, Вордstat** (как на вашем скрине с «API Вордстата» и остальными доступами).

**Секреты только на сервере** — в `.env`, не в git. См. также `docs/PROD_MAP.md`.

## Что на скриншоте oauth.yandex.ru (приложение DELNO)

На странице настроек OAuth-приложения обычно видны только **ключи приложения**, не «готовый токен Метрики» и не **номер счётчика** для сайта:

| Поле на скрине | Куда попадает на prod |
|----------------|------------------------|
| **ClientID** (`279b496a…`) | `YANDEX_MARKETING_OAUTH_CLIENT_ID` в `/opt/ava-mailer/.env` |
| **Client secret** | `YANDEX_MARKETING_OAUTH_CLIENT_SECRET` |
| **Redirect URI** `verification_code` | `YANDEX_MARKETING_OAUTH_REDIRECT_URI` |

Эти три значения **уже сверены с prod** (совпадают). Их достаточно, чтобы **запросить** OAuth-токен, но не заменяют шаг «войти в Яндекс → скопировать verification code → обменять на refresh_token» (файл `yandex_marketing_oauth_tokens.json`).

**ClientID ≠ ID счётчика Метрики** на `dlno.ru`. Номер счётчика (цифры в коде `ym(12345678)`) появляется после API `ensure` или в интерфейсе [metrika.yandex.ru](https://metrika.yandex.ru).

Для автоматизации **не использовать** посторонние логины из Cloud Agent (`YANDEX_LOGIN` и т.п.) — только OAuth-приложение со скрина и аккаунт, у которого есть доступ к счётчикам.

## Переменные окружения

Используется тот же механизм, что и для Телемоста в `mailer/yandex_oauth.py`:

| Переменная | Назначение |
|------------|------------|
| `YANDEX_OAUTH_CLIENT_ID` | ClientID из кабинета OAuth |
| `YANDEX_OAUTH_CLIENT_SECRET` | Client secret |
| `YANDEX_OAUTH_REDIRECT_URI` | Redirect URI **как в кабинете** (часто `https://oauth.yandex.ru/verification_code` для ручного кода) |
| `YANDEX_OAUTH_SCOPE` | Права в URL авторизации (пробелы). Для Телемоста уже есть дефолт; при подключении Метрики/Директа/Вебмастера допишите scope из документации соответствующего API |
| `YANDEX_OAUTH_TOKEN_FILE` | Файл с `access_token` / `refresh_token` (prod: `/opt/ava-mailer/yandex_oauth_tokens.json`, `chmod 600`) |

### Marketing-приложение (единый токен)

На prod (`/opt/ava-mailer/.env`) — **второй** блок, отдельно от Телемоста (`YANDEX_OAUTH_*`):

| Переменная | Назначение |
|------------|------------|
| `YANDEX_MARKETING_OAUTH_CLIENT_ID` | ClientID приложения (Метрика + Директ + Вебмастер + Вордstat в кабинете) |
| `YANDEX_MARKETING_OAUTH_CLIENT_SECRET` | Client secret |
| `YANDEX_MARKETING_OAUTH_REDIRECT_URI` | `https://oauth.yandex.ru/verification_code` |
| `YANDEX_MARKETING_OAUTH_SCOPE` | Scope в URL авторизации (см. ниже) |
| `YANDEX_MARKETING_OAUTH_TOKEN_FILE` | `/opt/ava-mailer/yandex_marketing_oauth_tokens.json` |

**Рекомендуемый `YANDEX_MARKETING_OAUTH_SCOPE`** (пробелы между правами):

```text
metrika:read metrika:write direct:api webmaster:hostinfo webmaster:verify
```

- **Метрика** — `metrika:read`, `metrika:write`
- **Директ** — `direct:api` ([регистрация приложения](https://yandex.ru/dev/direct/doc/en/register))
- **Вебмастер** — `webmaster:hostinfo`, `webmaster:verify` ([OAuth](https://yandex.com/dev/webmaster/doc/en/tasks/how-to-get-oauth))
- **Вордstat** — отдельного scope в URL часто нет: доступ включается **галочкой «API Вордстата»** в oauth.yandex.ru; тот же OAuth-токен + **ClientId** в запросах к [Wordstat API](https://yandex.ru/support/wordstat/en/content/api-wordstat) (`Authorization: Bearer …`), плюс заявка в поддержку Директа на доступ к API.

Mailer: `/oauth/yandex/marketing/*`, `/yandex/metrika/ensure` (счётчик на сайт — только Метрика; остальные API — позже на том же token).

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

4. Проверка Telemost: `GET /oauth/yandex/status` + header `X-Webhook-Token`.

### Marketing (единый токен → все API)

1. В `.env` mailer задайте полный `YANDEX_MARKETING_OAUTH_SCOPE` (см. выше).
2. `GET /oauth/yandex/marketing/manual?token=<WEBHOOK_TOKEN>` — войти, выдать **все** запрошенные права, сохранить refresh в `YANDEX_MARKETING_OAUTH_TOKEN_FILE`.
3. Для **счётчика на dlno.ru**: `GET /yandex/metrika/ensure?token=<WEBHOOK_TOKEN>&site=dlno.ru` → `counter_id`.
4. `bash /opt/delno/deploy/sync_metrika_and_site.sh` — `YM_COUNTER_ID` и пересборка `delno-site-root`.

## API после token

| Сервис | Документация (ориентир) |
|--------|-------------------------|
| Метрика | [API Метрики](https://yandex.ru/dev/metrika/doc/api2/concept/about.html) — заголовок `Authorization: OAuth <token>` |
| Директ | [API Директа](https://yandex.ru/dev/direct/doc/dg/concepts/about.html) |
| Вебмастер | [API Вебмастера](https://yandex.ru/dev/webmaster/doc/dg/concepts/about.html) |
| Вордstat | [Wordstat API](https://yandex.ru/support/wordstat/en/content/api-wordstat) — Bearer + ClientId, доступ по заявке |

Заголовок для Метрики/Директа/Вебмастера: `Authorization: OAuth <token>`. Для Вордstata: `Authorization: Bearer <token>` (тот же access token после OAuth).

Конкретные scope и лимиты — в карточках доступа приложения на oauth.yandex.ru.

## Счётчик на сайте (dlno.ru)

OAuth и API Метрики — для серверных отчётов. Для аналитики посещений на лендинге используется **код счётчика** в `DELNO-site-v23`:

| Переменная | Назначение |
|------------|------------|
| `NEXT_PUBLIC_YM_COUNTER_ID` | Числовой ID счётчика из [metrika.yandex.ru](https://metrika.yandex.ru) |

Компонент `components/YandexMetrika.tsx` подключён в `app/layout.tsx`. Без ID в env скрипт не грузится.

На prod (контейнер `delno-site-root`, путь `/opt/delno/site` или env в compose): добавьте переменную и пересоберите образ сайта.

## Безопасность

- Client secret и tokens **не коммитить** и не слать в открытые чаты/скриншоты в публичные каналы.
- Если secret засветился — **перевыпустите** secret в кабинете OAuth и обновите `.env` на сервере.
