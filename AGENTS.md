# Quantum Labs Office — Agent Onboarding

**Это репозиторий office-сервисов Quantum Labs**, не Polyhub trading.

## Что здесь

- `outreach/` — Bitrix outreach (FastAPI, `:8012`)
- `mailer/` — post-call письма, календарь, Телемост (`:8000`)
- `text-bot/` — Telegram-бот (`:8011`)
- `delno-api/` — DELNO platform API (multi-tenant SaaS)
- `docs/` — карта прода и состояние

## DELNO (commercial SaaS)

**Мастер-план (canonical):** [`docs/DELNO_MASTER_PLAN.md`](docs/DELNO_MASTER_PLAN.md)

Staging: https://a.47z.ru/delno/ · https://a.47z.ru/delno-api/ · prod path `/opt/delno/`

Second Brain (KB foundation): `/opt/ava-knowledge/brain_platform/` → port as `delno-knowledge`

## Прод (справочно)

- SSH: `ssh root@5.35.86.62`
- Сайт: https://a.47z.ru
- UI: https://a.47z.ru/_ava_outreach/ui/

| Путь | Сервис |
|------|--------|
| `/opt/ava-outreach` | `ava-outreach.service` |
| `/opt/ava-mailer` | `ava-mailer.service` |
| `/opt/ava-text-bot` | `ava-text-bot.service` |
| `/opt/polyhub/src` | **НЕ ТРОГАТЬ** (trading) |
| `/root/ava` | Asterisk AVA voice — **не ломать** |

Секреты: `/opt/ava-outreach/.env`, `/opt/ava-mailer/.env`, `/opt/ava-text-bot/.env`.

## Не ломать

Asterisk, AVA docker, Mango, VPN, `/opt/polyhub`.

## Проверки на сервере

```bash
systemctl status ava-outreach ava-mailer ava-text-bot
curl -sf http://127.0.0.1:8012/health
curl -sf http://127.0.0.1:8000/health
curl -sf http://127.0.0.1:8011/health
```

Снаружи: `curl -sf https://a.47z.ru/_ava_outreach/health`

## Cloud Agent / local bootstrap

```bash
./scripts/cloud-agent-install.sh   # uv venvs + deps + local .env stubs
./scripts/cloud-agent-start.sh     # mailer :8000, text-bot :8011, outreach :8012
```

- Outreach UI: `http://127.0.0.1:8012/ui/` (token from `OUTREACH_UI_TOKEN`, default local stub `dev-local-token-quantum`)
- Mailer reads `/opt/ava-mailer/.env` (created by install). Placeholder `OPENAI_API_KEY` boots the process; real key needed for LLM routes.
- Text-bot without `TELEGRAM_BOT_TOKEN` / `OPENAI_API_KEY` stays `degraded` but `/health` works.
- Live Bitrix sync needs a portal with REST subscription + valid `BITRIX_WEBHOOK_URL`.
