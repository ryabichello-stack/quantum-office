# DELNO — текущее состояние (обновлено 2026-09-01)

## Prod
- **URL:** https://a.47z.ru/delno/
- **Хост:** `5.35.86.62` (Quantum Labs, тот же nginx что Polyhub/outreach)
- **Путь на сервере:** `/opt/delno-site`
- **Сервис:** `delno-site.service` (Docker → `127.0.0.1:8019`)
- **Версия кода:** export v23 (коммит Sites `07ef5336…`)

## Репозиторий в workspace
- `DELNO-site-v23/` — исходники сайта + `docs/` (Master Spec, Decisions, Changelog)
- `quantum-office/` — **только reference**, не коммитить DELNO сюда без явной задачи
- Целевой репо: **`delno-platform`** (ещё не создан отдельно)

## Phase 1 — что уже есть
- Лендинг v2 (главная `/` → v2), альтернатива `/v4`
- Голосовое демо (`VoiceDemo`, `/api/tts`)
- Lead form → `/api/leads` (modal, centered, backdrop)
- Юридические страницы: privacy, terms
- Docker + nginx subpath `/delno`

## Phase 1 — пробелы vs Master Spec
| Требование | Статус |
|-----------|--------|
| 5–10 сек clarity test | Нужен UX-аудит; v4 — целевая версия по spec |
| v4 как основная страница | Сейчас на prod — v2; v4 доступна как `/delno/v4` |
| Lead → backend/CRM | API есть; **TELEGRAM_CHAT_ID не настроен** на prod |
| Поле «сайт компании» в форме | Проверить поля формы vs spec |
| dlno.ru как основной домен | Пока staging на a.47z.ru/delno |
| Premium visual (orb, bento, v4) | v4 CSS есть, не default |

## Следующие шаги (после сайта — не начинать раньше)
1. Аудит quantum-office → reference map
2. Unified DELNO Backend (modular monolith)
3. Multi-Tenant Core
4. Customer Cabinet
5. Tenant Voice Operator

## Связь с quantum-office
Переиспользовать как reference: `text-bot`, `mailer`, outreach telephony/knowledge patterns.
Не трогать: `/opt/polyhub`, Asterisk, AVA docker.
