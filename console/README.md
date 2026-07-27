# Console — Quantum Labs control center

Prod: `/opt/quantum-console` · `https://a.47z.ru/_quantum_console/` · port `8013`

Центр управления системой: телефония, outreach (Bitrix/email), знания, кампании.

## Auth

Human UI uses **login + password** (session cookie `qc_session`):

| Env | Default | Notes |
|-----|---------|--------|
| `CONSOLE_USER` | `admin` | Login |
| `CONSOLE_PASSWORD` | — | If empty, falls back to `CONSOLE_TOKEN` |
| `CONSOLE_SESSION_SECRET` | `CONSOLE_TOKEN` / dev | HMAC for session cookie |
| `CONSOLE_TOKEN` | — | Still required for bots / API (`X-Console-Token` or `Bearer`) |

## Outreach (embedded)

Menu **Outreach** loads the full outreach admin UI inside Console.
API calls go through `/api/outreach/{path}` → `ava-outreach:8012` with
`OUTREACH_UI_TOKEN` injected server-side (from console `.env` or `/opt/ava-outreach/.env`).

| Env | Notes |
|-----|--------|
| `OUTREACH_BASE` | default `http://127.0.0.1:8012` |
| `OUTREACH_UI_TOKEN` | optional if readable from outreach `.env` |

Standalone UI remains at `https://a.47z.ru/_ava_outreach/ui/` for emergencies.

## Deploy

```bash
cp main.py /opt/quantum-console/
cp -r static/* /opt/quantum-console/static/
systemctl restart quantum-console
```
