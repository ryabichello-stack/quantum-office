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

> **2026-11-11:** старый QL Beget `5.35.86.62` / `a.47z.ru` **безвозвратно уничтожен** (данные потеряны). Не SSH-ить туда. Новый прод — Cloud4Box. Подробнее: [`docs/QL_DISASTER_RECOVERY.md`](docs/QL_DISASTER_RECOVERY.md).

- SSH: `ssh root@161.104.89.123`
- Временно по IP: `http://161.104.89.123/_ava_*`, `/_quantum_console/`
- Compose: `/opt/quantum-office` (`deploy/cloud4box/`)
- Секреты: `/opt/quantum-office/.env` (mode 600)

| Путь / контейнер | Порт | Маршрут |
|------------------|------|---------|
| mailer | `:8000` | health |
| text-bot | `:8011` | `/_ava_secretary/` |
| outreach | `:8012` | `/_ava_outreach/` |
| console | `:8013` | `/_quantum_console/` |
| calendar | `:8014` | health |
| files | `:8015` | health |
| conference | `:8016` | `/_ava_conference/` |
| knowledge | `:8017` | `/_ava_knowledge/` |
| 3x-ui / xray | `:2053` / `:443` | panel + VLESS |

Asterisk / AVA voice / Mango / Polyhub с старого QL **не восстановлены** (потеряны вместе с хостом).

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
