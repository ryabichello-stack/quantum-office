# Partner Channel — Quantum Payouts

Кампания привлечения партнёрского канала продаж: колл-центры, аутсорсинг B2B-продаж, банковские/fintech агентские сети.

## Позиционирование

Мы **не** ищем операторов для холодного обзвона по часам/звонкам/дозвонам.

Мы предлагаем профессиональным B2B sales-командам стать агентами Quantum Payouts:

- партнёр находит клиента и заводит его в **агентский кабинет**;
- Quantum обеспечивает продукт, банки, онбординг;
- партнёр получает **Revenue Share** от фактического оборота клиента (ориентир: 12 месяцев после запуска; индивидуально).

## From-адрес и изоляция от outreach

**Отправка только с `rdv@quantumlabs.ru`.**  
`office@quantumlabs.ru` / `ava-outreach` для этой кампании **не использовать**.

Это **отдельный почтовый счёт**: партнёрская рассылка не списывает `OUTREACH_DAILY_LIMIT` и не ставит письма в outbox ломбардного outreach. Свой скрипт, свой CRM, свой SMTP-логин.

Пока `PARTNER_SEND_ENABLED=false` — только dry-run.

## Структура

| Путь | Назначение |
|------|------------|
| `materials/` | Расширенное КП, FAQ, скрипт звонка, мессенджеры, follow-up |
| `crm/partners.json` + `crm/partners.csv` | Единый реестр кампании |
| `emails/personalized/` | Персонализированные письма по компаниям |
| `scripts/send_campaign.py` | Отправка через SMTP `rdv@` + обновление CRM |
| `logs/` | Логи отправок (после запуска) |

## Быстрый старт (после подключения rdv@)

```bash
# На prod или локально с .env:
export MAIL_SMTP_HOST=smtp.mail.ru
export MAIL_SMTP_PORT=465
export MAIL_USERNAME=rdv@quantumlabs.ru
export MAIL_PASSWORD=...
export MAIL_FROM_NAME="Quantum Payouts · Partner Channel"
export MAIL_REPLY_TO=rdv@quantumlabs.ru
export PARTNER_SEND_ENABLED=true
export PARTNER_SEND_DRY_RUN=false

python partner-channel/scripts/send_campaign.py --priority A --limit 5
```

Dry-run без SMTP:

```bash
python partner-channel/scripts/send_campaign.py --dry-run --priority A
```

## KPI

Не число писем, а число компаний, готовых обсуждать CPA / Success Fee / CPA / Revenue Share.
