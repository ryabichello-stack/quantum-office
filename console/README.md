# Console — Quantum Labs telephony ops UI

Prod: `/opt/quantum-console` · `https://a.47z.ru/_quantum_console/` · port `8013`

## Auth

Human UI uses **login + password** (session cookie `qc_session`):

| Env | Default | Notes |
|-----|---------|--------|
| `CONSOLE_USER` | `admin` | Login |
| `CONSOLE_PASSWORD` | — | If empty, falls back to `CONSOLE_TOKEN` |
| `CONSOLE_SESSION_SECRET` | `CONSOLE_TOKEN` / dev | HMAC for session cookie |
| `CONSOLE_TOKEN` | — | Still required for bots / API (`X-Console-Token` or `Bearer`) |

`POST /api/auth/login` `{ "username", "password" }` → sets cookie.  
`POST /api/auth/logout` · `GET /api/auth/me`

Machine clients (text-bot, sheets campaign) keep using `CONSOLE_TOKEN`.

## Calls / transcripts

Tab **Звонки** is the source of truth for **outbound** results:

- Filter defaults to `outbound`
- Click a row → full turn table

Inbound still gets «Новый лид» email via mailer. Outbound does not.

## Deploy

```bash
cp main.py /opt/quantum-console/
cp static/* /opt/quantum-console/static/
# add CONSOLE_USER / CONSOLE_PASSWORD to /opt/quantum-console/.env
systemctl restart quantum-console
```
