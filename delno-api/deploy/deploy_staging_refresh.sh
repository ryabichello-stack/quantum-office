#!/usr/bin/env bash
# Refresh DELNO on server: api + knowledge + site (staging AND dlno.ru prod root).
# Targets: https://a.47z.ru/delno/ (delno-site :18019) + https://dlno.ru/ (delno-site-root :18022)
set -euo pipefail

STACK_DIR="${STACK_DIR:-/opt/delno}"
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
SSH_HOST="${SSH_HOST:-root@5.35.86.62}"
SSH_KEY="${SSH_KEY:-}"
SITE_BACKUP="${SITE_BACKUP:-/opt/delno/site.bak.1788465018}"

SSH_OPTS=(-o BatchMode=yes)
if [ -n "$SSH_KEY" ]; then
  SSH_OPTS=(-i "$SSH_KEY" -o BatchMode=yes)
fi
RSYNC_SSH=(ssh "${SSH_OPTS[@]}")

echo "==> sync delno-api + delno-knowledge → ${SSH_HOST}:${STACK_DIR}"

rsync -az --delete -e "${RSYNC_SSH[*]}" \
  --exclude node_modules --exclude .next --exclude __pycache__ --exclude .venv \
  "${REPO_ROOT}/delno-api/" "${SSH_HOST}:${STACK_DIR}/api/"

rsync -az --delete -e "${RSYNC_SSH[*]}" \
  --exclude __pycache__ --exclude .venv \
  "${REPO_ROOT}/delno-knowledge/" "${SSH_HOST}:${STACK_DIR}/knowledge/"

echo "==> overlay widget sources on site (no full-site delete — repo checkout is partial)"
rsync -az -e "${RSYNC_SSH[*]}" \
  "${REPO_ROOT}/DELNO-site-v23/components/widget/" "${SSH_HOST}:${STACK_DIR}/site/components/widget/"
rsync -az -e "${RSYNC_SSH[*]}" \
  "${REPO_ROOT}/DELNO-site-v23/app/api/widget/" "${SSH_HOST}:${STACK_DIR}/site/app/api/widget/"
rsync -az -e "${RSYNC_SSH[*]}" \
  "${REPO_ROOT}/DELNO-site-v23/app/api/widget/voice/" "${SSH_HOST}:${STACK_DIR}/site/app/api/widget/voice/" 2>/dev/null || true
rsync -az -e "${RSYNC_SSH[*]}" \
  "${REPO_ROOT}/DELNO-site-v23/app/api/stt/" "${SSH_HOST}:${STACK_DIR}/site/app/api/stt/" 2>/dev/null || true
rsync -az -e "${RSYNC_SSH[*]}" \
  "${REPO_ROOT}/DELNO-site-v23/lib/widgetApi.ts" "${SSH_HOST}:${STACK_DIR}/site/lib/widgetApi.ts" 2>/dev/null || true
rsync -az -e "${RSYNC_SSH[*]}" \
  "${REPO_ROOT}/DELNO-site-v23/lib/delnoVoice.ts" "${SSH_HOST}:${STACK_DIR}/site/lib/delnoVoice.ts" 2>/dev/null || true
rsync -az -e "${RSYNC_SSH[*]}" \
  "${REPO_ROOT}/DELNO-site-v23/app/v2/VoiceDemo.tsx" "${SSH_HOST}:${STACK_DIR}/site/app/v2/VoiceDemo.tsx" 2>/dev/null || true
rsync -az -e "${RSYNC_SSH[*]}" \
  "${REPO_ROOT}/DELNO-site-v23/app/v2/v2.css" "${SSH_HOST}:${STACK_DIR}/site/app/v2/v2.css" 2>/dev/null || true
rsync -az -e "${RSYNC_SSH[*]}" \
  "${REPO_ROOT}/DELNO-site-v23/hooks/useDelnoVoice.ts" "${SSH_HOST}:${STACK_DIR}/site/hooks/useDelnoVoice.ts" 2>/dev/null || true

echo "==> rebuild + restart containers"
ssh "${SSH_OPTS[@]}" "$SSH_HOST" bash -s <<REMOTE
set -euo pipefail
SITE="${STACK_DIR}/site"
BAK="${SITE_BACKUP}"
if [ ! -f "\$SITE/package.json" ] && [ -d "\$BAK" ]; then
  echo "site scaffold missing — restoring from \$BAK"
  rsync -a "\$BAK/" "\$SITE/" --exclude node_modules --exclude .next
fi
docker rm -f delno-site 2>/dev/null || true
cd ${STACK_DIR}
docker compose build knowledge api site
docker compose up -d knowledge api site
echo "==> build delno-site-root (https://dlno.ru) :18022"
docker build --build-arg NEXT_PUBLIC_BASE_PATH= -t delno-site-root:latest "\$SITE"
docker rm -f delno-site-root 2>/dev/null || true
ENV_FILE=()
[ -f "${STACK_DIR}/.env" ] && ENV_FILE=(--env-file "${STACK_DIR}/.env")
docker run -d --name delno-site-root --restart unless-stopped \\
  "\${ENV_FILE[@]}" \\
  --network delno-internal \\
  -e DELNO_API_URL=http://api:8020 \\
  -e DELNO_TENANT_SLUG=delno-demo \\
  -p 127.0.0.1:18022:3000 \\
  delno-site-root:latest
for i in \$(seq 1 40); do
  curl -sf http://127.0.0.1:18020/v1/health >/dev/null && curl -sf http://127.0.0.1:18021/health >/dev/null && break
  sleep 3
done
curl -sf http://127.0.0.1:18020/v1/health && echo
curl -sf http://127.0.0.1:18021/health && echo
docker exec delno-knowledge python -m brain_platform seed-demo --verify | tail -20
curl -sf -X POST http://127.0.0.1:18020/v1/public/widget/message \\
  -H 'Content-Type: application/json' \\
  -H 'X-Tenant-Slug: delno-demo' \\
  -d '{"site_key":"demo_dlno","message":"Сколько стоит DELNO?","visitor_id":"deploy-smoke"}' \\
  | head -c 400 && echo
curl -sf http://127.0.0.1:18022/ | head -c 60 && echo
REMOTE

echo "==> done: https://dlno.ru/ · https://a.47z.ru/delno/ · https://api.dlno.ru/"
