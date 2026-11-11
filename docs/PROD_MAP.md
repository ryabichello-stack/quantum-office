# PROD MAP — Quantum Labs Office

> **2026-11-11:** Beget `5.35.86.62` / `a.47z.ru` destroyed.  
> Recovery host: **Cloud4Box `161.104.89.123`** — see [`QL_DISASTER_RECOVERY.md`](QL_DISASTER_RECOVERY.md).

**Host (recovery):** `161.104.89.123`  
**User:** `root`  
**Public (temp):** `http://161.104.89.123/_ava_*`  
**Former:** `5.35.86.62` / https://a.47z.ru (down)

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
- `GET https://a.47z.ru/_ava_outreach/health`

## Secrets (do not commit)

- `/opt/ava-*/.env`, `/opt/quantum-console/.env`
- `/opt/ava-mailer/yandex_oauth_tokens.json`
- `/opt/ava-conference/yandex_oauth_tokens.json`

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
