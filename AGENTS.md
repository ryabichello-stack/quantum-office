# Quantum Labs Office — Agent Onboarding

**Это репозиторий office-сервисов Quantum Labs + DELNO**, не Polyhub trading.

## Что здесь

| Папка | Сервис |
|-------|--------|
| `outreach/` | Bitrix outreach `:8012` |
| `mailer/` | post-call / calendar·Telemost `:8000` |
| `text-bot/` | Telegram + HTTP `:8011` |
| `console/` | пульт `:8013` |
| `knowledge/` | Second Brain / KB `:8017` |
| `calendar/` `conference/` `files/` | office brokers |
| `delno-api/` `delno-web/` `delno-admin/` `DELNO-site-v23/` | DELNO SaaS |
| `delno-office/` | DELNO brokers under `/opt/delno` |
| `docs/` | планы, DNS, restore |

## DELNO

- **Prod host:** Cloud4Box **`161.104.89.123`** (Beget `5.35.86.62` уничтожен — не SSH туда)
- Site: https://dlno.ru · Cabinet: https://app.dlno.ru · API: https://api.dlno.ru
- **Restore from git:** [`docs/DELNO_RESTORE.md`](docs/DELNO_RESTORE.md)
- DNS: [`docs/DLNO_DOMAINS.md`](docs/DLNO_DOMAINS.md)
- Env template: `delno-api/.env.example` → `/opt/delno/.env` only (never git)
- Master plan: [`docs/DELNO_MASTER_PLAN.md`](docs/DELNO_MASTER_PLAN.md)

## Дисциплина

1. Любое изменение → commit + push + PR  
2. Журнал → [`CHANGELOG.md`](CHANGELOG.md)  
3. **Реестр агентов Cursor↔Codex** → [`docs/AGENT_CHANGE_REGISTER.md`](docs/AGENT_CHANGE_REGISTER.md)
   (прод: `/opt/delno/docs/AGENT_CHANGE_REGISTER.md`) — читать до правок, писать после  
4. Секреты не в git  
5. Прод обновлять из git **сразу**, затем smoke `/health` (владелец тестирует только прод)

## Не ломать

Asterisk / AVA docker / Mango / VPN / `/opt/polyhub` / 3x-ui Reality (после ingress на **:8443**).
