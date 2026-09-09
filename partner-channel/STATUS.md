# Статус кампании — Partner Channel Quantum Payouts

**Дата подготовки:** 2026-09-09  
**From для рассылки:** `rdv@quantumlabs.ru` — **отдельный ящик** от outreach  
**Изоляция:** скрипт `partner-channel/scripts/send_campaign.py` не ходит в ava-outreach / Bitrix outbox / `OUTREACH_DAILY_LIMIT`. Лимиты `office@` не расходуются.  
**Отправка:** через SMTP `rdv@` + локальный CRM; `PARTNER_SEND_ENABLED=true`  
**ICP в письмах:** регулярные выплаты, ориентир от ~5–10 млн ₽/мес

## Что готово

1. Полный список компаний + доп. поиск (банковские агентские сети) — `crm/partners.json`
2. Приоритеты A/B/C — `crm/priority_summary.json`
3. Контакты с источником (официальные сайты) — CRM
4. Обоснование fit — поле `fit_reason`
5. Персонализированные письма — `emails/personalized/*.txt`
6. Расширенное КП — `materials/01_extended_offer.md`
7. Мессенджер-тексты — `materials/04_messenger_short.md` + `*.messenger.txt`
8. FAQ — `materials/02_faq.md` (пункты **[СОГЛАСОВАТЬ]** не выдуманы)
9. Скрипт звонка — `materials/03_call_script.md`
10. CRM таблица — `crm/partners.csv`
11. Follow-up даты — проставятся скриптом при реальной отправке (+3 / +7 рабочих дней)
12. Фактические отправки — **0** (ждём `rdv@`)

## Кого звать на созвон в первую очередь (A)

| Компания | Почему | Контакт |
|----------|--------|---------|
| InteractiveCenter / IC Premium | RevShare/CPA + банки/МФО | welcome@ic.gl |
| Prodagi.PRO | ОП за результат + фин. кейсы | sales@prodagi.pro |
| RKO Group | банковские агенты CPA | support@rko-group.ru · t.me/rkogroup |
| E-RKO | агентская сеть РКО | support@e-rko.ru |
| FINLEO | агенты БГ/финпродуктов | info@finleo.ru |
| BARS (Barsltd) | ОП за результат | тел. (email не опубликован) |

## Гипотеза «фин. агенты сильнее КЦ»

В shortlist добавлены RKO Group, E-RKO, FINLEO. Их модель (агентский %, ЛК, банковские продукты) ближе к нашему RevShare, чем классический телемаркетинг. Имеет смысл созвониться с ними **раньше**, чем с крупными сервисными КЦ класса B/C.

## Следующий шаг с вашей стороны

1. Добавить ящик `rdv@quantumlabs.ru` (SMTP/IMAP Mail.ru Business).
2. Передать SMTP-пароль / положить в env на prod.
3. Запустить:

```bash
export MAIL_SMTP_HOST=smtp.mail.ru
export MAIL_SMTP_PORT=465
export MAIL_USERNAME=rdv@quantumlabs.ru
export MAIL_PASSWORD='…'
export MAIL_FROM_NAME='Quantum Payouts · Partner Channel'
export MAIL_REPLY_TO=rdv@quantumlabs.ru
export PARTNER_SEND_ENABLED=true

python partner-channel/scripts/send_campaign.py --priority A --limit 5
```
