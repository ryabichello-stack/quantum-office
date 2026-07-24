# PROD MAP — Quantum Labs Office

**Host:** `5.35.86.62` (`gakgoudtua`)  
**User:** `root`  
**Public:** https://a.47z.ru

## Services

| systemd | path | bind | notes |
|---------|------|------|-------|
| `ava-outreach` | `/opt/ava-outreach` | `127.0.0.1:8012` | Bitrix outreach + UI under `/_ava_outreach/` |
| `ava-mailer` | `/opt/ava-mailer` | `0.0.0.0:8000` | post-call, knowledge proxy, welcome PDF, legacy calendar |
| `ava-calendar` | `/opt/ava-calendar` | `127.0.0.1:8014` | Mail.ru CalDAV — **voice AVA tools** check/create |
| `ava-conference` | `/opt/ava-conference` | `127.0.0.1:8016` | Telemost + invites — voice `create_conference` |
| `ava-files` | `/opt/ava-files` | `127.0.0.1:8015` | disks/repo → email/Telegram |
| `ava-text-bot` | `/opt/ava-text-bot` | `127.0.0.1:8011` | Telegram text bot |
| `ava-sheets-campaign` | `/opt/ava-sheets-campaign` | `127.0.0.1:8018` | Google Sheet → payouts outbound campaign |

## Public routes

- `GET https://a.47z.ru/_ava_outreach/health` → `{"ok":true,"service":"ava-outreach"}`
- UI: https://a.47z.ru/_ava_outreach/ui/

## Secrets (do not commit)

- `/opt/ava-outreach/.env`
- `/opt/ava-mailer/.env`
- `/opt/ava-text-bot/.env`
- `/opt/ava-mailer/yandex_oauth_tokens.json`

## Do not touch

- `/opt/polyhub` (trading)
- Asterisk / AVA docker (`/root/ava`) / Mango / VPN (`/opt/xray-vpn1-edge`)

## Repo mapping

| git | prod |
|-----|------|
| `outreach/` | `/opt/ava-outreach` |
| `mailer/` | `/opt/ava-mailer` |
| `calendar/` | `/opt/ava-calendar` |
| `conference/` | `/opt/ava-conference` |
| `files/` | `/opt/ava-files` |
| `text-bot/` | `/opt/ava-text-bot` |
| `sheets-campaign/` | `/opt/ava-sheets-campaign` |
| `console/` | `/opt/quantum-console` |
