# PROD MAP — Quantum Labs Office

**Host:** `5.35.86.62`  
**User:** `root`  
**Public:** https://a.47z.ru

## Services

| systemd | path | bind | notes |
|---------|------|------|-------|
| `ava-outreach` | `/opt/ava-outreach` | `127.0.0.1:8012` | Bitrix outreach + UI `/_ava_outreach/` |
| `ava-mailer` | `/opt/ava-mailer` | `0.0.0.0:8000` | post-call / legacy |
| `ava-text-bot` | `/opt/ava-text-bot` | `127.0.0.1:8011` | Telegram text bot |
| `quantum-console` | `/opt/quantum-console` | `127.0.0.1:8013` | Пульт `/_quantum_console/` |
| `ava-knowledge` | `/opt/ava-knowledge` | `127.0.0.1:8017` | shared KB / brain |
| `ava-calendar` | `/opt/ava-calendar` | `127.0.0.1:8014` | CalDAV |
| `ava-conference` | `/opt/ava-conference` | `127.0.0.1:8016` | Telemost + invites |
| `ava-files` | `/opt/ava-files` | `127.0.0.1:8015` | file broker |
| `ava-sheets-campaign` | `/opt/ava-sheets-campaign` | `127.0.0.1:8018` | Sheet → outbound |

## Public routes

- Outreach UI: https://a.47z.ru/_ava_outreach/ui/
- Пульт: https://a.47z.ru/_quantum_console/
- Секретарь (TG/Max HTTP): https://a.47z.ru/_ava_secretary/
- `GET https://a.47z.ru/_ava_outreach/health`
- Remote MCP API paths (token in app, see `office-mcp/deploy/nginx-office-api.conf.snippet`):
  - `/_ava_files/` → `:8015` (Mail.ru Cloud)
  - `/_ava_knowledge/` → `:8017`
  - `/_ava_calendar/` → `:8014`
  - `/_ava_conference/` → `:8016`
  - `/_ava_sheets_campaign/` → `:8018`

## Secrets (do not commit)

- `/opt/ava-*/.env`, `/opt/quantum-console/.env`
- `/opt/ava-mailer/yandex_oauth_tokens.json`
- `/opt/ava-conference/yandex_oauth_tokens.json`

## Postgres (anti-hang)

На проде Postgres один на несколько приложений. Уже случался outage Second Brain:
`signal` держал 4‑дневный `INSERT` + hourly `ALTER TABLE` → 95 waiting backends → `max_connections` кончились.

Защита (на сервере):
- `max_connections = 200`
- `idle_in_transaction_session_timeout = 15min` (global)
- роль `signal`: `lock_timeout=10s`, `idle_in_transaction_session_timeout=10min`, `statement_timeout=30min`
- `/opt/signal/.../migrate.py` — каждый ALTER в своей транзакции с `SET LOCAL lock_timeout/statement_timeout` (не стопорит всю очередь)
- timer `pg-kill-stuck.timer` → `/opt/quantum-office-mcp/scripts/pg_kill_stuck.sh` (убивает non-superuser backends >2h)

## Do not touch

- `/opt/polyhub` (trading)
- Asterisk / AVA docker (`/root/ava`) / Mango / VPN

## Repo mapping

| git | prod |
|-----|------|
| `outreach/` | `/opt/ava-outreach` |
| `mailer/` | `/opt/ava-mailer` |
| `text-bot/` | `/opt/ava-text-bot` |
| `console/` | `/opt/quantum-console` |
| `knowledge/` | `/opt/ava-knowledge` |
| `calendar/` | `/opt/ava-calendar` |
| `conference/` | `/opt/ava-conference` |
| `files/` | `/opt/ava-files` |
| `sheets-campaign/` | `/opt/ava-sheets-campaign` |

Версии и история изменений: [`../CHANGELOG.md`](../CHANGELOG.md).
