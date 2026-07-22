# Quantum Labs Office — Agent Onboarding

**Это репозиторий office-сервисов Quantum Labs**, не Polyhub trading.

## Что здесь

- `outreach/` — Bitrix outreach (FastAPI, `:8012`)
- `mailer/` — post-call письма, календарь (`:8000`); Telemost внутри calendar пока остаётся
- `conference/` — **отдельный** сервис Телемост + email-приглашения (`:8013`, on-demand)
- `text-bot/` — Telegram-бот (`:8011`)
- `docs/` — карта прода и состояние

Голосовой сценарий «создай конференцию, пригласи …» → `POST /api/conferences` в `conference/`. См. `docs/CONFERENCE_SERVICE.md`.

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
