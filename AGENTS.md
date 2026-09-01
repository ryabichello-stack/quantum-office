# Quantum Labs Office — Agent Onboarding

**Это репозиторий office-сервисов Quantum Labs**, не Polyhub trading.

## Что здесь

- `outreach/` — Bitrix outreach (FastAPI, `:8012`)
- `mailer/` — post-call письма, календарь, Телемост (`:8000`)
- `text-bot/` — Telegram-бот (`:8011`)
- `delno-api/` — DELNO platform API (multi-tenant SaaS)
- `docs/` — карта прода и состояние
- `docs/architecture/` — **AI Revenue OS Этап 0** (AS_IS / TARGET / GAP / MIGRATION)

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
