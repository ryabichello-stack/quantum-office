#!/usr/bin/env bash
# Restore DELNO stack on Cloud4Box from a git checkout (no secrets in git).
# Usage (on server as root):
#   git clone <repo> /tmp/quantum-office && cd /tmp/quantum-office
#   bash delno-api/deploy/restore_cloud4box.sh
# Then: copy secrets into /opt/delno/.env from backup / password manager.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
STACK_DIR="${STACK_DIR:-/opt/delno}"
DRY_RUN="${DRY_RUN:-0}"

echo "==> DELNO restore from git → ${STACK_DIR}"
echo "    repo: ${REPO_ROOT}"

need() { command -v "$1" >/dev/null || { echo "missing $1"; exit 1; }; }
need docker
need rsync
need nginx

mkdir -p "${STACK_DIR}"/{deploy,cdn,ingress/wiki,ingress/status}

sync_dir() {
  local src="$1" dst="$2"
  if [ ! -d "$src" ]; then
    echo "WARN: skip missing $src"
    return 0
  fi
  echo "rsync $src → $dst"
  if [ "$DRY_RUN" = "1" ]; then return 0; fi
  mkdir -p "$dst"
  rsync -a --delete \
    --exclude '.env' --exclude '.env.*' --exclude 'node_modules' --exclude '.next' \
    --exclude 'venv' --exclude '__pycache__' --exclude '*.pyc' --exclude 'data' \
    --exclude '*.db' --exclude 'vault' \
    "$src"/ "$dst"/
}

# Layout mapping (git → /opt/delno)
sync_dir "${REPO_ROOT}/delno-api"              "${STACK_DIR}/api"
sync_dir "${REPO_ROOT}/delno-web"              "${STACK_DIR}/web"
sync_dir "${REPO_ROOT}/delno-admin"            "${STACK_DIR}/admin"
sync_dir "${REPO_ROOT}/DELNO-site-v23"         "${STACK_DIR}/site"
sync_dir "${REPO_ROOT}/delno-office/knowledge" "${STACK_DIR}/knowledge"
sync_dir "${REPO_ROOT}/delno-office/mail"      "${STACK_DIR}/mail"
sync_dir "${REPO_ROOT}/delno-office/files"     "${STACK_DIR}/files"
sync_dir "${REPO_ROOT}/delno-office/calendar"  "${STACK_DIR}/calendar"
sync_dir "${REPO_ROOT}/delno-office/conference" "${STACK_DIR}/conference"
sync_dir "${REPO_ROOT}/delno-api/deploy"       "${STACK_DIR}/deploy"

if [ -d "${REPO_ROOT}/delno-api/deploy/static/cdn" ]; then
  rsync -a "${REPO_ROOT}/delno-api/deploy/static/cdn"/ "${STACK_DIR}/cdn"/ || true
fi
if [ -d "${REPO_ROOT}/delno-api/deploy/static/wiki" ]; then
  rsync -a "${REPO_ROOT}/delno-api/deploy/static/wiki"/ "${STACK_DIR}/ingress/wiki"/ || true
fi
if [ -d "${REPO_ROOT}/delno-api/deploy/static/status" ]; then
  rsync -a "${REPO_ROOT}/delno-api/deploy/static/status"/ "${STACK_DIR}/ingress/status"/ || true
fi

cp "${REPO_ROOT}/delno-api/deploy/docker-compose.stack.yml" "${STACK_DIR}/docker-compose.yml"

if [ ! -f "${STACK_DIR}/.env" ]; then
  echo "==> No ${STACK_DIR}/.env — copying template (FILL SECRETS before up)"
  cp "${REPO_ROOT}/delno-api/.env.example" "${STACK_DIR}/.env"
  chmod 600 "${STACK_DIR}/.env"
  echo "    EDIT ${STACK_DIR}/.env then re-run with RUN_COMPOSE=1"
fi

# Nginx ingress (HTTP + HTTPS + stream SNI)
if [ -f "${REPO_ROOT}/delno-api/deploy/nginx-dlno.ru.conf" ]; then
  cp "${REPO_ROOT}/delno-api/deploy/nginx-dlno.ru.conf" /etc/nginx/sites-available/dlno.ru.conf
  ln -sf /etc/nginx/sites-available/dlno.ru.conf /etc/nginx/sites-enabled/dlno.ru.conf
fi
if [ -f "${REPO_ROOT}/delno-api/deploy/nginx-dlno.ru.ssl.conf" ]; then
  cp "${REPO_ROOT}/delno-api/deploy/nginx-dlno.ru.ssl.conf" /etc/nginx/sites-available/dlno.ru.ssl.conf
  # enable only if certs exist
  if [ -f /etc/letsencrypt/live/dlno.ru/fullchain.pem ]; then
    ln -sf /etc/nginx/sites-available/dlno.ru.ssl.conf /etc/nginx/sites-enabled/dlno.ru.ssl.conf
  else
    echo "WARN: LE cert missing — skip ssl site until certbot"
  fi
fi
if [ -f "${REPO_ROOT}/delno-api/deploy/nginx-stream-sni-mux-443.conf" ]; then
  mkdir -p /etc/nginx/stream.d
  cp "${REPO_ROOT}/delno-api/deploy/nginx-stream-sni-mux-443.conf" /etc/nginx/stream.d/sni-mux-443.conf
fi
nginx -t && systemctl reload nginx || true

if [ "${RUN_COMPOSE:-0}" = "1" ]; then
  echo "==> docker compose build/up"
  cd "${STACK_DIR}"
  docker compose build
  docker compose up -d
  echo "==> migrate"
  docker compose exec -T api alembic upgrade head || \
    docker compose run --rm api alembic upgrade head || true
  curl -sf http://127.0.0.1:18020/health || true
  echo
fi

echo "==> restore files synced. Secrets stay in ${STACK_DIR}/.env only."
echo "    Docs: docs/DELNO_RESTORE.md"
