#!/usr/bin/env bash
# Refresh DELNO staging stack on a.47z.ru (/opt/delno): api + knowledge + site.
set -euo pipefail

STACK_DIR="${STACK_DIR:-/opt/delno}"
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
SSH_HOST="${SSH_HOST:-root@5.35.86.62}"
SSH_KEY="${SSH_KEY:-}"

SSH_OPTS=(-o BatchMode=yes)
RSYNC_SSH=(ssh "${SSH_OPTS[@]}")
if [ -n "$SSH_KEY" ]; then
  SSH_OPTS=(-i "$SSH_KEY" -o BatchMode=yes)
  RSYNC_SSH=(ssh -i "$SSH_KEY" -o BatchMode=yes)
fi

echo "==> sync sources → ${SSH_HOST}:${STACK_DIR}"

rsync -az --delete -e "${RSYNC_SSH[*]}" \
  --exclude node_modules --exclude .next --exclude __pycache__ --exclude .venv \
  "${REPO_ROOT}/delno-api/" "${SSH_HOST}:${STACK_DIR}/api/"

rsync -az --delete -e "${RSYNC_SSH[*]}" \
  --exclude __pycache__ --exclude .venv \
  "${REPO_ROOT}/delno-knowledge/" "${SSH_HOST}:${STACK_DIR}/knowledge/"

rsync -az --delete -e "${RSYNC_SSH[*]}" \
  --exclude node_modules --exclude .next --exclude .sites-runtime --exclude .wrangler \
  "${REPO_ROOT}/DELNO-site-v23/" "${SSH_HOST}:${STACK_DIR}/site/"

echo "==> rebuild + restart containers"
ssh "${SSH_OPTS[@]}" "$SSH_HOST" bash -s <<'REMOTE'
set -euo pipefail
cd /opt/delno
docker compose build knowledge api site
docker compose up -d knowledge api site
echo "==> wait for health"
for i in $(seq 1 30); do
  if curl -sf http://127.0.0.1:18020/v1/health >/dev/null && curl -sf http://127.0.0.1:18021/health >/dev/null; then
    break
  fi
  sleep 2
done
curl -sf http://127.0.0.1:18020/v1/health && echo
curl -sf http://127.0.0.1:18021/health && echo
docker exec delno-knowledge python -m brain_platform seed-demo --verify | tail -25
echo "==> widget smoke"
curl -sf -X POST http://127.0.0.1:18020/v1/public/widget/message \
  -H 'Content-Type: application/json' \
  -H 'X-Tenant-Slug: delno-demo' \
  -d '{"site_key":"demo_dlno","message":"Сколько стоит DELNO?","visitor_id":"deploy-smoke"}' \
  | head -c 500 && echo
REMOTE

echo "==> done: https://a.47z.ru/delno/"
