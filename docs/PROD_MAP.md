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

## Public routes

- `GET https://a.47z.ru/_ava_outreach/health` → `{"ok":true,"service":"ava-outreach"}`
- UI: https://a.47z.ru/_ava_outreach/ui/

## Secrets (do not commit)

- `/opt/ava-outreach/.env`
- `/opt/ava-mailer/.env`
- `/opt/ava-text-bot/.env`
- `/opt/ava-mailer/yandex_oauth_tokens.json`

## Telegram egress (prod)

С хоста `api.telegram.org` по DNS A `149.154.166.110` **недоступен** (TCP/443 timeout).
Рабочий DC: `149.154.167.220` (проверено `getMe` / `getUpdates`).

Аварийный фикс на проде (2026-10-09): в `/etc/hosts` строка

```
149.154.167.220 api.telegram.org # quantum-tg-egress-fix
```

После правки — `systemctl restart ava-text-bot`. Бэкап hosts: `/etc/hosts.bak.*`.
Если провайдер снова откроет канонический A-record — строку можно убрать и проверить `curl -4 -m 8 https://api.telegram.org/`.

## Do not touch

- `/opt/polyhub` (trading)
- Asterisk / AVA docker (`/root/ava`) / Mango / VPN (`/opt/xray-vpn1-edge`)

## Repo mapping

| git | prod |
|-----|------|
| `outreach/` | `/opt/ava-outreach` |
| `mailer/` | `/opt/ava-mailer` |
| `text-bot/` | `/opt/ava-text-bot` |
