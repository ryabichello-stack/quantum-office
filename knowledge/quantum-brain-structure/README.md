# quantum-brain-structure

**Структура** Second Brain / vault / Postgres — **без самих знаний**.

Назначение: быстро поднять пустой каркас базы знаний (каталоги, ACL meta, SQL-схема, systemd, docker Postgres+pgvector), затем залить контент отдельно.

> Код приложения `ava-knowledge` / `brain_platform` живёт в репозитории [`quantum-office`](https://github.com/ryabichello-stack/quantum-office) (`knowledge/`).  
> Этот каталог — **deployable structure pack**. Его можно скопировать в private repo `quantum-brain` когда он будет создан.

## Что внутри / чего нет

| Есть | Нет |
|------|-----|
| Дерево vault (пустые шаблоны) | FAQ / playbook / платформенные тексты |
| `_meta` taxonomy, ACL, principals | Почта, контакты, embeddings |
| `schema_postgres.sql` / SQLite schema | `.env` с секретами |
| docker-compose (Postgres 16 + pgvector) | Dump прод-БД |
| systemd unit templates | Polyhub / Asterisk / Mango / VPN |
| bootstrap-скрипты | |

## Быстрый старт (пустой инстанс)

```bash
# 1) Postgres + pgvector
cd knowledge/quantum-brain-structure
cp .env.example .env   # заполнить пароли / OPENAI_API_KEY позже
docker compose up -d
./scripts/init-postgres.sh

# 2) Приложить структуру vault на сервер (пример)
sudo mkdir -p /opt/ava-knowledge/vault
sudo rsync -a vault/ /opt/ava-knowledge/vault/quantum-brain/

# 3) Код сервиса — из quantum-office/knowledge (отдельно)
#    см. knowledge/scripts/install_prod.sh в office-репо
#    BRAIN_VAULT_PATH=/opt/ava-knowledge/vault/quantum-brain
#    BRAIN_STORE=postgres
#    BRAIN_DATABASE_URL=postgresql://brain_app:...@127.0.0.1:5433/quantum_brain

# 4) После появления markdown-шардов:
#    python -m brain_platform ingest --sources vault
```

Подробности: [`DEPLOY.md`](./DEPLOY.md), карта дерева: [`STRUCTURE.md`](./STRUCTURE.md).

## Как добавить знания позже

1. Скопировать шаблон `vault/_templates/NOTE.template.md` → `vault/<area>/<slug>.md`
2. Заполнить frontmatter + тело
3. Обновить `vault/_meta/shards.yaml`
4. `brain ingest --sources vault` (+ `embed-backfill` при необходимости)

Не коммитьте секреты, дампы БД, почту, PII.

## Вынести в отдельный GitHub repo

```bash
# когда будет доступ на создание private repo quantum-brain:
git subtree split -P knowledge/quantum-brain-structure -b quantum-brain-structure
# затем push ветки в новый remote
```
