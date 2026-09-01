#!/usr/bin/env bash
# Full DELNO stack deploy to /opt/delno (api + knowledge + postgres + site)
set -euo pipefail

STACK_DIR="${STACK_DIR:-/opt/delno}"
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"

echo "==> DELNO full stack deploy → ${STACK_DIR}"

mkdir -p "${STACK_DIR}"/{api,knowledge,site,site-src,deploy}

# API
rsync -a --delete "${REPO_ROOT}/delno-api/" "${STACK_DIR}/api/" \
  --exclude .venv --exclude __pycache__ --exclude .pytest_cache --exclude .env

# Knowledge
rsync -a --delete "${REPO_ROOT}/delno-knowledge/" "${STACK_DIR}/knowledge/" \
  --exclude __pycache__ --exclude data --exclude .env

# Compose
cp "${REPO_ROOT}/delno-api/deploy/docker-compose.stack.yml" "${STACK_DIR}/docker-compose.yml"

cd "${STACK_DIR}"
docker compose build api knowledge
docker compose up -d postgres
sleep 3
docker compose up -d api knowledge
docker compose ps

echo "==> health"
curl -sf "http://127.0.0.1:18020/v1/health" && echo
curl -sf "http://127.0.0.1:18021/api/brain/health" && echo || echo "WARN: knowledge health pending init-db"

echo "==> done. Site deploy separately: install_dlno_ru.sh / staging rebuild"
