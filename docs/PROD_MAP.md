# PROD MAP — Quantum Labs Office

**Host:** `5.35.86.62` (`gakgoudtua`)  
**User:** `root`  
**Public:** https://a.47z.ru

## Services

| systemd | path | bind | notes |
|---------|------|------|-------|
| `ava-outreach` | `/opt/ava-outreach` | `127.0.0.1:8012` | Bitrix outreach + UI under `/_ava_outreach/` |
| `ava-mailer` | `/opt/ava-mailer` | `0.0.0.0:8000` | calendar / Telemost / post-call |
| `ava-text-bot` | `/opt/ava-text-bot` | `127.0.0.1:8011` | Telegram text bot |
| `quantum-console` | `/opt/quantum-console` | `127.0.0.1:8013` | Пульт: линия, робот, outreach, звонки |
| `ava-knowledge` | `/opt/ava-knowledge` | `127.0.0.1:8017` | общая KB |
| `ava-calendar` | `/opt/ava-calendar` | `127.0.0.1:8014` | CalDAV |
| `ava-conference` | `/opt/ava-conference` | `127.0.0.1:8016` | Телемост |
| `ava-files` | `/opt/ava-files` | `127.0.0.1:8015` | брокер файлов |
| `ava-sheets-campaign` | `/opt/ava-sheets-campaign` | `127.0.0.1:8018` | обзвон из Sheet |

## Public routes

- `GET https://a.47z.ru/_ava_outreach/health` → `{"ok":true,"service":"ava-outreach"}`
- UI outreach: https://a.47z.ru/_ava_outreach/ui/
- Пульт: https://a.47z.ru/_quantum_console/

## Secrets (do not commit)

- `/opt/ava-outreach/.env`
- `/opt/ava-mailer/.env`
- `/opt/ava-text-bot/.env`
- `/opt/quantum-console/.env`
- `/opt/ava-mailer/yandex_oauth_tokens.json`

## Do not touch

- `/opt/polyhub` (trading)
- Asterisk / AVA docker (`/root/ava`) / Mango / VPN (`/opt/xray-vpn1-edge`)

## Repo mapping

| git | prod |
|-----|------|
| `outreach/` | `/opt/ava-outreach` |
| `mailer/` | `/opt/ava-mailer` |
| `text-bot/` | `/opt/ava-text-bot` |
| `console/` | `/opt/quantum-console` |
