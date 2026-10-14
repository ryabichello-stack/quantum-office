# Cold marketing mailbox (outreach)

Корпоративный `office@quantumlabs.ru` **защищён**: массовый cold outreach с него блокируется
(`protected_domain:quantumlabs.ru`). Для рассылок нужен отдельный ящик на другом домене.

## Env (`/opt/ava-outreach/.env`)

```bash
OUTREACH_COLD_MAIL_USERNAME=outreach@YOUR-COLD-DOMAIN.ru
OUTREACH_COLD_MAIL_PASSWORD=...
OUTREACH_COLD_SMTP_HOST=smtp.mail.ru
OUTREACH_COLD_SMTP_PORT=465
OUTREACH_COLD_MAIL_FROM_NAME=Quantum Labs
OUTREACH_COLD_REPLY_TO=office@quantumlabs.ru   # ответы можно на тёплый ящик
OUTREACH_COLD_DAILY_LIMIT=30
```

После `systemctl restart ava-outreach` модуль `sending_accounts` регистрирует аккаунт `cold`
как ACTIVE marketing. Проверка: `GET /api/modules/sending_accounts/marketing-gate`.

## DNS (обязательно до прогрева)

На домене ящика:

| Запись | Назначение |
|--------|------------|
| SPF (`TXT` на корне) | `v=spf1 include:_spf.mail.ru ~all` (или провайдер SMTP) |
| DKIM | ключ из панели Mail.ru / провайдера |
| DMARC (`_dmarc.domain TXT`) | `v=DMARC1; p=none; rua=mailto:…` → затем `p=quarantine` |

Проверка API: `GET /api/modules/dns_auth/check?domain=YOUR-COLD-DOMAIN.ru`.

## Прогрев

Начинать с низкого `OUTREACH_COLD_DAILY_LIMIT` (10–30), только engagement-сегменты,
следить bounce/complaint в deliverability. `office@` — только тёплая переписка и `mail.send mailbox=office`.

## MCP

- `mail.send` — обычное письмо (`mailbox=office` или `cold`)
- `outreach.send_one` / `send_batch` — предпочитают cold, когда он настроен
- `OUTREACH_UI_TOKEN` в env MCP-сервера обязателен (не `WEBHOOK_TOKEN`)
