# Каналы — единый отчёт в пульте

Раздел **Каналы** в [Центре управления](https://a.47z.ru/_quantum_console/): Telegram, Max, email-рассылка, звонки (вх/исх), заявки с Tilda за выбранный период.

## API

```http
GET /_quantum_console/api/channels/report?from_day=2026-08-01&to_day=2026-09-03
```

Auth: сессия пульта или `X-Console-Token`.

## Источники

| Канал | Откуда |
|-------|--------|
| Telegram / Max | `/opt/ava-text-bot/data/sessions.db` (сообщения и чаты) |
| Email | `/opt/ava-outreach/data/modules.db` → `send_events` (без `@quantumlabs.ru`) |
| Звонки | `/root/ava/data/call_history.db` → `call_records` (`outbound*` = исходящие, остальное ≈ входящие) |
| Tilda заявки | webhook → SQLite `/opt/quantum-console/data/tilda_leads.db` |
| Tilda визиты | опционально Yandex Metrika |

## Подключение Tilda (заявки)

1. В `.env` пульта задайте секрет (или используйте `CONSOLE_TOKEN`):

```bash
TILDA_WEBHOOK_SECRET=длинный-секрет
```

2. В Tilda: **Настройки сайта → Формы → Webhook** (или «отправка данных» у формы):

```text
https://a.47z.ru/_quantum_console/api/channels/tilda/lead?token=длинный-секрет
```

3. Отправьте тестовую заявку — она появится в разделе «Каналы».

Tilda **не отдаёт** готовую публичную статистику визитов в наш API. Для посещений:

- подключите счётчик **Яндекс.Метрики** на сайт Tilda;
- в `.env` пульта:

```bash
TILDA_METRIKA_COUNTER=12345678
TILDA_METRIKA_TOKEN=y0_oauth_token
```

Тогда в отчёте появятся визиты и конверсия заявок.

## Деплой

Скопировать в `/opt/quantum-console/`:

- `main.py`
- `channels_report.py`
- `static/` (index.html, console.js, console.css)
- `requirements.txt` (+ `python-multipart`)

```bash
cd /opt/quantum-console && ./venv/bin/pip install -r requirements.txt
systemctl restart quantum-console
curl -sf http://127.0.0.1:8013/health
```
