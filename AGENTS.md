# Quantum Labs Office — Agent Onboarding

**Это репозиторий office-сервисов Quantum Labs**, не Polyhub trading.

## Что здесь

| Папка | Сервис | Порт |
|-------|--------|------|
| `outreach/` | Bitrix outreach | `:8012` |
| `mailer/` | post-call / legacy calendar·Telemost | `:8000` |
| `text-bot/` | Telegram + HTTP секретарь | `:8011` |
| `console/` | **пульт управления** | `:8013` |
| `knowledge/` | общая база знаний / brain | `:8017` |
| `calendar/` | CalDAV check/suggest/create | `:8014` |
| `conference/` | Телемост + приглашения | `:8016` |
| `files/` | брокер файлов | `:8015` |
| `sheets-campaign/` | обзвон из Google Sheet | `:8018` |
| `docs/` | карта прода и состояние | — |

## Дисциплина разработки (обязательно)

1. **Любое изменение** → commit + push в ветку + PR (не оставлять только на проде).
2. **Журнал** → править [`CHANGELOG.md`](CHANGELOG.md) на каждое значимое изменение.
3. **Стандарты** → [`CONTRIBUTING.md`](CONTRIBUTING.md): conventional commits, semver, без секретов в git.
4. Прод обновлять **из git**, затем smoke `/health`.

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
| `/opt/ava-knowledge` | `ava-knowledge.service` |
| `/opt/ava-calendar` | `ava-calendar.service` |
| `/opt/ava-conference` | `ava-conference.service` |
| `/opt/ava-files` | `ava-files.service` |
| `/opt/ava-sheets-campaign` | `ava-sheets-campaign.service` |
| `/opt/polyhub/src` | **НЕ ТРОГАТЬ** (trading) |
| `/root/ava` | Asterisk AVA voice — **не ломать** |

Секреты: `/opt/ava-*/.env`, `/opt/quantum-console/.env` (mode 600). Knowledge content на проде может жить отдельно от git vault.

## Не ломать

Asterisk, AVA docker, Mango, VPN, `/opt/polyhub`.

## Проверки на сервере

```bash
systemctl status ava-outreach ava-mailer ava-text-bot quantum-console \
  ava-knowledge ava-calendar ava-conference ava-files ava-sheets-campaign
curl -sf http://127.0.0.1:8013/health
curl -sf http://127.0.0.1:8017/health
curl -sf http://127.0.0.1:8012/health
```

Снаружи: `curl -sf https://a.47z.ru/_ava_outreach/health`
