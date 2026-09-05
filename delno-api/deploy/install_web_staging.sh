#!/usr/bin/env bash
# Rebuild tenant cabinet (a.47z.ru/delno-app) → delno-api JWT auth.
set -euo pipefail

STACK_DIR="${STACK_DIR:-/opt/delno}"
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
WEB_SRC="${WEB_SRC:-${REPO_ROOT}/delno-web}"
BASE_PATH="${NEXT_PUBLIC_BASE_PATH:-/delno-app}"
WEB_PORT="${WEB_PORT:-18023}"
API_PUBLIC="${NEXT_PUBLIC_DELNO_API_URL:-https://a.47z.ru/delno-api}"

echo "==> DELNO web staging rebuild → ${STACK_DIR}/delno-web (basePath=${BASE_PATH})"

if [ ! -f "${WEB_SRC}/Dockerfile" ]; then
  echo "ERROR: ${WEB_SRC}/Dockerfile not found"
  exit 1
fi

mkdir -p "${STACK_DIR}/delno-web"
rsync -a --delete "${WEB_SRC}/" "${STACK_DIR}/delno-web/" \
  --exclude node_modules --exclude .next

echo "==> docker build delno-web"
docker build \
  --build-arg NEXT_PUBLIC_DELNO_API_URL="${API_PUBLIC}" \
  --build-arg NEXT_PUBLIC_BASE_PATH="${BASE_PATH}" \
  -t delno-web:latest \
  "${STACK_DIR}/delno-web"

docker rm -f delno-web 2>/dev/null || true
docker run -d --name delno-web --restart unless-stopped \
  -e NEXT_PUBLIC_DELNO_API_URL="${API_PUBLIC}" \
  -p "127.0.0.1:${WEB_PORT}:3000" \
  delno-web:latest

echo "==> smoke"
curl -sf "http://127.0.0.1:${WEB_PORT}/" | head -c 80 && echo
curl -sf "http://127.0.0.1:18020/v1/health" && echo

echo "==> done: https://a.47z.ru${BASE_PATH}/"
