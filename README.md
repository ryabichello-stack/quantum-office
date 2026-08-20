# quantum-office

Quantum Labs office stack (не Polyhub trading).

| Сервис | Папка | Прод-путь | Порт |
|--------|-------|-----------|------|
| Bitrix outreach / SMTP | `outreach/` | `/opt/ava-outreach` | 8012 |
| Почта (mailer) | `mailer/` | `/opt/ava-mailer` | 8000 |
| Telegram-бот | `text-bot/` | `/opt/ava-text-bot` | 8011 |
| **Пульт управления** | `console/` | `/opt/quantum-console` | 8013 |
| База знаний | `knowledge/` | `/opt/ava-knowledge` | 8017 |
| Календарь | `calendar/` | `/opt/ava-calendar` | 8014 |
| Телемост | `conference/` | `/opt/ava-conference` | 8016 |
| Файлы | `files/` | `/opt/ava-files` | 8015 |
| Обзвон Sheets | `sheets-campaign/` | `/opt/ava-sheets-campaign` | 8018 |

- Пульт: https://a.47z.ru/_quantum_console/
- Outreach UI: https://a.47z.ru/_ava_outreach/ui/
- Журнал версий: [`CHANGELOG.md`](CHANGELOG.md)
- Как работать с git/PR: [`CONTRIBUTING.md`](CONTRIBUTING.md)
- Карта прода: [`docs/PROD_MAP.md`](docs/PROD_MAP.md)
- Онбординг агента: [`AGENTS.md`](AGENTS.md)

Секреты только в `/opt/*/.env` на сервере — в git не коммитить.
