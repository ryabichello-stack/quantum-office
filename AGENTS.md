# Quantum Labs Office — Agent Onboarding

**Это репозиторий office-сервисов Quantum Labs**, не Polyhub trading.

## Что здесь

- `outreach/` — Bitrix outreach (FastAPI, `:8012`)
- `mailer/` — post-call письма, календарь, Телемост (`:8000`)
- `text-bot/` — Telegram-бот (`:8011`)
- `console/` — **пульт управления** секретарём / линией / звонками (`:8013`)
- `docs/` — карта прода и состояние

## Прод (справочно)

- SSH: `ssh root@5.35.86.62`
- Сайт: https://a.47z.ru
- UI outreach: https://a.47z.ru/_ava_outreach/ui/
- Пульт: https://a.47z.ru/_quantum_console/

| Путь | Сервис |
|------|--------|
| `/opt/ava-outreach` | `ava-outreach.service` |
| `/opt/ava-mailer` | `ava-mailer.service` |
| `/opt/ava-text-bot` | `ava-text-bot.service` |
| `/opt/quantum-console` | `quantum-console.service` |
| `/opt/polyhub/src` | **НЕ ТРОГАТЬ** (trading) |
| `/root/ava` | Asterisk AVA voice — **не ломать** |

Секреты: `/opt/ava-outreach/.env`, `/opt/ava-mailer/.env`, `/opt/ava-text-bot/.env`, `/opt/quantum-console/.env`.

## Не ломать

Asterisk, AVA docker, Mango, VPN, `/opt/polyhub`.

## Проверки на сервере

```bash
systemctl status ava-outreach ava-mailer ava-text-bot quantum-console
curl -sf http://127.0.0.1:8012/health
curl -sf http://127.0.0.1:8000/health
curl -sf http://127.0.0.1:8011/health
curl -sf http://127.0.0.1:8013/health
```

Снаружи: `curl -sf https://a.47z.ru/_ava_outreach/health`
