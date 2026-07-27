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
source: tools#tools-faq
shard: tools-faq
---

# Частые вопросы про инструменты Quantum Labs

### Какой сервис за что отвечает?

Смотри каталог: mailer 8000, text-bot 8011, outreach 8012, console 8013, calendar 8014, files 8015, conference 8016, knowledge/Second Brain 8017.

### Как создать Телемост?

Через text-bot сценарий conference, API `ava-conference`, или calendar create с `create_telemost=true`. Голосом — tool создания события/конференции.

### Как отправить презентацию клиенту?

`ava-files` (`POST /api/files/send`) из local/yadisk/repo в email или Telegram. Либо попросить text-bot в режиме files.

### Где холодные письма ломбардам?

`ava-outreach` UI `/_ava_outreach/ui/`. Отправка только при `OUTREACH_ENABLED=true`.

### Где база знаний продукта?

`ava-knowledge` + vault Quantum Payouts / ломбарды. Голос читает режим `KNOWLEDGE_READ_MODE=brain`.

### Что такое quantum-console?

Наш ops UI телефонии на `:8013`, не путать с AVA Admin `:3003`.

### Документы Polyhub / VPN попадают в базу?

Нет. Сознательно исключены из ingest office knowledge.
