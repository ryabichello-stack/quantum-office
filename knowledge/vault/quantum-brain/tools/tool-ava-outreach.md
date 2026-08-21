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
source: tools#ava-outreach
shard: tool-ava-outreach
---

# Инструмент: ava-outreach (Bitrix SMTP outreach)

Оркестратор B2B-касаний по базе ломбардов. Не ESP и не часть SIP/Asterisk.

- Путь: `/opt/ava-outreach`
- Порт: `8012`
- Unit: `ava-outreach.service`
- UI: `http://127.0.0.1:8012/ui/` и `https://a.47z.ru/_ava_outreach/ui/`
- Auth UI: `OUTREACH_UI_TOKEN`

## Интеграции

- CRM Bitrix24 (компании/контакты, отрасль «Ломбарды»)
- Почта Mail.ru Business `office@quantumlabs.ru` (stable From)
- DaData по ИНН (директор, реквизиты)
- Post-call fan-out из mailer: `POST /api/telephony/lead`

## Безопасность отправки

- `OUTREACH_ENABLED=false` по умолчанию (kill-switch)
- Дневной лимит, warmup, jitter 60–180с
- Domain cap / company cap / suppression / unsubscribe

## CLI

```bash
cd /opt/ava-outreach
./venv/bin/python main.py status
./venv/bin/python main.py sync
./venv/bin/python main.py dry-run 5
./venv/bin/python main.py send-batch 1
```

Изолирован от Asterisk / AVA docker / VPN — их не трогает.
