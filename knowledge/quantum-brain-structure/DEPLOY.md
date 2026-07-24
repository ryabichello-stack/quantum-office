# Deploy — пустой Second Brain structure pack

Не трогает Polyhub / Asterisk / Mango / VPN.

## A. Postgres (локально / на сервере)

```bash
cd knowledge/quantum-brain-structure
cp .env.example .env
# задайте POSTGRES_PASSWORD / BRAIN_APP_PASSWORD
docker compose up -d
./scripts/init-postgres.sh
# проверка:
docker compose exec postgres psql -U postgres -d quantum_brain -c '\dx'
```

Порт по умолчанию: **5433** (чтобы не конфликтовать с системным Postgres).

`BRAIN_DATABASE_URL` пример:

```text
postgresql://brain_app:CHANGE_ME@127.0.0.1:5433/quantum_brain
```

## B. Vault directories на диск

```bash
sudo mkdir -p /opt/ava-knowledge/{vault,data,content}
sudo rsync -a vault/ /opt/ava-knowledge/vault/quantum-brain/
sudo rsync -a content/ /opt/ava-knowledge/content/
# data/ остаётся пустым runtime
```

## C. Сервис ava-knowledge (код из office-репо)

```bash
# на машине с quantum-office:
sudo bash knowledge/scripts/install_prod.sh
# затем в /opt/ava-knowledge/.env:
#   BRAIN_STORE=postgres
#   BRAIN_VECTOR_BACKEND=pgvector
#   BRAIN_DATABASE_URL=...
#   BRAIN_VAULT_PATH=/opt/ava-knowledge/vault/quantum-brain
#   KNOWLEDGE_READ_MODE=legacy   # пока нет контента; brain — после наполнения
sudo systemctl restart ava-knowledge
curl -sS http://127.0.0.1:8017/health
```

Опционально поставить unit-файлы из `systemd/` этого pack’а (если ещё не стоят).

## D. Инициализация схемы без docker (уже есть Postgres)

```bash
psql "$BRAIN_DATABASE_URL" -f schema/schema_postgres.sql
# или из app:
#   PYTHONPATH=/opt/ava-knowledge python -m brain_platform init-pg
```

## E. Smoke пустого корпуса

```bash
curl -sS http://127.0.0.1:8017/api/brain/health
# search вернёт пусто/мало — это нормально до ingest контента
```

## Rollback / изоляция

- Structure pack не содержит знаний — удаление `/opt/ava-knowledge/vault/quantum-brain` безопасно для секретов.
- Voice остаётся на `KNOWLEDGE_READ_MODE=legacy`, пока не зальёте FAQ и не переключите на `brain`.
