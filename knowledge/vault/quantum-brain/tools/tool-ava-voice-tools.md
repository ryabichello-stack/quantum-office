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
source: tools#ava-voice-tools
shard: tool-ava-voice-tools
---

# Инструмент: голосовая AVA (in-call tools)

Голосовой ассистент Quantum Labs на входящей линии 8 (800) 555-94-18.

Поток (кратко): Mango SIP → Asterisk → Stasis AVA → OpenAI Realtime → HTTP tools на ava-mailer.

## Tools во время звонка

| Tool | Действие |
|------|----------|
| check_calendar | проверить занятость |
| create_calendar_event | слот + Телемост + письмо |
| get_company_knowledge | ответ из базы знаний / Second Brain |
| hangup_call | завершить звонок |

Greeting (типовой): «Добрый день! Вы позвонили в Quantum Labs. Чем могу помочь?»

После звонка: webhook → mailer → письмо в office / CRM fan-out.

## Связанные UI

- quantum-console `:8013` — наш ops UI
- AVA Admin `:3003` — upstream admin / scheduling

Паспорт стека на сервере: `/root/ava/docs/AVA_QUANTUM_LABS_SYSTEM.md` (копия также в vault `tools/imported/` после sync).  
Polyhub trading на том же хосте — **не** часть голосового секретаря и не ingest’ится сюда.
