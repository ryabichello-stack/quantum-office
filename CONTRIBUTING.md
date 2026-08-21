# Contributing — Quantum Office

Правила профессиональной разработки для этого репозитория.
Кратко: **код → commit → push → PR → CHANGELOG → review → merge → deploy**.

## 1. Источник истины

| Правило | Деталь |
|---------|--------|
| Git = канон | Прод (`/opt/ava-*`, `/opt/quantum-console`) обновляется **из** репозитория, не наоборот |
| Секреты вне git | Только `.env.example`. Реальные `.env`, OAuth tokens, SA keys — на сервере mode `600` |
| Не трогать | `/opt/polyhub`, ядро Asterisk/Mango/VPN без явной задачи |

## 2. Ветки и PR

- Ветка: `cursor/<кратко>-9b51` (lowercase)
- Conventional Commits: `feat|fix|docs|chore|refactor|test|ci: …`
- Один PR = одна цель; описание: что / зачем / как проверить / риски
- Draft PR можно открывать рано; перед merge — ready + актуальный `CHANGELOG.md`

## 3. Журнал версий (обязательно)

Файл: [`CHANGELOG.md`](CHANGELOG.md) (Keep a Changelog).

На каждое значимое изменение в ветке:

1. Добавьте пункт в секцию `## [Unreleased]` (`Added` / `Changed` / `Fixed` / `Removed` / `Security`)
2. Перед merge в `main` перенесите Unreleased в новый или существующий релиз `[X.Y.Z] — YYYY-MM-DD`
3. SemVer для **стека office** (корневой журнал):
   - **MAJOR** — ломающие API/контракты между сервисами или dialplan
   - **MINOR** — новая функциональность (пульт, сервис, endpoint)
   - **PATCH** — багфиксы, доки, мелкие правки без контрактов

Опционально сервисы держат локальный `version` в FastAPI/`__version__` — тогда дублируйте строку в CHANGELOG под сервисом.

## 4. Чеклист перед push / PR

- [ ] Нет `.env`, `*token*`, `*credential*`, дампов БД
- [ ] `CHANGELOG.md` обновлён
- [ ] README / PROD_MAP / AGENTS затронуты, если менялись порты/пути/сервисы
- [ ] Smoke на проде или локально: `/health` затронутых сервисов
- [ ] Dialplan/телефония: только осознанно; после правок — `dialplan reload` и проверка входящей

## 5. Deploy

```bash
# пример: console
tar czf /tmp/svc.tgz -C console .
# на сервере: распаковать → scripts/install_prod.sh или systemctl restart
```

После деплоя — коротко в PR / CHANGELOG: куда выкатили и что проверили.

## 6. Запрещено

- Коммитить секреты «на минуту»
- Править прод без последующего commit в git
- Отключать транскрипцию голоса / ломать Asterisk без явного accept
- Оставлять изменения только на сервере
