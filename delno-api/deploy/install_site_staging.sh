#!/usr/bin/env bash
# Rebuild staging site (a.47z.ru/delno) with DELNO_API_URL → delno-api PostgreSQL.
set -euo pipefail

STACK_DIR="${STACK_DIR:-/opt/delno}"
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
SITE_SRC="${SITE_SRC:-${REPO_ROOT}/DELNO-site-v23}"
BASE_PATH="${NEXT_PUBLIC_BASE_PATH:-/delno}"
SITE_PORT="${SITE_PORT:-18019}"

echo "==> DELNO site staging rebuild → ${STACK_DIR}/site"

if [ ! -f "${SITE_SRC}/Dockerfile" ]; then
  echo "ERROR: ${SITE_SRC}/Dockerfile not found"
  exit 1
fi

mkdir -p "${STACK_DIR}/site"
rsync -a --delete "${SITE_SRC}/" "${STACK_DIR}/site/" \
  --exclude node_modules --exclude .next --exclude .sites-runtime --exclude .wrangler

echo "==> docker build (basePath=${BASE_PATH})"
docker build \
  --build-arg NEXT_PUBLIC_BASE_PATH="${BASE_PATH}" \
  -t delno-site:latest \
  "${STACK_DIR}/site"

docker network create delno-internal 2>/dev/null || true

docker rm -f delno-site 2>/dev/null || true

ENV_FILE=()
[ -f "${STACK_DIR}/.env" ] && ENV_FILE=(--env-file "${STACK_DIR}/.env")

# Join delno-internal network to reach api:8020
docker run -d --name delno-site --restart unless-stopped \
  "${ENV_FILE[@]}" \
  --network delno-internal \
  -e DELNO_API_URL="${DELNO_API_URL:-http://api:8020}" \
  -e DELNO_TENANT_SLUG="${DELNO_TENANT_SLUG:-delno-demo}" \
  -p "127.0.0.1:${SITE_PORT}:3000" \
  delno-site:latest

echo "==> smoke: site health + lead proxy"
curl -sf "http://127.0.0.1:${SITE_PORT}/" | head -c 80 && echo
curl -sf "http://127.0.0.1:18020/v1/health" && echo

echo "==> optional lead test (set RUN_LEAD_SMOKE=1)"
if [ "${RUN_LEAD_SMOKE:-0}" = "1" ]; then
  curl -sf -X POST "http://127.0.0.1:${SITE_PORT}/api/leads" \
    -H "Content-Type: application/json" \
    -d '{"source":"deploy-smoke","name":"Smoke Test","phone":"+79990001122","email":"smoke@delno.one"}' \
    | head -c 200 && echo
fi

echo "==> done: https://a.47z.ru/delno/"
