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
source: tools#quantum-console
shard: tool-quantum-console
---

# Инструмент: quantum-console

Операционный веб-интерфейс **нашей** системы (телефония + outreach + знания), не стоковый AVA Admin UI.

- Путь: `/opt/quantum-console`
- Порт: `8013`
- Unit: `quantum-console.service`
- UI: `http://127.0.0.1:8013/` и `https://a.47z.ru/_quantum_console/`
- Auth UI: `CONSOLE_USER` + `CONSOLE_PASSWORD` (session cookie); API bots: `CONSOLE_TOKEN`
- **Outreach** встроен в меню консоли (прокси на `:8012`, отдельный токен outreach в браузере не нужен)

## Возможности

- Статус mailer / ai_engine / регистрации / outbound dialplan
- Редактор сценария (greeting, prompt, model, voice)
- Просмотр базы знаний FAQ
- История звонков
- Исходящий тестовый звонок
- Чеклист секретов (без значений), бэкап, inventory пакета

Полноценные CSV-кампании — через AVA Admin `:3003` → Call Scheduling.
