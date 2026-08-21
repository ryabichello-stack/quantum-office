---
tenant_id: quantum-labs
visibility: company
classification:
  level: internal
  contains_personal_data: false
channels: [office-assistant]
ai_processing:
  allow_external_embed: true
publication:
  manual_approve: false
source: tools#office-stack-catalog
shard: office-stack-catalog
---

# Каталог инструментов Quantum Labs (office stack)

Карта **наших** сервисов на prod. Не включает Polyhub trading, Xray VPN и чужие upstream-доки без Quantum-кастома.

Публичные контакты компании: сайт https://quantumlabs.ru , email office@quantumlabs.ru , телефон 8 (800) 555-94-18.

## Сервисы и порты

| Инструмент | Путь | Порт | Unit | Назначение |
|------------|------|------|------|------------|
| ava-mailer | `/opt/ava-mailer` | 8000 | ava-mailer | Календарь, Телемост, knowledge proxy, post-call, SMTP |
| ava-text-bot | `/opt/ava-text-bot` | 8011 | ava-text-bot | Telegram ИИ-секретарь + HTTP chat |
| ava-outreach | `/opt/ava-outreach` | 8012 | ava-outreach | Bitrix SMTP outreach / ломбарды |
| quantum-console | `/opt/quantum-console` | 8013 | quantum-console | Наш ops UI телефонии |
| ava-calendar | `/opt/ava-calendar` | 8014 | ava-calendar | Mail.ru CalDAV календарь |
| ava-files | `/opt/ava-files` | 8015 | ava-files | Брокер файлов → email/Telegram |
| ava-conference | `/opt/ava-conference` | 8016 | ava-conference | Яндекс Телемост + инвайты |
| ava-knowledge | `/opt/ava-knowledge` | 8017 | ava-knowledge | Second Brain + FAQ knowledge API |
| AVA Admin UI | docker | 3003 | quantum-ava-docker | Upstream admin / call scheduling |

Публичные UI (nginx):  
- Outreach: `https://a.47z.ru/_ava_outreach/ui/`  
- Console: `https://a.47z.ru/_quantum_console/`

## Голосовая AVA (in-call tools)

Во время звонка `ai_engine` вызывает HTTP-tools на mailer:

- `check_calendar` → календарь
- `create_calendar_event` → событие + Телемост + welcome email
- `get_company_knowledge` → база знаний (через mailer → `:8017`)
- `hangup_call`

## Что не кладём в эту базу

- Документация **Polyhub** trading / стратегия / кошельки
- **Xray / VPN** runbooks
- Секреты, токены, пароли, дампы БД

Телефония Mango/Asterisk описывается только на уровне office-паспорта (без секретов), без правок самих систем из Second Brain.
