# quantum-office

Quantum Labs office stack (не Polyhub trading):

| Сервис | Папка | Прод-путь | Порт |
|--------|-------|-----------|------|
| Bitrix outreach / SMTP | `outreach/` | `/opt/ava-outreach` | 8012 |
| Почта / календарь / Телемост | `mailer/` | `/opt/ava-mailer` | 8000 |
| Telegram-бот | `text-bot/` | `/opt/ava-text-bot` | 8011 |
| **Пульт управления** | `console/` | `/opt/quantum-console` | 8013 |

- UI outreach: https://a.47z.ru/_ava_outreach/ui/
- Пульт: https://a.47z.ru/_quantum_console/
- Health: https://a.47z.ru/_ava_outreach/health
- Карта прода: [`docs/PROD_MAP.md`](docs/PROD_MAP.md)
- Онбординг агента: [`AGENTS.md`](AGENTS.md)

Секреты только в `/opt/ava-* /.env` и `/opt/quantum-console/.env` на сервере — в git не коммитить.
