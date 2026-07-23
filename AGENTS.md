# Quantum Labs Office — Agent Onboarding

**Это репозиторий office-сервисов Quantum Labs**, не Polyhub trading.

## Что здесь

- `outreach/` — Bitrix outreach (FastAPI, `:8012`)
- `mailer/` — post-call письма (`:8000`); legacy calendar/Telemost ещё внутри, не ломаем
- `knowledge/` — **общая** база знаний для голоса и текста (`:8017`)
- `calendar/` — **отдельный** CalDAV check/suggest/create (`:8014`)
- `conference/` — **отдельный** Телемост + email-приглашения (`:8016`)
- `files/` — **отдельный** брокер файлов: local/repo/Я.Диск/Mail.ru → email/Telegram (`:8015`)
- `text-bot/` — ИИ-секретарь Telegram + HTTP (`:8011`)
- `docs/` — карта прода и состояние

См. `knowledge/README.md`, `docs/CALENDAR_SERVICE.md`, `docs/CONFERENCE_SERVICE.md`, `docs/FILES_SERVICE.md`.

**Second Brain (архитектура, без реализации до Accept):**
- `docs/architecture/ADR-0001-second-brain.md`
- `docs/architecture/SECOND_BRAIN_ROADMAP.md`
- `docs/architecture/KNOWLEDGE_BASELINE.md`

## Прод (справочно)

- SSH: `ssh root@5.35.86.62`
- Сайт: https://a.47z.ru
- UI: https://a.47z.ru/_ava_outreach/ui/

| Путь | Сервис |
|------|--------|
| `/opt/ava-outreach` | `ava-outreach.service` |
| `/opt/ava-mailer` | `ava-mailer.service` |
| `/opt/ava-knowledge` | `ava-knowledge.service` |
| `/opt/ava-calendar` | `ava-calendar.service` |
| `/opt/ava-conference` | `ava-conference.service` |
| `/opt/ava-files` | `ava-files.service` |
| `/opt/ava-text-bot` | `ava-text-bot.service` |
| `/opt/polyhub/src` | **НЕ ТРОГАТЬ** (trading) |
| `/root/ava` | Asterisk AVA voice — **не ломать** |

Секреты: `/opt/ava-*/.env` (mode 600). Knowledge content: `/root/ava/config/knowledge/`.

## Не ломать

Asterisk, AVA docker, Mango, VPN, `/opt/polyhub`.

## Проверки на сервере

```bash
systemctl status ava-outreach ava-mailer ava-knowledge ava-text-bot
curl -sf http://127.0.0.1:8017/health
curl -sf http://127.0.0.1:8017/api/knowledge/topics
curl -sf http://127.0.0.1:8011/health
```

Снаружи: `curl -sf https://a.47z.ru/_ava_outreach/health`
