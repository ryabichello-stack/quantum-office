# sheets-campaign — обзвон номеров из Google Sheets

Читает вкладки **НомераКлиентов** и **НомераКлиентов Архив**, звонит через
Quantum Console (AVA outbound) с Second Brain + календарь/Телемост, пишет итог
в **Пометки Клиента** (+ транскрипт / статус).

## Sheet

- ID: `1xjr7vtz56ro9WD8lTIBj3uGliSSN3mh2KHZFJPdLGXE`
- gids: `467949580` (актив), `323510684` (архив)

Чтение работает по публичному CSV export. **Запись** — через Google Service Account
(Редактор на таблице) или Apps Script webhook.

## Setup (Google write)

### Вариант A — Service Account (предпочтительно)
1. GCP → IAM → Service Account → JSON ключ
2. Console → **Обзвон Sheets** → вставить JSON → «Сохранить ключ»
   (или файл `/opt/ava-sheets-campaign/sa.json` + `GOOGLE_SERVICE_ACCOUNT_FILE=...` в `.env`)
3. Share таблицу с `client_email` из JSON (**Редактор**)

### Вариант B — Apps Script
См. `apps_script_writeback.gs` → Deploy as Web App → `SHEETS_WEBHOOK_URL` в `.env`.

Без writeback сервис всё равно звонит **по очереди** и копит пометки локально;
кнопка «Дописать пометки в Sheet» / авто-flush после установки ключа.

## Где скрипт разговора

Не во вкладке Console «Сценарий» (это YAML `outbound`).

Скрипт кампании:
- UI: Console → **Кампания Sheets** (greeting + playbook, сохранить)
- API: `GET/PUT /api/campaign/script` на `:8018` (и proxy на Console)
- Файл override: `/opt/ava-sheets-campaign/data/campaign_script.json`
- Builtin default: `sheets-campaign/script.py`

## API (port 8018)

| Method | Path | Назначение |
|--------|------|------------|
| GET | `/health` | health |
| GET | `/api/campaign/preview` | кандидаты без пометки |
| POST | `/api/campaign/start` | старт воркера (`max_calls`, `sheet`, `dry_run`) |
| POST | `/api/campaign/stop` | стоп |
| GET | `/api/campaign/status` | прогресс |
| POST | `/api/campaign/flush-writebacks` | дописать локальные итоги в Sheets |

Auth: `X-Webhook-Token` = `WEBHOOK_TOKEN`.

## Dial policy

На каждый звонок:

- `use_knowledge=true` → Second Brain (`get_company_knowledge`)
- tools: `get_company_knowledge`, `check_calendar`, `create_calendar_event`, `create_conference`, `send_welcome_email`, `hangup_call`
- сценарий: квалификация → рассказ о Quantum Labs → **запись на консультацию**
  (`check_calendar` → `create_calendar_event` → Телемост) → **явная отправка письма**
  (`send_welcome_email` с презентацией PDF)
  либо письмо без слота, если интересно, но записаться сейчас нельзя
- если интересно, но без слота — пометка «перезвонить лично»
- после звонка: poll Console `GET /api/calls`, классификация → пометка в Sheet

Пометки (примеры):
`ИНТЕРЕСНО — записан на консультацию (календарь+Телемост+почта)`,
`ИНТЕРЕСНО — перезвонить лично`, `НЕ ИНТЕРЕСНО`, `НЕ ДОЗВОН`, `ПЕРЕЗВОНИТЬ позже`.
