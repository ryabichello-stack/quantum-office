#!/usr/bin/env bash
# Apply schema to an already-running compose Postgres.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

PASS="${POSTGRES_PASSWORD:-CHANGE_ME_SUPER}"
APP_PASS="${BRAIN_APP_PASSWORD:-CHANGE_ME}"
PORT="${POSTGRES_PORT:-5433}"

echo "==> waiting for postgres on :${PORT}"
for _ in $(seq 1 60); do
  if docker compose exec -T postgres pg_isready -U postgres >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
docker compose exec -T postgres pg_isready -U postgres

echo "==> ensure role + database"
docker compose exec -T -e PGPASSWORD="$PASS" postgres psql -U postgres -d postgres <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'brain_app') THEN
    CREATE ROLE brain_app LOGIN PASSWORD '${APP_PASS}';
  ELSE
    ALTER ROLE brain_app PASSWORD '${APP_PASS}';
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'brain_readonly') THEN
    CREATE ROLE brain_readonly LOGIN PASSWORD '${APP_PASS}_ro';
  END IF;
END
\$\$;
SELECT 'CREATE DATABASE quantum_brain OWNER brain_app'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'quantum_brain')\gexec
GRANT ALL PRIVILEGES ON DATABASE quantum_brain TO brain_app;
SQL

echo "==> apply schema"
docker compose exec -T -e PGPASSWORD="$PASS" postgres \
  psql -U postgres -d quantum_brain -v ON_ERROR_STOP=1 < "$ROOT/schema/schema_postgres.sql"

docker compose exec -T -e PGPASSWORD="$PASS" postgres psql -U postgres -d quantum_brain <<'SQL'
GRANT USAGE ON SCHEMA public TO brain_app;
GRANT USAGE ON SCHEMA brain_public, brain_private TO brain_app;
GRANT ALL ON ALL TABLES IN SCHEMA public TO brain_app;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO brain_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO brain_app;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO brain_readonly;
SQL

echo "==> ok"
docker compose exec -T -e PGPASSWORD="$PASS" postgres \
  psql -U postgres -d quantum_brain -c "SELECT extname FROM pg_extension WHERE extname IN ('vector','pg_trgm');"
docker compose exec -T -e PGPASSWORD="$PASS" postgres \
  psql -U postgres -d quantum_brain -c "\dt"
